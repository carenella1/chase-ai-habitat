document.addEventListener("DOMContentLoaded", () => {
    if (!document.querySelector(".panel-generate")) return;

    const $ = id => document.getElementById(id);
    const esc = s => String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");

    const STATUS_LABELS = {
        queued: "Queued…",
        starting_comfyui: "Starting ComfyUI…",
        unloading_llm: "Freeing GPU memory from the chat model…",
        generating: "Generating…",
        saving: "Saving image…",
        done: "Done!",
        error: "Error",
        cancelled: "Cancelled",
    };

    const WATCHDOG_MS = 6 * 60 * 1000; // if a job hasn't resolved by then, the
    // server may have died mid-job (see creative_engine.py's orphan cleanup) —
    // surface a toast instead of leaving the user staring at a stuck bar.

    let pollTimer = null;
    let watchdogTimer = null;
    let currentJobId = null;
    let lastGenerateBody = null;
    let galleryItems = [];
    let activeSource = "user";
    let selectedForDelete = new Set();

    const EMPTY_STATES = {
        user: '<div class="empty-state"><div class="empty-icon">◎</div><div>No images yet.</div><div class="empty-sub">Generate your first image above.</div></div>',
        nex: '<div class="empty-state"><div class="empty-icon">◎</div><div>Nex hasn\'t felt moved to create anything yet.</div><div class="empty-sub">It only turns its most significant moments into art — at most about once a day.</div></div>',
    };

    async function loadEngineStatus() {
        try {
            const s = await fetch("/creative/engine-status").then(r => r.json());
            const dot = $("cs-comfy-dot");
            if (s.online) {
                $("cs-comfy-status").textContent = "Online";
                $("cs-comfy-sub").textContent = "ready to generate";
                if (dot) { dot.style.background = "#00ffc8"; dot.style.boxShadow = "0 0 8px #00ffc8"; }
            } else if (s.starting) {
                $("cs-comfy-status").textContent = "Starting…";
                $("cs-comfy-sub").textContent = "give it a moment";
                if (dot) { dot.style.background = "#ffaa33"; dot.style.boxShadow = "0 0 8px #ffaa33"; }
            } else {
                $("cs-comfy-status").textContent = "Offline";
                $("cs-comfy-sub").textContent = s.comfyui_dir_found ? "will start on generate" : "not installed — see install_creative.md";
                if (dot) { dot.style.background = "#ff6666"; dot.style.boxShadow = "0 0 8px #ff6666"; }
            }

            const models = s.models || {};
            $("cs-turbo-status").textContent = models.turbo ? "Ready" : "Missing files";
            $("cs-turbo-status").style.color = models.turbo ? "#00ffc8" : "#ff6666";
            $("cs-quality-status").textContent = models.quality ? "Ready" : "Missing files";
            $("cs-quality-status").style.color = models.quality ? "#00ffc8" : "#ff6666";
        } catch (e) { console.error("Creative engine status error:", e); }
    }

    function renderGallery() {
        const grid = $("creative-gallery-grid");
        if (!grid) return;
        const items = galleryItems.filter(item => (item.source || "user") === activeSource);
        if (!items.length) {
            grid.innerHTML = EMPTY_STATES[activeSource] || EMPTY_STATES.user;
            updateToolbar();
            return;
        }
        grid.innerHTML = items.map(item => {
            const isNex = item.source === "nex";
            const badgeClass = "creative-gallery-badge" + (isNex ? " badge-nex" : "");
            const badgeText = isNex ? "NEX" : (item.model_choice === "quality" ? "FLUX.2" : "TURBO");
            const selectedClass = selectedForDelete.has(item.job_id) ? " queued-delete" : "";
            return `
            <div class="creative-gallery-item${selectedClass}" data-job-id="${esc(item.job_id)}">
                <span class="${badgeClass}">${badgeText}</span>
                <img src="${item.image_url}" alt="${esc(item.prompt || "")}" loading="lazy">
            </div>`;
        }).join("");
        updateToolbar();
    }

    async function loadGallery() {
        try {
            galleryItems = await fetch("/creative/gallery").then(r => r.json());
            renderGallery();
        } catch (e) { console.error("Creative gallery error:", e); }
    }

    function setActiveTab(source) {
        activeSource = source;
        selectedForDelete.clear();
        document.querySelectorAll(".creative-gallery-tab").forEach(btn => {
            btn.classList.toggle("active", btn.dataset.source === source);
        });
        renderGallery();
    }

    document.querySelectorAll(".creative-gallery-tab").forEach(btn => {
        btn.addEventListener("click", () => setActiveTab(btn.dataset.source));
    });

    /* =========================
       TOAST — surfaces stuck/failed generations with Retry/Cancel
    ========================= */
    function ensureToast() {
        let toast = document.getElementById("creative-toast");
        if (!toast) {
            toast = document.createElement("div");
            toast.id = "creative-toast";
            document.body.appendChild(toast);
        }
        return toast;
    }

    function hideToast() {
        const toast = document.getElementById("creative-toast");
        if (toast) toast.classList.remove("visible");
    }

    function showToast(message, { retry = false, cancel = false, kind = "error" } = {}) {
        const toast = ensureToast();
        toast.className = `creative-toast visible is-${kind}`;

        let buttons = "";
        if (retry) buttons += `<button class="creative-toast-btn creative-toast-btn-primary" id="creative-toast-retry">Retry</button>`;
        if (cancel) buttons += `<button class="creative-toast-btn creative-toast-btn-danger" id="creative-toast-cancel">Cancel job</button>`;
        buttons += `<button class="creative-toast-btn" id="creative-toast-dismiss">Dismiss</button>`;

        toast.innerHTML = `<div class="creative-toast-msg">${esc(message)}</div><div class="creative-toast-actions">${buttons}</div>`;

        $("creative-toast-dismiss")?.addEventListener("click", hideToast);
        if (retry) $("creative-toast-retry")?.addEventListener("click", () => { hideToast(); retryGenerate(); });
        if (cancel) $("creative-toast-cancel")?.addEventListener("click", () => { hideToast(); cancelCurrentJob(); });
    }

    /* =========================
       FULL-TEXT HOVER BUBBLE
    ========================= */
    function ensureCaptionTip() {
        let tip = document.getElementById("creative-caption-tip");
        if (!tip) {
            tip = document.createElement("div");
            tip.id = "creative-caption-tip";
            document.body.appendChild(tip);
        }
        return tip;
    }

    function showCaptionTip(el, item) {
        const isNex = item.source === "nex";
        const text = isNex && item.artist_note ? item.artist_note : (item.prompt || "");
        if (!text) return;
        const originLine = isNex && item.origin_agent
            ? `<span class="cct-origin">— ${esc(item.origin_agent)}</span>` : "";
        const tip = ensureCaptionTip();
        tip.innerHTML = `${esc(text)}${originLine}`;
        tip.classList.add("visible");

        const margin = 10;
        tip.style.left = "0px";
        tip.style.top = "0px";
        const r = el.getBoundingClientRect();
        const tw = tip.offsetWidth || 300;
        const th = tip.offsetHeight || 60;
        let left = r.left + r.width / 2 - tw / 2;
        left = Math.max(margin, Math.min(left, window.innerWidth - tw - margin));
        let top = r.top - th - 8;
        if (top < margin) top = r.bottom + 8;
        tip.style.left = `${left}px`;
        tip.style.top = `${top}px`;
    }

    function hideCaptionTip() {
        const tip = document.getElementById("creative-caption-tip");
        if (tip) tip.classList.remove("visible");
    }

    /* =========================
       DELETE — selection, toolbar, right-click menu
    ========================= */
    function updateToolbar() {
        const toolbar = $("creative-gallery-toolbar");
        const label = $("creative-toolbar-label");
        if (!toolbar) return;
        toolbar.classList.toggle("active", selectedForDelete.size > 0);
        if (label) {
            label.textContent = selectedForDelete.size === 1
                ? "1 selected" : `${selectedForDelete.size} selected`;
        }
    }

    function toggleSelect(jobId) {
        if (selectedForDelete.has(jobId)) selectedForDelete.delete(jobId);
        else selectedForDelete.add(jobId);
        renderGallery();
    }

    function ensureContextMenu() {
        let menu = document.getElementById("creative-context-menu");
        if (!menu) {
            menu = document.createElement("div");
            menu.id = "creative-context-menu";
            menu.className = "creative-context-menu";
            menu.style.display = "none";
            document.body.appendChild(menu);
        }
        return menu;
    }

    function hideContextMenu() {
        const menu = document.getElementById("creative-context-menu");
        if (menu) menu.style.display = "none";
    }

    function showContextMenu(x, y, jobId) {
        const menu = ensureContextMenu();
        menu.innerHTML = `<div class="creative-context-menu-item danger" id="ctx-delete-item">🗑 Delete</div>`;
        menu.style.display = "block";
        const mw = menu.offsetWidth || 140;
        const mh = menu.offsetHeight || 40;
        menu.style.left = `${Math.min(x, window.innerWidth - mw - 8)}px`;
        menu.style.top = `${Math.min(y, window.innerHeight - mh - 8)}px`;
        document.getElementById("ctx-delete-item").addEventListener("click", () => {
            hideContextMenu();
            deleteItems([jobId]);
        });
    }

    document.addEventListener("click", (e) => {
        const menu = document.getElementById("creative-context-menu");
        if (menu && menu.style.display !== "none" && !menu.contains(e.target)) hideContextMenu();
    });

    async function deleteItems(jobIds) {
        if (!jobIds.length) return;
        const label = jobIds.length === 1 ? "this image" : `these ${jobIds.length} images`;
        if (!confirm(`Delete ${label}? This can't be undone.`)) return;
        try {
            await Promise.all(jobIds.map(id =>
                fetch(`/creative/delete/${id}`, { method: "POST" })
            ));
        } catch (e) { console.error("Creative delete error:", e); }
        selectedForDelete.clear();
        hideCaptionTip();
        await loadGallery();
    }

    const galleryGrid = $("creative-gallery-grid");
    if (galleryGrid) {
        galleryGrid.addEventListener("click", (e) => {
            const el = e.target.closest(".creative-gallery-item");
            if (!el) return;
            toggleSelect(el.dataset.jobId);
        });
        galleryGrid.addEventListener("contextmenu", (e) => {
            const el = e.target.closest(".creative-gallery-item");
            if (!el) return;
            e.preventDefault();
            showContextMenu(e.clientX, e.clientY, el.dataset.jobId);
        });
        galleryGrid.addEventListener("mouseover", (e) => {
            const el = e.target.closest(".creative-gallery-item");
            if (!el) return;
            const item = galleryItems.find(g => g.job_id === el.dataset.jobId);
            if (item) showCaptionTip(el, item);
        });
        galleryGrid.addEventListener("mouseout", (e) => {
            const el = e.target.closest(".creative-gallery-item");
            if (!el || el.contains(e.relatedTarget)) return;
            hideCaptionTip();
        });
    }

    $("creative-toolbar-trash")?.addEventListener("click", () => deleteItems([...selectedForDelete]));
    $("creative-toolbar-cancel")?.addEventListener("click", () => {
        selectedForDelete.clear();
        renderGallery();
    });

    function setProgress(pct) {
        const wrap = $("creative-progress-wrap");
        const fill = $("creative-progress-fill");
        if (wrap) wrap.style.display = "flex";
        if (fill) fill.style.width = `${Math.max(0, Math.min(100, pct))}%`;
    }

    function setStatusLine(text, kind) {
        const line = $("creative-status-line");
        if (!line) return;
        line.textContent = text || "";
        line.className = "creative-status-line" + (kind ? ` is-${kind}` : "");
    }

    function showCancelButton(show) {
        const btn = $("btn-cancel-generate");
        if (!btn) return;
        btn.style.display = show ? "inline-flex" : "none";
        btn.disabled = false;
    }

    function clearWatchdog() {
        if (watchdogTimer) { clearTimeout(watchdogTimer); watchdogTimer = null; }
    }

    async function cancelCurrentJob() {
        if (!currentJobId) return;
        const btn = $("btn-cancel-generate");
        if (btn) btn.disabled = true;
        setStatusLine("Cancelling…", null);
        try {
            await fetch(`/creative/cancel/${currentJobId}`, { method: "POST" });
        } catch (e) { console.error("Creative cancel error:", e); }
        // The poll loop picks up the resulting "cancelled" status on its
        // next tick and finalizes the UI — nothing else to do here.
    }

    function pollJob(jobId) {
        currentJobId = jobId;
        clearWatchdog();
        watchdogTimer = setTimeout(() => {
            showToast(
                "This generation is taking longer than expected. It may still finish " +
                "on its own, or something may have gone wrong.",
                { cancel: true, kind: "warn" }
            );
        }, WATCHDOG_MS);

        if (pollTimer) clearInterval(pollTimer);
        pollTimer = setInterval(async () => {
            try {
                const s = await fetch(`/creative/status/${jobId}`).then(r => r.json());
                if (!s.found) return;
                setProgress(s.progress || 0);
                if (s.status === "error") {
                    setStatusLine(s.error || "Something went wrong.", "error");
                    showToast(s.error || "Something went wrong.", { retry: true });
                    stopPolling();
                } else if (s.status === "cancelled") {
                    setStatusLine(s.error || "Cancelled.", "error");
                    hideToast();
                    stopPolling();
                } else if (s.status === "done") {
                    setStatusLine("Done!", "done");
                    setProgress(100);
                    hideToast();
                    stopPolling();
                    loadGallery();
                } else {
                    setStatusLine(STATUS_LABELS[s.status] || s.status, null);
                }
            } catch (e) { console.error("Creative status poll error:", e); }
        }, 1200);
    }

    function stopPolling() {
        const btn = $("btn-generate");
        if (btn) { btn.disabled = false; btn.textContent = "▶ GENERATE"; }
        if (pollTimer) { clearInterval(pollTimer); pollTimer = null; }
        clearWatchdog();
        showCancelButton(false);
        currentJobId = null;
        loadEngineStatus();
    }

    async function submitGenerate(body) {
        hideToast();
        const btn = $("btn-generate");
        btn.disabled = true;
        btn.textContent = "● WORKING…";
        setProgress(0);
        setStatusLine("Queued…", null);
        showCancelButton(true);

        try {
            const res = await fetch("/creative/generate", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(body),
            }).then(r => r.json());

            if (!res.job_id) {
                setStatusLine(res.error || "Could not start generation.", "error");
                stopPolling();
                return;
            }
            pollJob(res.job_id);
        } catch (e) {
            setStatusLine("Could not reach NEX to start generation.", "error");
            stopPolling();
        }
    }

    function retryGenerate() {
        if (!lastGenerateBody) return;
        submitGenerate(lastGenerateBody);
    }

    async function generate() {
        const prompt = $("cr-prompt").value.trim();
        if (!prompt) {
            setStatusLine("Type a prompt first.", "error");
            return;
        }
        const [width, height] = $("cr-dimensions").value.split("x").map(Number);
        const body = {
            prompt,
            negative_prompt: $("cr-negative").value.trim(),
            model_choice: $("cr-model").value,
            width,
            height,
            lora_name: $("cr-lora-name").value.trim() || null,
            lora_strength: parseFloat($("cr-lora-strength").value) || 0.8,
        };
        lastGenerateBody = body;
        await submitGenerate(body);
    }

    $("btn-generate").addEventListener("click", generate);
    $("btn-cancel-generate")?.addEventListener("click", cancelCurrentJob);

    loadEngineStatus();
    loadGallery();
    setInterval(loadEngineStatus, 15000);
});

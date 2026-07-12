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
    };

    let pollTimer = null;
    let galleryItems = [];
    let activeSource = "user";

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
            return;
        }
        grid.innerHTML = items.map(item => {
            const isNex = item.source === "nex";
            const badgeClass = "creative-gallery-badge" + (isNex ? " badge-nex" : "");
            const badgeText = isNex ? "NEX" : (item.model_choice === "quality" ? "FLUX.2" : "TURBO");
            const caption = isNex && item.artist_note ? item.artist_note : (item.prompt || "");
            const originLine = isNex && item.origin_agent
                ? `<span class="creative-gallery-origin">— ${esc(item.origin_agent)}</span>` : "";
            return `
            <div class="creative-gallery-item">
                <span class="${badgeClass}">${badgeText}</span>
                <img src="${item.image_url}" alt="${esc(item.prompt || "")}" loading="lazy">
                <div class="creative-gallery-caption">${esc(caption.slice(0, 140))}${originLine}</div>
            </div>`;
        }).join("");
    }

    async function loadGallery() {
        try {
            galleryItems = await fetch("/creative/gallery").then(r => r.json());
            renderGallery();
        } catch (e) { console.error("Creative gallery error:", e); }
    }

    function setActiveTab(source) {
        activeSource = source;
        document.querySelectorAll(".creative-gallery-tab").forEach(btn => {
            btn.classList.toggle("active", btn.dataset.source === source);
        });
        renderGallery();
    }

    document.querySelectorAll(".creative-gallery-tab").forEach(btn => {
        btn.addEventListener("click", () => setActiveTab(btn.dataset.source));
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

    function pollJob(jobId) {
        if (pollTimer) clearInterval(pollTimer);
        pollTimer = setInterval(async () => {
            try {
                const s = await fetch(`/creative/status/${jobId}`).then(r => r.json());
                if (!s.found) return;
                setProgress(s.progress || 0);
                if (s.status === "error") {
                    setStatusLine(s.error || "Something went wrong.", "error");
                    stopPolling();
                } else if (s.status === "done") {
                    setStatusLine("Done!", "done");
                    setProgress(100);
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
        loadEngineStatus();
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

        const btn = $("btn-generate");
        btn.disabled = true;
        btn.textContent = "● WORKING…";
        setProgress(0);
        setStatusLine("Queued…", null);

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

    $("btn-generate").addEventListener("click", generate);

    loadEngineStatus();
    loadGallery();
    setInterval(loadEngineStatus, 15000);
});

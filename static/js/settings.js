document.addEventListener("DOMContentLoaded", () => {
    if (!document.querySelector(".settings-page")) return;

    const inputSelect = document.getElementById("input-device-select");
    const outputSelect = document.getElementById("output-device-select");
    const outputNote = document.getElementById("output-device-note");
    const volumeSlider = document.getElementById("settings-volume-slider");
    const volumeIcon = document.getElementById("settings-volume-icon");
    const silenceSlider = document.getElementById("silence-slider");
    const silenceValue = document.getElementById("silence-value");
    const voiceGrid = document.getElementById("voice-grid");
    const voiceActiveLabel = document.getElementById("voice-active-label");
    const voiceClearBtn = document.getElementById("voice-clear-btn");

    /* =========================
       VOLUME — same localStorage key chat.js reads/writes, so both
       sliders stay in sync automatically. No backend involved.
    ========================= */
    function getVolume() {
        const stored = localStorage.getItem("nexVolume");
        const vol = stored !== null ? parseFloat(stored) : 0.8;
        return Number.isFinite(vol) ? Math.min(1, Math.max(0, vol)) : 0.8;
    }

    function updateVolumeIcon(vol) {
        if (!volumeIcon) return;
        volumeIcon.textContent = vol === 0 ? "🔇" : vol < 0.5 ? "🔉" : "🔊";
    }

    if (volumeSlider) {
        const initialVol = getVolume();
        volumeSlider.value = Math.round(initialVol * 100);
        updateVolumeIcon(initialVol);
        volumeSlider.addEventListener("input", () => {
            const vol = volumeSlider.value / 100;
            localStorage.setItem("nexVolume", String(vol));
            updateVolumeIcon(vol);
        });
    }

    /* =========================
       AUDIO OUTPUT — browser-side device list + localStorage.
       A different id scheme than the Python-side input list, so this
       never touches /api/settings.
    ========================= */
    async function loadOutputDevices() {
        if (!outputSelect) return;
        if (!navigator.mediaDevices || !navigator.mediaDevices.enumerateDevices) {
            if (outputNote) outputNote.style.display = "block";
            outputSelect.disabled = true;
            return;
        }
        try {
            // Labels are only populated after a permission grant; the mic
            // permission Nex Live already requests is enough, so we don't
            // request a separate one just for the output list.
            const devices = await navigator.mediaDevices.enumerateDevices();
            const outputs = devices.filter(d => d.kind === "audiooutput");
            const testEl = document.createElement("audio");
            if (typeof testEl.setSinkId !== "function") {
                if (outputNote) outputNote.style.display = "block";
                outputSelect.disabled = true;
                return;
            }
            const saved = localStorage.getItem("nexOutputDeviceId") || "";
            outputSelect.innerHTML = '<option value="">System default</option>';
            // Before mic permission is granted, browsers return a blank
            // placeholder output entry (empty id/label) for privacy —
            // not a real selectable device, so skip it.
            outputs.filter(d => d.deviceId).forEach(d => {
                const opt = document.createElement("option");
                opt.value = d.deviceId;
                opt.textContent = d.label || `Output device (${d.deviceId.slice(0, 6)})`;
                if (d.deviceId === saved) opt.selected = true;
                outputSelect.appendChild(opt);
            });
        } catch (e) {
            console.warn("Could not enumerate output devices:", e);
            if (outputNote) outputNote.style.display = "block";
        }
    }

    if (outputSelect) {
        outputSelect.addEventListener("change", () => {
            localStorage.setItem("nexOutputDeviceId", outputSelect.value || "");
        });
        loadOutputDevices();
    }

    /* =========================
       AUDIO INPUT — server-side (Python/sounddevice) enumeration,
       persisted in settings.json since it drives backend mic capture.
    ========================= */
    async function loadInputDevices() {
        if (!inputSelect) return;
        try {
            const res = await fetch("/api/settings/audio-devices");
            const data = await res.json();
            if (data.status !== "ok") {
                inputSelect.innerHTML = '<option value="">Could not list devices</option>';
                return;
            }
            const settingsRes = await fetch("/api/settings");
            const settingsData = await settingsRes.json();
            const current = settingsData.settings ? settingsData.settings.input_device_index : null;

            inputSelect.innerHTML = "";
            const autoOpt = document.createElement("option");
            autoOpt.value = "";
            autoOpt.textContent = "System default";
            if (current === null || current === undefined) autoOpt.selected = true;
            inputSelect.appendChild(autoOpt);

            data.devices.forEach(d => {
                const opt = document.createElement("option");
                opt.value = d.index;
                opt.textContent = d.name + (d.is_default ? " (system default)" : "");
                if (current === d.index) opt.selected = true;
                inputSelect.appendChild(opt);
            });
        } catch (e) {
            console.warn("Could not load input devices:", e);
            inputSelect.innerHTML = '<option value="">Could not list devices</option>';
        }
    }

    if (inputSelect) {
        inputSelect.addEventListener("change", () => {
            const val = inputSelect.value;
            postSettings({ input_device_index: val === "" ? null : parseInt(val, 10) });
        });
        loadInputDevices();
    }

    /* =========================
       SILENCE SENSITIVITY — server-side, drives Nex Live's mic capture.
    ========================= */
    if (silenceSlider) {
        silenceSlider.addEventListener("input", () => {
            if (silenceValue) silenceValue.textContent = `${silenceSlider.value}ms`;
        });
        silenceSlider.addEventListener("change", () => {
            postSettings({ silence_ms: parseInt(silenceSlider.value, 10) });
        });
    }

    /* =========================
       SETTINGS API HELPERS
    ========================= */
    async function postSettings(partial) {
        try {
            const res = await fetch("/api/settings", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(partial)
            });
            const data = await res.json();
            return data.settings || null;
        } catch (e) {
            console.error("Settings save failed:", e);
            return null;
        }
    }

    async function loadCurrentSettings() {
        try {
            const res = await fetch("/api/settings");
            const data = await res.json();
            if (data.status !== "ok") return;
            const s = data.settings;
            if (silenceSlider && s.silence_ms) {
                silenceSlider.value = s.silence_ms;
                if (silenceValue) silenceValue.textContent = `${s.silence_ms}ms`;
            }
            applyVoiceOverrideUI(s.voice_override);
        } catch (e) { }
    }

    /* =========================
       VOICE TYPE — preview, select, clear
    ========================= */
    function applyVoiceOverrideUI(voiceId) {
        document.querySelectorAll(".voice-card").forEach(card => {
            card.classList.toggle("active", !!voiceId && card.dataset.voiceId === voiceId);
        });
        if (voiceId) {
            const card = document.querySelector(`.voice-card[data-voice-id="${CSS.escape(voiceId)}"]`);
            const label = card ? card.querySelector(".voice-card-label").textContent : voiceId;
            if (voiceActiveLabel) voiceActiveLabel.textContent = label;
            if (voiceClearBtn) voiceClearBtn.style.display = "";
        } else {
            if (voiceActiveLabel) voiceActiveLabel.textContent = "Auto (persona-driven)";
            if (voiceClearBtn) voiceClearBtn.style.display = "none";
        }
    }

    async function previewVoice(voiceId, btn) {
        const original = btn.textContent;
        btn.disabled = true;
        btn.textContent = "Loading…";
        try {
            const res = await fetch("/api/voice/speak", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ text: "Hi, this is my voice.", voice_id: voiceId })
            });
            const data = await res.json();
            if (!data.audio) {
                btn.textContent = "No audio ⚠";
                console.warn(`🔈 Preview for voice "${voiceId}" returned no audio — check habitat_debug.log.`);
                setTimeout(() => { btn.textContent = original; btn.disabled = false; }, 2000);
                return;
            }
            const isWav = data.audio.startsWith("UklG");
            const mime = isWav ? "audio/wav" : "audio/mpeg";
            const audioEl = new Audio(`data:${mime};base64,${data.audio}`);
            audioEl.volume = getVolume();
            audioEl.onended = () => { btn.textContent = original; btn.disabled = false; };
            audioEl.onerror = () => { btn.textContent = original; btn.disabled = false; };
            audioEl.play().catch((e) => {
                console.error("Preview playback failed:", e);
                btn.textContent = original;
                btn.disabled = false;
            });
        } catch (e) {
            console.error("Preview failed:", e);
            btn.textContent = original;
            btn.disabled = false;
        }
    }

    if (voiceGrid) {
        voiceGrid.addEventListener("click", async (e) => {
            const previewBtn = e.target.closest(".voice-preview-btn");
            const selectBtn = e.target.closest(".voice-select-btn");
            if (previewBtn) {
                previewVoice(previewBtn.dataset.voiceId, previewBtn);
            } else if (selectBtn) {
                const settings = await postSettings({ voice_override: selectBtn.dataset.voiceId });
                if (settings) applyVoiceOverrideUI(settings.voice_override);
            }
        });
    }

    if (voiceClearBtn) {
        voiceClearBtn.addEventListener("click", async () => {
            const settings = await postSettings({ voice_override: null });
            if (settings) applyVoiceOverrideUI(settings.voice_override);
        });
    }

    loadCurrentSettings();
});

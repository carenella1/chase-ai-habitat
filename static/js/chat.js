import { sendMessage } from "/static/js/adapters/chatAdapter.js";

document.addEventListener("DOMContentLoaded", () => {
    if (!document.querySelector(".chat-layout")) return;
    console.log("🔥 NEXARION CHAT ONLINE");

    const thread = document.getElementById("chat-thread");
    const input = document.getElementById("chat-input");
    const sendBtn = document.getElementById("send-btn");
    const micBtn = document.getElementById("mic-btn");
    const modeBtn = document.getElementById("mode-toggle");
    const orbOverlay = document.getElementById("orb-overlay");
    const exitOrbBtn = document.getElementById("exit-orb");
    const orbEl = document.getElementById("nexarion-orb");
    const orbStatus = document.getElementById("orb-status-text");
    const orbReply = document.getElementById("orb-response-text");
    const newChatBtn = document.getElementById("new-chat-btn");
    const chatList = document.getElementById("chat-list");
    const traceToggleBtn = document.getElementById("trace-toggle-btn");

    let isListening = false;
    let isSending = false;
    let orbMode = false;
    let activeConvId = null;
    let lastResponse = null;
    let traceEnabled = false;

    /* =========================
       TRACE TOGGLE
    ========================= */
    if (traceToggleBtn) {
        traceToggleBtn.addEventListener("click", () => {
            traceEnabled = !traceEnabled;
            traceToggleBtn.classList.toggle("trace-on", traceEnabled);
            traceToggleBtn.querySelector(".trace-state").textContent = traceEnabled ? "ON" : "OFF";

            // Show/hide all existing trace panels
            document.querySelectorAll(".trace-panel").forEach(p => {
                p.style.display = traceEnabled ? "" : "none";
            });
        });
    }

    /* =========================
       TRACE PANEL BUILDER
    ========================= */
    function buildTracePanel(trace) {
        if (!trace || Object.keys(trace).length === 0) return null;

        const panel = document.createElement("div");
        panel.className = "trace-panel";
        panel.style.display = traceEnabled ? "" : "none";

        // Header (clickable to collapse)
        panel.innerHTML = `
        <div class="trace-panel-header">
            <span class="trace-panel-title">◈ Thinking Trace</span>
            <span class="trace-panel-toggle">▼</span>
        </div>
        <div class="trace-panel-body"></div>`;

        const header = panel.querySelector(".trace-panel-header");
        header.addEventListener("click", () => {
            panel.classList.toggle("collapsed");
        });

        const body = panel.querySelector(".trace-panel-body");

        // Meta row — cycle, domain, tools
        const metaChips = [];
        if (trace.cycle) metaChips.push(`<span class="trace-meta-chip chip-cycle">cycle ${trace.cycle}</span>`);
        if (trace.domain) metaChips.push(`<span class="trace-meta-chip chip-domain">${esc(trace.domain)}</span>`);
        if (trace.tools_used?.length) {
            trace.tools_used.forEach(t => metaChips.push(`<span class="trace-meta-chip chip-tool">⚙ ${esc(t)}</span>`));
        }
        if (metaChips.length) {
            const metaRow = document.createElement("div");
            metaRow.className = "trace-meta-row";
            metaRow.innerHTML = metaChips.join("");
            body.appendChild(metaRow);
        }

        // Active goal
        if (trace.active_goal) {
            const sec = document.createElement("div");
            sec.className = "trace-section";
            sec.innerHTML = `
                <div class="trace-section-label">Active Goal</div>
                <div class="trace-goal">${esc(trace.active_goal)}</div>`;
            body.appendChild(sec);
        }

        // Memory pulled
        if (trace.memory?.length) {
            const sec = document.createElement("div");
            sec.className = "trace-section";
            sec.innerHTML = `<div class="trace-section-label">Memory Retrieved</div>`;
            trace.memory.forEach(line => {
                const typeMatch = line.match(/^\[(FACT|BELIEF \d+%|MEMORY|ENTITY)\]/);
                const typeLabel = typeMatch ? typeMatch[1] : "MEM";
                const content = line.replace(/^\[.*?\]\s*/, "").trim();
                const item = document.createElement("div");
                item.className = "trace-memory-item";
                item.innerHTML = `<span class="mem-type">${esc(typeLabel)}</span>${esc(content.substring(0, 120))}`;
                sec.appendChild(item);
            });
            body.appendChild(sec);
        }

        // Top beliefs activated
        if (trace.beliefs?.length) {
            const sec = document.createElement("div");
            sec.className = "trace-section";
            sec.innerHTML = `<div class="trace-section-label">Beliefs Informing Response</div>`;
            trace.beliefs.slice(0, 4).forEach(b => {
                const conf = Math.round((b.confidence || 0.5) * 100);
                const color = conf > 75 ? "#00ffcc" : conf > 50 ? "#66ccff" : "#ffaa33";
                const item = document.createElement("div");
                item.className = "trace-belief-item";
                item.innerHTML = `
                    <span class="trace-belief-conf" style="color:${color}">${conf}%</span>
                    <span class="trace-belief-text">${esc((b.statement || "").substring(0, 110))}</span>`;
                sec.appendChild(item);
            });
            body.appendChild(sec);
        }

        // Topics context
        if (trace.topics?.length) {
            const sec = document.createElement("div");
            sec.className = "trace-section";
            sec.innerHTML = `
                <div class="trace-section-label">Topic Context</div>
                <div class="trace-section-content">${trace.topics.map(t => esc(t)).join(" · ")}</div>`;
            body.appendChild(sec);
        }

        return panel;
    }

    function esc(s) {
        return String(s || "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
    }

    /* =========================
       MESSAGE RENDERER
    ========================= */
    function addMessage(text, role = "habitat", skipScroll = false, trace = null) {
        const wrap = document.createElement("div");
        wrap.className = `chat-message ${role}`;

        const meta = document.createElement("div");
        meta.className = "chat-meta";
        meta.textContent = role === "user" ? "Chase" : "Nexarion";

        const bubble = document.createElement("div");
        bubble.className = "chat-bubble";
        bubble.textContent = text;

        wrap.appendChild(meta);
        wrap.appendChild(bubble);

        // Add trace panel for NEX responses
        if (role === "habitat" && trace && Object.keys(trace).length > 0) {
            const tracePanel = buildTracePanel(trace);
            if (tracePanel) wrap.appendChild(tracePanel);
        }

        thread.appendChild(wrap);
        if (!skipScroll) thread.scrollTop = thread.scrollHeight;
    }

    function showTyping() {
        const wrap = document.createElement("div");
        wrap.className = "chat-message habitat typing-msg";
        wrap.innerHTML = `<div class="chat-bubble"><div class="typing-indicator"><div class="typing-dot"></div><div class="typing-dot"></div><div class="typing-dot"></div></div></div>`;
        thread.appendChild(wrap);
        thread.scrollTop = thread.scrollHeight;
        return wrap;
    }

    function clearThread() {
        thread.innerHTML = "";
    }

    /* =========================
       LIVE CONTEXT SIDEBAR
    ========================= */
    async function updateLiveContext() {
        try {
            const data = await fetch("/api/chat/context").then(r => r.json());
            if (data.status !== "ok") return;

            const cycleEl = document.getElementById("ctx-cycle");
            const goalEl = document.getElementById("ctx-goal");
            const topicEl = document.getElementById("ctx-topic");
            const beliefsEl = document.getElementById("ctx-beliefs");
            const cyclePill = document.getElementById("chat-cycle-pill");

            if (cycleEl) cycleEl.textContent = (data.cycle || 0).toLocaleString();
            if (cyclePill) cyclePill.textContent = `cycle ${(data.cycle || 0).toLocaleString()}`;
            if (goalEl) goalEl.textContent = data.active_goal || "Exploring freely";
            if (topicEl) topicEl.textContent = data.top_topic || "—";
            if (beliefsEl) beliefsEl.textContent = data.belief_count || "—";
        } catch (e) { }
    }

    // Domain detection on the fly (from last trace response)
    function updateContextFromTrace(trace) {
        if (!trace) return;
        const domainEl = document.getElementById("ctx-domain");
        if (domainEl) domainEl.textContent = trace.domain || "general";
    }

    /* =========================
       CONVERSATIONS SIDEBAR
    ========================= */
    async function loadConversations() {
        try {
            const res = await fetch("/api/chat/list");
            const data = await res.json();
            if (!data.chats) return;

            activeConvId = data.active_id;
            renderConversationList(data.chats, data.active_id);
        } catch (err) {
            console.warn("Could not load conversations:", err);
        }
    }

    function renderConversationList(convs, activeId) {
        if (!chatList) return;
        chatList.innerHTML = "";

        if (convs.length === 0) {
            chatList.innerHTML = `<div style="opacity:0.4;font-size:12px;padding:8px;">No saved chats yet</div>`;
            return;
        }

        convs.forEach(conv => {
            const item = document.createElement("div");
            item.className = `chat-item${conv.id === activeId ? " active" : ""}`;
            item.dataset.id = conv.id;

            const title = document.createElement("div");
            title.style.cssText = "font-size:13px;font-weight:500;margin-bottom:3px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;";
            title.textContent = conv.title || "New Conversation";

            const preview = document.createElement("div");
            preview.style.cssText = "font-size:11px;opacity:0.5;";
            const date = new Date((conv.updated_at || 0) * 1000);
            preview.textContent = date.toLocaleDateString([], { month: "short", day: "numeric" }) +
                " · " + Math.floor((conv.message_count || 0) / 2) + " exchanges";

            item.appendChild(title);
            item.appendChild(preview);
            chatList.appendChild(item);

            item.addEventListener("click", () => loadConversation(conv.id));
        });
    }

    async function loadConversation(convId) {
        try {
            const res = await fetch(`/api/chat/load/${convId}`, { method: "POST" });
            const data = await res.json();
            if (data.status !== "ok") return;

            activeConvId = convId;
            clearThread();

            for (const turn of (data.history || [])) {
                addMessage(turn.content, turn.role === "user" ? "user" : "habitat", true);
            }
            thread.scrollTop = thread.scrollHeight;

            const divider = document.createElement("div");
            divider.style.cssText = `text-align:center;font-size:11px;color:rgba(0,240,255,0.35);
                letter-spacing:1px;text-transform:uppercase;padding:8px 0 4px;`;
            divider.textContent = `— ${data.title || "conversation"} —`;
            thread.appendChild(divider);
            thread.scrollTop = thread.scrollHeight;

            document.querySelectorAll(".chat-item").forEach(el => {
                el.classList.toggle("active", el.dataset.id === convId);
            });

        } catch (err) {
            console.error("Load conversation failed:", err);
        }
    }

    async function startNewChat() {
        try {
            const res = await fetch("/api/chat/new", { method: "POST" });
            const data = await res.json();
            if (data.status !== "ok") return;

            activeConvId = data.chat_id;
            clearThread();
            addMessage("New conversation started. What's on your mind, Chase?", "habitat");
            await loadConversations();
        } catch (err) {
            console.error("New chat failed:", err);
        }
    }

    /* =========================
       RESTORE HISTORY ON LOAD
    ========================= */
    async function restoreHistory() {
        try {
            const res = await fetch("/api/chat/history");
            const data = await res.json();

            await loadConversations();

            if (!data.history || data.history.length === 0) {
                addMessage("Nexarion is online. What's on your mind, Chase?", "habitat");
                return;
            }

            for (const turn of data.history) {
                addMessage(turn.content, turn.role === "user" ? "user" : "habitat", true);
            }
            thread.scrollTop = thread.scrollHeight;

            const divider = document.createElement("div");
            divider.style.cssText = `text-align:center;font-size:11px;color:rgba(0,240,255,0.35);
                letter-spacing:1px;text-transform:uppercase;padding:8px 0 4px;`;
            divider.textContent = `— memory restored · ${Math.floor(data.history.length / 2)} exchanges —`;
            thread.appendChild(divider);
            thread.scrollTop = thread.scrollHeight;

        } catch (err) {
            console.warn("History restore failed:", err);
            addMessage("Nexarion is online.", "habitat");
        }
    }

    /* =========================
       SEND FLOW
    ========================= */
    async function handleSend(overrideText) {
        if (isSending) return;

        const text = (overrideText !== undefined ? overrideText : input.value).trim();
        if (!text) return;

        input.value = "";
        isSending = true;
        sendBtn.disabled = true;
        lastResponse = null;

        addMessage(text, "user");
        if (orbMode) setOrbState("thinking");

        const typing = showTyping();

        try {
            const res = await sendMessage(text);
            lastResponse = res;
            typing.remove();

            if (!res || !res.text) {
                addMessage("⚠️ No response from Nexarion. Is the backend running?", "habitat");
                if (orbMode) setOrbState("idle");
                return;
            }

            // Add message with trace
            addMessage(res.text, "habitat", false, res.trace || null);

            // Update live context from trace
            updateContextFromTrace(res.trace);
            updateLiveContext();

            if (orbReply) orbReply.textContent = res.text;

            loadConversations();

            if (res.audio) {
                if (orbMode) setOrbState("speaking");
                const isWav = res.audio.startsWith("UklG");
                const mime = isWav ? "audio/wav" : "audio/mpeg";
                const audio = new Audio(`data:${mime};base64,${res.audio}`);
                audio.onended = () => {
                    if (orbMode) {
                        setOrbState("idle");
                        setTimeout(startListening, 2000);
                    }
                };
                audio.onerror = () => {
                    const alt = new Audio(`data:${isWav ? "audio/mpeg" : "audio/wav"};base64,${res.audio}`);
                    alt.onended = () => {
                        if (orbMode) { setOrbState("idle"); setTimeout(startListening, 2000); }
                    };
                    alt.play().catch(() => { if (orbMode) setOrbState("idle"); });
                };
                audio.play().catch(() => { if (orbMode) setOrbState("idle"); });
            } else {
                if (orbMode) setOrbState("idle");
            }

        } catch (err) {
            typing.remove();
            addMessage("⚠️ Connection error.", "habitat");
            console.error(err);
            if (orbMode) setOrbState("idle");
        } finally {
            isSending = false;
            sendBtn.disabled = false;
            if (orbMode && !isListening && !lastResponse?.audio) {
                setTimeout(startListening, 4000);
            }
        }
    }

    /* =========================
       MICROPHONE — Python backend
    ========================= */
    function initSpeech() {
        console.log("🎤 Voice: Python backend mode (SpeechRecognition)");
    }

    async function startListening() {
        if (isListening || isSending) return;

        isListening = true;
        if (micBtn) micBtn.classList.add("mic-active");
        input.placeholder = "Listening…";
        input.classList.add("listening");
        if (orbMode) setOrbState("listening");
        if (orbReply) orbReply.textContent = "";

        console.log("🎤 Starting Python mic capture...");

        try {
            const res = await fetch("/api/voice/listen", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({})
            });
            const data = await res.json();

            isListening = false;
            if (micBtn) micBtn.classList.remove("mic-active");
            input.placeholder = "Speak to Nexarion...";
            input.classList.remove("listening", "interim");

            if (data.status === "ok" && data.text) {
                if (orbMode) {
                    await handleSend(data.text);
                } else {
                    input.value = data.text;
                    input.focus();
                }
            } else if (data.status === "timeout") {
                if (orbMode) {
                    setOrbState("idle");
                    setTimeout(startListening, 2000);
                }
            }
        } catch (err) {
            isListening = false;
            if (micBtn) micBtn.classList.remove("mic-active");
            input.placeholder = "Speak to Nexarion...";
            input.classList.remove("listening");
            console.error("🎤 Listen error:", err);
            if (orbMode) setOrbState("idle");
        }
    }

    /* =========================
       ORB MODE
    ========================= */
    function setOrbState(state) {
        if (!orbOverlay) return;
        orbOverlay.dataset.state = state;
        const states = {
            idle: "Nexarion is ready",
            listening: "Listening…",
            thinking: "Processing…",
            speaking: "Speaking…"
        };
        if (orbStatus) orbStatus.textContent = states[state] || "Ready";
        if (orbEl) {
            orbEl.classList.remove("state-listening", "state-thinking", "state-speaking");
            if (state !== "idle") orbEl.classList.add(`state-${state}`);
        }
    }

    if (modeBtn) {
        modeBtn.addEventListener("click", () => {
            orbMode = true;
            if (orbOverlay) {
                orbOverlay.style.display = "flex";
                setOrbState("idle");
            }
        });
    }

    if (exitOrbBtn) {
        exitOrbBtn.addEventListener("click", () => {
            orbMode = false;
            isListening = false;
            if (orbOverlay) orbOverlay.style.display = "none";
        });
    }

    if (orbEl) {
        orbEl.addEventListener("click", () => {
            if (!isListening && !isSending) startListening();
        });
    }

    /* =========================
       EVENT LISTENERS
    ========================= */
    if (sendBtn) sendBtn.addEventListener("click", () => handleSend());
    if (input) {
        input.addEventListener("keydown", e => {
            if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                handleSend();
            }
        });
    }
    if (micBtn) micBtn.addEventListener("click", startListening);
    if (newChatBtn) newChatBtn.addEventListener("click", startNewChat);

    /* =========================
       INITIATION POLLING
    ========================= */
    function addInitiationMessage(text, agent, significance) {
        const msg = document.createElement("div");
        msg.className = "chat-message habitat nexarion-initiated";
        msg.innerHTML = `
            <div class="initiation-label">⬡ Nexarion</div>
            <div class="chat-bubble initiation-bubble">${text}</div>
            <div class="initiation-meta">Initiated · ${agent} · significance ${significance}/10</div>
        `;
        thread.appendChild(msg);
        thread.scrollTop = thread.scrollHeight;
    }

    async function pollInitiations() {
        try {
            const res = await fetch("/api/initiations/pending");
            const data = await res.json();
            const items = data.initiations || [];
            for (const item of items) {
                addInitiationMessage(item.message, item.agent, item.significance);
            }
        } catch (e) { }
    }

    pollInitiations();
    setInterval(pollInitiations, 10000);

    /* =========================
       BOOT
    ========================= */
    initSpeech();
    restoreHistory();
    updateLiveContext();
    setInterval(updateLiveContext, 15000);
});
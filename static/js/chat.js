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

    let isListening = false;
    let isSending = false;
    let orbMode = false;
    let activeConvId = null;
    let lastResponse = null;  // track last response for finally block

    /* =========================
       MESSAGE RENDERER
    ========================= */
    function addMessage(text, role = "habitat", skipScroll = false) {
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

            addMessage(res.text, "habitat");

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

            // In orb mode without audio, restart listening after delay
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
            input.classList.remove("listening");
            input.placeholder = "Speak to Nexarion...";

            console.log("🎤 Voice result:", data.status, "|", data.text);

            if (data.text && data.text.trim()) {
                handleSend(data.text.trim());
            } else {
                if (orbMode) setOrbState("idle");
                if (orbMode) setTimeout(startListening, 1200);
            }

        } catch (err) {
            isListening = false;
            if (micBtn) micBtn.classList.remove("mic-active");
            input.classList.remove("listening");
            input.placeholder = "Speak to Nexarion...";
            if (orbMode) setOrbState("idle");
            console.error("🎤 Voice fetch error:", err);
        }
    }

    function toggleMic() {
        if (isListening) return;
        startListening();
    }

    /* =========================
       ORB MODE
    ========================= */
    function setOrbState(state) {
        if (!orbEl || !orbStatus) return;
        orbEl.classList.remove("orb-idle", "orb-listening", "orb-thinking", "orb-speaking");
        orbEl.classList.add(`orb-${state}`);
        orbStatus.textContent = {
            idle: "Nexarion is ready",
            listening: "Listening…",
            thinking: "Nexarion is thinking…",
            speaking: "Nexarion is speaking…"
        }[state] || "";
    }

    function openOrb() {
        orbMode = true;
        if (orbOverlay) orbOverlay.classList.add("orb-visible");
        if (orbReply) orbReply.textContent = "";
        setOrbState("idle");
        setTimeout(startListening, 500);
    }

    function closeOrb() {
        orbMode = false;
        isListening = false;
        if (orbOverlay) orbOverlay.classList.remove("orb-visible");
        if (micBtn) micBtn.classList.remove("mic-active");
        input.placeholder = "Speak to Nexarion...";
    }

    /* =========================
       EVENTS
    ========================= */
    sendBtn?.addEventListener("click", () => handleSend());
    input?.addEventListener("keydown", (e) => {
        if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); handleSend(); }
    });
    micBtn?.addEventListener("click", toggleMic);
    modeBtn?.addEventListener("click", openOrb);
    exitOrbBtn?.addEventListener("click", closeOrb);
    orbEl?.addEventListener("click", () => { if (orbMode && !isSending) toggleMic(); });
    newChatBtn?.addEventListener("click", startNewChat);


    /* =========================
    NEXARION INITIATION POLLER
    Checks every 10s if Nexarion has something to say.
    When it does, renders a visually distinct "initiated" message.
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
        } catch (e) {
            // silent — polling should never crash the chat
        }
    }

    // Start polling — check immediately, then every 10 seconds
    pollInitiations();
    setInterval(pollInitiations, 10000);

    /* =========================
       BOOT
    ========================= */
    initSpeech();
    restoreHistory();
});
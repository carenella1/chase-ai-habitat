import { sendMessage } from "/static/js/adapters/chatAdapter.js";

/* =========================
   INIT
========================= */

document.addEventListener("DOMContentLoaded", () => {
    if (!document.querySelector(".chat-layout")) return;

    console.log("🔥 CHAT SYSTEM ONLINE");

    const thread = document.querySelector("#chat-thread");
    const input = document.querySelector("#chat-input");
    const sendBtn = document.querySelector("#send-btn");

    /* =========================
       MESSAGE RENDER
    ========================= */

    function addMessage(text, role = "assistant") {
        const msg = document.createElement("div");
        msg.className = `chat-message ${role}`;

        msg.innerHTML = `
            <div class="chat-bubble">${text}</div>
        `;

        thread.appendChild(msg);
        thread.scrollTop = thread.scrollHeight;
    }

    function showTyping() {
        const msg = document.createElement("div");
        msg.className = "chat-message assistant typing";

        msg.innerHTML = `
            <div class="chat-bubble">...</div>
        `;

        thread.appendChild(msg);
        thread.scrollTop = thread.scrollHeight;

        return msg;
    }

    /* =========================
       SEND FLOW
    ========================= */

    async function handleSend() {
        const text = input.value.trim();
        if (!text) return;

        addMessage(text, "user");
        input.value = "";

        const typing = showTyping();

        const res = await sendMessage(text);

        typing.remove();

        if (!res) {
            addMessage("⚠️ Error reaching AI", "assistant");
            return;
        }

        addMessage(res.text, "assistant");

        if (res.audio) {
            const audio = new Audio(`data:audio/mp3;base64,${res.audio}`);
            audio.play().catch(() => { });
        }
    }

    /* =========================
       EVENTS
    ========================= */

    sendBtn.addEventListener("click", handleSend);

    input.addEventListener("keydown", (e) => {
        if (e.key === "Enter") {
            e.preventDefault();
            handleSend();
        }
    });
});
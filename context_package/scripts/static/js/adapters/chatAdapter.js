import { apiPost } from "/static/js/core/apiClient.js";

/* =========================
   CHAT API LAYER
========================= */

export async function sendMessage(message) {
    const res = await apiPost("/api/chat", { message });

    if (!res) return null;

    return {
        text: res.response || "",
        audio: res.audio || ""
    };
}
/* =========================
   CHAT API LAYER
========================= */

/**
 * Streams a chat response from /api/chat (Server-Sent Events).
 *
 * callbacks:
 *   onChunk(text)        - called with each new text piece as it arrives
 *   onDone({text, trace}) - called once with the final, fully-cleaned text
 *   onError(err)         - called on network/parse failure
 */
export async function streamMessage(message, { onChunk, onDone, onError } = {}) {
    try {
        const res = await fetch("/api/chat", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ message })
        });

        if (!res.ok || !res.body) {
            onError?.(new Error(`HTTP ${res.status}`));
            return;
        }

        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";

        while (true) {
            const { value, done } = await reader.read();
            if (done) break;
            buffer += decoder.decode(value, { stream: true });

            // SSE events are separated by a blank line
            let sep;
            while ((sep = buffer.indexOf("\n\n")) !== -1) {
                const rawEvent = buffer.slice(0, sep);
                buffer = buffer.slice(sep + 2);
                _handleSseEvent(rawEvent, onChunk, onDone);
            }
        }
    } catch (err) {
        onError?.(err);
    }
}

function _handleSseEvent(rawEvent, onChunk, onDone) {
    let eventType = "message";
    let dataLine = "";
    for (const line of rawEvent.split("\n")) {
        if (line.startsWith("event:")) eventType = line.slice(6).trim();
        else if (line.startsWith("data:")) dataLine += line.slice(5).trim();
    }
    if (!dataLine) return;

    let payload;
    try {
        payload = JSON.parse(dataLine);
    } catch {
        return;
    }

    if (eventType === "chunk" && payload.text) {
        onChunk?.(payload.text);
    } else if (eventType === "done") {
        onDone?.(payload);
    }
}

/** Fetches TTS audio for a piece of text. Returns "" on failure. */
export async function speakText(text) {
    try {
        const res = await fetch("/api/voice/speak", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ text })
        });
        if (!res.ok) return "";
        const data = await res.json();
        return data.audio || "";
    } catch {
        return "";
    }
}

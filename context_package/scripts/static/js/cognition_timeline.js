(function () {
    const container = document.getElementById("cognition-log");

    if (!container) {
        console.error("cognition-log container not found");
        return;
    }

    let lastSeenTimestamp = null;

    function truncate(text, maxLength) {
        if (!text) return "";
        return text.length > maxLength ? text.slice(0, maxLength) + "..." : text;
    }

    function renderEntry(entry, prepend = true) {
        const item = document.createElement("div");
        item.className = "cognition-entry";

        const content = entry.content || entry.message || "";
        const reasoning = entry.reasoning || "";
        const confidence = entry.confidence;

        item.innerHTML = `
            <div class="cognition-agent">${entry.agent || "Unknown Agent"}</div>
            <div class="cognition-type">${entry.type || ""}</div>
            <div class="cognition-content">${truncate(content, 240)}</div>
            ${reasoning ? `<div class="cognition-reasoning">${truncate(reasoning, 180)}</div>` : ""}
            <div class="cognition-confidence">confidence: ${confidence ?? "n/a"}</div>
        `;

        if (prepend) {
            container.prepend(item);
        } else {
            container.appendChild(item);
        }
    }

    async function updateTimeline() {
        try {
            const res = await fetch("/cognition");
            const data = await res.json();

            if (!data || !Array.isArray(data.entries) || data.entries.length === 0) return;

            const entries = data.entries;

            if (!lastSeenTimestamp) {
                container.innerHTML = "";
                entries.slice(0, 20).reverse().forEach((entry) => renderEntry(entry, false));
                lastSeenTimestamp = entries[0].timestamp;
                return;
            }

            const newEntries = [];
            for (const entry of entries) {
                if (entry.timestamp === lastSeenTimestamp) break;
                newEntries.push(entry);
            }

            newEntries.reverse().forEach((entry) => renderEntry(entry, true));

            while (container.children.length > 30) {
                container.removeChild(container.lastChild);
            }

            lastSeenTimestamp = entries[0].timestamp;
        } catch (err) {
            console.warn("Timeline update failed", err);
        }
    }

    updateTimeline();
    setInterval(updateTimeline, 2000);
})();
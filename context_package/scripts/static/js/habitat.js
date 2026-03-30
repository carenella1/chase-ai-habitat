let lastCognitionSignature = null;
let lastCognitionHash = null;

/* =========================
   IMPORT ADAPTERS
========================= */

import { getCognitionFeed } from "/static/js/adapters/habitatAdapter.js?v=2";

import { apiPost } from "/static/js/core/apiClient.js";

/* =========================
   PAGE INIT
========================= */

document.addEventListener("DOMContentLoaded", () => {
    if (!document.querySelector(".habitat-page")) return;
    initHabitat();
});

const AGENT_COLORS = {
    Researcher: "#66ccff",
    Explorer: "#ff66cc",
    Strategist: "#ffcc00",
    Curator: "#00ffcc",
    Archivist: "#aaaaaa",
    Builder: "#66ff66"
};

/* =========================
   MAIN INIT
========================= */

function initHabitat() {
    bindEvents();

    // 🔥 INITIAL LOAD (IMPORTANT)
    loadBuilderProposals();
    loadCognitionFeed();

    setInterval(() => {
        console.log("⏱ polling...");
        loadBuilderProposals();
        loadCognitionFeed();
    }, 8000);
}

/* =========================
   EVENTS
========================= */

function bindEvents() {
    document.getElementById("run-cognition")?.addEventListener("click", runCognitionCycle);
    document.getElementById("run-agents")?.addEventListener("click", runAgentTasks);
}

/* =========================
   ACTIONS
========================= */

async function runCognitionCycle() {
    try {
        await apiPost("/api/cognition/run", {});
        await loadCognitionFeed();
    } catch (e) {
        console.error(e);
    }
}

async function runAgentTasks() {
    try {
        await apiPost("/api/agents/execute", {});
        await loadBuilderProposals();
    } catch (e) {
        console.error(e);
    }
}

/* =========================
   HELPERS
========================= */

function safeText(value) {
    return value ? String(value) : "";
}

/* =========================
   COGNITION ENTRY
========================= */
function normalizeCognitionEntry(entry) {
    if (!entry) return null;

    // 🔥 HANDLE NEW FORMAT (your memory.json)
    if (entry.summary || entry.details) {
        return {
            timestamp: entry.timestamp,
            summary: entry.summary || "",
            details: entry.details || "",
            agent: entry.agent || "system",
            priority: entry.priority || "low"
        };
    }

    // 🔥 HANDLE OLD FORMAT (brain loop)
    if (entry.cognition) {
        return {
            timestamp: entry.timestamp,
            summary: entry.cognition.insight || "",
            details: entry.cognition.research || "",
            agent: entry.cognition.agent || "system",
            priority: entry.cognition.source === "wikipedia" ? "high" : "medium"
        };
    }

    return null;
}
function truncate(text, maxLength) {
    if (!text) return "";
    return text.length > maxLength
        ? text.slice(0, maxLength) + "..."
        : text;
}

function formatTime(ts) {
    try {
        const date = ts > 1e12 ? new Date(ts) : new Date(ts * 1000);
        return date.toLocaleTimeString([], {
            hour: "2-digit",
            minute: "2-digit"
        });
    } catch (e) {
        return "";
    }
}

function createCognitionEntry(entry) {

    if (!entry || !entry.cognition) return null;

    const { agent, insight, research, source } = entry.cognition;
    const importance = getImportance(entry);
    const importanceLabel = ["Low", "Medium", "High"][importance] || "Low";

    const wrapper = document.createElement("div");
    wrapper.className = "cognition-entry";

    // 🔍 Split evolution if present
    let mainInsight = insight;
    let evolution = "";
    let evolutionType = "";

    // 🔥 Detect FULL evolution blocks
    if (insight.includes("--- Cross-Agent Evolution ---")) {
        evolutionType = "cross";

        const parts = insight.split("--- Cross-Agent Evolution ---");
        mainInsight = parts[0];
        evolution = parts[1] || "";

    } else if (insight.includes("--- Self Evolution ---")) {
        evolutionType = "self";

        const parts = insight.split("--- Self Evolution ---");
        mainInsight = parts[0];
        evolution = parts[1] || "";

    } else if (insight.includes("--- Evolution ---")) {
        evolutionType = "basic";

        const parts = insight.split("--- Evolution ---");
        mainInsight = parts[0];
        evolution = parts[1] || "";
    }

    wrapper.innerHTML = `
<div class="cog-header">
    <span class="agent" style="color: ${AGENT_COLORS[agent] || "#fff"}">
            ${agent}
    </span>

    <span class="importance importance-${importance}">
            ${importanceLabel}
    </span>

    <span class="time">
        ${formatTimestamp(entry.timestamp)}
    </span>
</div>

        <div class="cog-section insight">
            <div class="label" onclick="toggleSection(this)">
                🧠 Insight
            </div>
            <div class="content">
                ${mainInsight}
        </div>
    </div>

        ${evolution ? `
        <div class="cog-section evolution evolution-${evolutionType}">
            <div class="label">
                ${evolutionType === "cross" ? "🔁 Cross-Agent Evolution"
                : evolutionType === "self" ? "🔄 Self Evolution"
                    : "🔁 Evolution"}
            </div>
            <div class="content">${evolution}</div>
        </div>
        ` : ""}

        ${research ? `
        <div class="cog-section research">
            <div class="label">🌐 Research (${source})</div>
            <div class="content">${research}</div>
        </div>
        ` : ""}
    `;

    return wrapper;

    function getImportance(entry) {
        let score = 0;

        const insight = entry.cognition?.insight || "";
        const research = entry.cognition?.research || "";

        if (insight.length > 300) score += 1;
        if (insight.includes("Evolution")) score += 1;
        if (research) score += 1;

        return score;
    }
}

function formatTimestamp(ts) {
    const date = new Date(ts);
    return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

function toggleSection(label) {
    const content = label.nextElementSibling;
    if (!content) return;

    content.style.display =
        content.style.display === "none" ? "block" : "none";
}

function getCognitionIcon(data) {
    const text = (data.summary || "").toLowerCase();

    if (text.includes("error") || data.priority === "high") return "🚨";
    if (text.includes("memory")) return "🧠";
    if (text.includes("latency")) return "⚡";
    if (text.includes("stable")) return "✅";
    if (text.includes("expanding")) return "📈";

    return "⚙️";
}



/* =========================
   LOAD COGNITION
========================= */

async function loadCognitionFeed() {
    try {
        console.log("FETCHING COGNITION...");

        const container = document.getElementById("cognition-feed");
        if (!container) return;

        container.innerHTML = "";

        const raw = await getCognitionFeed();

        console.log("🧪 ADAPTER RAW:", raw);

        const entries = Array.isArray(raw) ? raw : [];
        console.log("🧪 ENTRIES:", entries);
        // 🔥 FETCH FULL COGNITION STATE (NEW)
        const stateRes = await fetch("/api/cognition/all");
        const stateData = await stateRes.json();

        // 🔥 RENDER NEW UI BLOCKS
        renderCognitionState(stateData);

        entries
            .sort((a, b) => {
                const ta = normalizeTimestamp(a.timestamp);
                const tb = normalizeTimestamp(b.timestamp);
                return tb - ta;
            })

            .forEach(entry => {
                if (!entry || !entry.timestamp) return;

                const el = createCognitionEntry(entry);
                if (!el) return;

                container.appendChild(el);
            });
        entries.sort((a, b) => {
            const ta = normalizeTimestamp(a.timestamp);
            const tb = normalizeTimestamp(b.timestamp);
            return tb - ta;
        });

        console.log("🕒 NEWEST ENTRY TS:", entries[0]?.timestamp);


        const nodes = container.querySelectorAll(".cognition-entry");

        nodes.forEach((node, index) => {
            node.style.opacity = Math.max(1 - index * 0.15, 0.2);
            node.style.transform = `scale(${1 - index * 0.02})`;
        });

        while (container.children.length > 20) {
            container.removeChild(container.lastChild);
        }
        container.scrollTop = 0;
    } catch (err) {
        console.error("Cognition feed error:", err);
    }

}


function renderCognitionState(data) {
    const topicsDiv = document.getElementById("top-topics");
    const synthesisDiv = document.getElementById("synthesis");
    const memoryDiv = document.getElementById("memory-context");

    // =========================
    // 🧠 TOP TOPICS
    // =========================
    topicsDiv.innerHTML = "";
    (data.top_topics || []).forEach(([topic, score]) => {
        const el = document.createElement("span");
        el.textContent = `${topic} (${score.toFixed(1)})`;
        topicsDiv.appendChild(el);
    });

    // =========================
    // ⚡ SYNTHESIS
    // =========================
    synthesisDiv.innerHTML = "";
    (data.synthesis || []).forEach(pair => {
        const el = document.createElement("div");
        el.textContent = `${pair[0]} ⇄ ${pair[1]}`;
        synthesisDiv.appendChild(el);
    });

    // =========================
    // 🔥 MEMORY
    // =========================
    memoryDiv.innerHTML = "";
    (data.memory || []).forEach(m => {
        const el = document.createElement("div");
        el.textContent = m.summary || (m.insight || "").slice(0, 80);
        memoryDiv.appendChild(el);
    });
}

async function loadBuilderProposals() {
    try {
        const res = await fetch(`/api/build/pending?ts=${Date.now()}`);
        const data = await res.json();

        const container = document.getElementById("builder-proposals");
        if (!container) return;

        container.innerHTML = "";

        const proposals = data?.data?.pending || [];

        proposals.forEach(p => {
            const el = document.createElement("div");
            el.className = "proposal";
            el.innerHTML = `
    <div class="proposal-header">
        <div class="proposal-title">
            Act on: ${p.description || "No description"}
        </div>
        <div class="proposal-confidence">
            ${(p.confidence * 100 || 90).toFixed(0)}%
        </div>
    </div>

    <div class="proposal-body">
        <div class="proposal-reason">
            <strong>Reason</strong>
            <div>Generated from cognition</div>
        </div>

        <div class="proposal-impact">
            <strong>Impact</strong>
            <div>${p.impact || "N/A"}</div>
        </div>
    </div>

    <div class="proposal-actions">
        <button onclick="approveBuild('${p.id}')">✓ Deploy</button>
        <button onclick="rejectBuild('${p.id}')">✗ Reject</button>
    </div>
`;
            container.appendChild(el);
        });

    } catch (err) {
        console.error("Builder feed error:", err);
    }
}

function normalizeTimestamp(ts) {
    if (!ts) return 0;

    ts = Number(ts);

    if (ts < 1e12) {
        ts = ts * 1000;
    }

    return ts;
}





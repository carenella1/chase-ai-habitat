/* =========================
   IMPORTS
========================= */
import { apiPost } from "/static/js/core/apiClient.js";

/* =========================
   AGENT COLORS
========================= */
const AGENT_COLORS = {
    Researcher: "#66ccff",
    Explorer: "#ff66cc",
    Strategist: "#ffcc00",
    Curator: "#00ffcc",
    Archivist: "#aaaaaa",
    Builder: "#66ff66",
};

/* =========================
   PAGE INIT
========================= */
document.addEventListener("DOMContentLoaded", () => {
    if (!document.querySelector(".habitat-page")) return;
    initHabitat();
});

function initHabitat() {
    bindEvents();
    loadBuilderProposals();
    loadCognitionFeed();

    setInterval(() => {
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
function formatTimestamp(ts) {
    try {
        const date = ts > 1e12 ? new Date(ts) : new Date(ts * 1000);
        return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
    } catch (e) { return ""; }
}

function normalizeTimestamp(ts) {
    if (!ts) return 0;
    ts = Number(ts);
    return ts < 1e12 ? ts * 1000 : ts;
}

function toggleSection(label) {
    const content = label.nextElementSibling;
    if (!content) return;
    content.style.display = content.style.display === "none" ? "block" : "none";
}

/* =========================
   COGNITION STATUS INDICATOR
   Finds the status pill that contains COGNITION in the header
   and replaces the dynamic word (Idle/Active/Thinking).
   Works by scanning for text nodes — no class dependency.
========================= */
function updateCognitionStatus(entries) {
    // Find the target: the text node showing Idle/Active/Thinking
    // inside whichever element also contains the word "COGNITION"
    const statusEl = getCognitionValueEl();
    if (!statusEl) return;

    if (!entries || entries.length === 0) {
        applyStatus(statusEl, "Idle", "idle");
        return;
    }

    const newest = entries.reduce((max, e) => {
        const ts = normalizeTimestamp(e.timestamp);
        return ts > max ? ts : max;
    }, 0);

    const ageSeconds = (Date.now() - newest) / 1000;

    if (ageSeconds < 90) {
        applyStatus(statusEl, "Active", "active");
    } else if (ageSeconds < 300) {
        applyStatus(statusEl, "Thinking", "thinking");
    } else {
        applyStatus(statusEl, "Idle", "idle");
    }
}

function applyStatus(el, text, state) {
    el.textContent = text;
    el.className = el.className
        .replace(/(active|idle|thinking)/g, "")
        .trim() + " " + state;
}

// Find the child element that holds the dynamic status word
// inside the COGNITION status pill — works regardless of class names
function getCognitionValueEl() {
    // Direct ID lookup — habitat.html has id="status-cognition" on this element
    return document.getElementById("status-cognition");
}

/* =========================
   COGNITION ENTRY BUILDER
========================= */
function createCognitionEntry(entry) {
    if (!entry) return null;

    // --- Normalise format ---
    let agent, insight, research, source, source_url;

    if (entry.cognition) {
        agent = entry.cognition.agent || "System";
        insight = entry.cognition.insight || "";
        research = entry.cognition.research || "";
        source = entry.cognition.source || "llm";
        source_url = entry.cognition.source_url || "";
    } else if (entry.summary || entry.details) {
        agent = entry.agent || "System";
        insight = entry.summary || "";
        research = entry.details || "";
        source = "llm";
        source_url = "";
    } else {
        return null;
    }

    if (!insight) return null;

    // --- Importance ---
    let importance = 0;
    if (insight.length > 300) importance++;
    if (insight.includes("Evolution")) importance++;
    if (research) importance++;
    if (source === "web") importance = Math.max(importance, 2);
    const importanceLabel = ["Low", "Medium", "High"][Math.min(importance, 2)];

    // --- Evolution split ---
    let mainInsight = insight;
    let evolution = "";
    let evolutionType = "";

    for (const [marker, type] of [
        ["--- Cross-Agent Evolution ---", "cross"],
        ["--- Self Evolution ---", "self"],
        ["--- Evolution ---", "basic"],
    ]) {
        if (insight.includes(marker)) {
            const parts = insight.split(marker);
            mainInsight = parts[0];
            evolution = parts[1] || "";
            evolutionType = type;
            break;
        }
    }

    // --- Source badge ---
    let sourceHtml = "";
    if (source === "web" && source_url) {
        const domain = source_url.replace(/^https?:\/\/(www\.)?/, "").split("/")[0];
        sourceHtml = `<a class="source-link source-badge-web" href="${source_url}" target="_blank">${domain}</a>`;
    } else if (source === "wikipedia" && source_url) {
        sourceHtml = `<a class="source-link" href="${source_url}" target="_blank">wikipedia.org</a>`;
    } else if (source === "wikipedia") {
        sourceHtml = `<span class="source-link">wikipedia</span>`;
    }

    // --- Build element ---
    const wrapper = document.createElement("div");
    wrapper.className = `cognition-entry source-${source === "wikipedia" ? "wiki" : source}`;

    wrapper.innerHTML = `
<div class="cog-header">
    <span class="agent" style="color:${AGENT_COLORS[agent] || "#fff"}">${agent}</span>
    <span class="importance importance-${Math.min(importance, 2)}">${importanceLabel}</span>
    <span class="time">${formatTimestamp(entry.timestamp)}</span>
</div>

<div class="cog-section insight">
    <div class="label" onclick="toggleSection(this)">▸ Insight</div>
    <div class="content">${mainInsight}</div>
</div>

${evolution ? `
<div class="cog-section evolution evolution-${evolutionType}">
    <div class="label">
        ${evolutionType === "cross" ? "◈ Cross-Agent Evolution"
                : evolutionType === "self" ? "↺ Self Evolution"
                    : "◉ Evolution"}
    </div>
    <div class="content">${evolution}</div>
</div>` : ""}

${research ? `
<div class="cog-section research">
    <div class="label">▸ Research ${sourceHtml}</div>
    <div class="content">${research}</div>
</div>` : ""}
    `;

    return wrapper;
}

/* =========================
   LOAD COGNITION FEED
========================= */
async function loadCognitionFeed() {
    try {
        const container = document.getElementById("cognition-feed");
        if (!container) return;

        const stateRes = await fetch("/api/cognition/all");
        const stateData = await stateRes.json();

        renderCognitionState(stateData);
        renderWebStats(stateData.web_stats || {});

        const entries = (stateData.entries || [])
            .filter(e => e && e.timestamp)
            .sort((a, b) => normalizeTimestamp(b.timestamp) - normalizeTimestamp(a.timestamp));

        // 🟢 Update the cognition status badge based on entry freshness
        updateCognitionStatus(entries);

        // Only re-render if data actually changed — compare newest timestamp
        // (count-based check was causing feed to stop when entry count stabilized)
        const newestTs = entries.length ? normalizeTimestamp(entries[0].timestamp) : 0;
        const lastRenderedTs = Number(container.dataset.lastTs || 0);
        if (newestTs === lastRenderedTs && container.querySelectorAll(".cognition-entry").length > 0) return;
        container.dataset.lastTs = String(newestTs);

        container.innerHTML = "";

        if (entries.length === 0) {
            container.innerHTML = `<div class="empty-state">Awaiting cognition cycles...</div>`;
            return;
        }

        entries.forEach((entry, index) => {
            const el = createCognitionEntry(entry);
            if (!el) return;
            el.style.opacity = String(Math.max(1 - index * 0.1, 0.2));
            el.style.transform = `scale(${1 - index * 0.01})`;
            container.appendChild(el);
        });

        while (container.children.length > 20) {
            container.removeChild(container.lastChild);
        }

        container.scrollTop = 0;

    } catch (err) {
        console.error("Cognition feed error:", err);
    }
}

/* =========================
   RENDER COGNITIVE STATE
========================= */
function renderCognitionState(data) {
    const topicsDiv = document.getElementById("top-topics");
    const synthesisDiv = document.getElementById("synthesis");
    const memoryDiv = document.getElementById("memory-context");

    if (topicsDiv) {
        topicsDiv.innerHTML = "";
        (data.top_topics || []).forEach(([topic, score]) => {
            const el = document.createElement("span");
            el.textContent = `${topic} (${score.toFixed(1)})`;
            topicsDiv.appendChild(el);
        });
        if (!data.top_topics?.length) {
            topicsDiv.innerHTML = `<span style="opacity:0.3">Learning...</span>`;
        }
    }

    if (synthesisDiv) {
        synthesisDiv.innerHTML = "";
        (data.synthesis || []).forEach(pair => {
            const el = document.createElement("div");
            el.textContent = `${pair[0]} \u21c4 ${pair[1]}`;
            synthesisDiv.appendChild(el);
        });
        if (!data.synthesis?.length) {
            synthesisDiv.innerHTML = `<div style="opacity:0.3">Forming connections...</div>`;
        }
    }

    if (memoryDiv) {
        memoryDiv.innerHTML = "";
        (data.memory || []).forEach(m => {
            const el = document.createElement("div");
            el.textContent = (m.summary || (m.insight || "")).slice(0, 90);
            memoryDiv.appendChild(el);
        });
        if (!data.memory?.length) {
            memoryDiv.innerHTML = `<div style="opacity:0.3">Building memory...</div>`;
        }
    }
}

/* =========================
   RENDER WEB STATS
========================= */
function renderWebStats(stats) {
    const totalEl = document.getElementById("ws-total");
    const successEl = document.getElementById("ws-success");
    const lastEl = document.getElementById("ws-last");
    const domainsEl = document.getElementById("ws-domains");

    if (totalEl) totalEl.textContent = stats.total_searches || "0";
    if (successEl) successEl.textContent = stats.successful_fetches || "0";
    if (lastEl) lastEl.textContent = stats.last_search || "—";

    if (domainsEl) {
        domainsEl.innerHTML = "";
        const domains = (stats.domains_visited || []).slice(-8); // last 8 domains
        domains.forEach(d => {
            const el = document.createElement("span");
            el.textContent = d;
            domainsEl.appendChild(el);
        });
    }
}

/* =========================
   BUILDER PROPOSALS
========================= */
async function loadBuilderProposals() {
    try {
        const res = await fetch(`/api/build/pending?ts=${Date.now()}`);
        const data = await res.json();

        const container = document.getElementById("builder-proposals");
        if (!container) return;

        const proposals = data?.data?.pending || [];

        if (proposals.length === 0) {
            container.innerHTML = `<div class="empty-state">No proposals queued</div>`;
            return;
        }

        container.innerHTML = "";

        proposals.forEach(p => {
            const confidence = p.confidence || 0.9;
            const pct = Math.round(confidence * 100);

            // Clean up the description — strip "Act on:" prefix
            const rawDesc = (p.description || "").replace(/^Act on:\s*/i, "").trim();
            const desc = rawDesc.length > 120 ? rawDesc.slice(0, 120) + "…" : rawDesc;

            // Clean up impact text
            const impact = (p.impact || "Potential system improvement")
                .replace(/^Here are the 2-3 most important[^:]*:\s*/i, "")
                .slice(0, 140);

            const el = document.createElement("div");
            el.className = "proposal";

            el.innerHTML = `
<div class="proposal-header">
    <div class="proposal-title">${desc}</div>
    <div class="proposal-confidence">${pct}%</div>
</div>
<div class="proposal-body">
    <div class="proposal-reason">
        <strong>Origin</strong>
        Generated from cognition loop
    </div>
    <div class="proposal-impact">
        <strong>Research Basis</strong>
        ${impact}
    </div>
</div>
<div class="proposal-actions">
    <button onclick="approveBuild('${p.id}')">&#10003; Deploy</button>
    <button onclick="rejectBuild('${p.id}')">&#10007; Reject</button>
</div>`;

            container.appendChild(el);
        });

    } catch (err) {
        console.error("Builder feed error:", err);
    }
}

/* expose toggleSection globally for onclick handlers */
window.toggleSection = toggleSection;
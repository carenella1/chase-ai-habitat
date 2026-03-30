import { getAgents } from "/static/js/adapters/agentsAdapter.js";

document.addEventListener("DOMContentLoaded", () => {
    if (!document.querySelector(".agents-page")) return;

    console.log("🧠 AGENTS SYSTEM ONLINE");

    const canvas = document.getElementById("agent-canvas");

    if (!canvas) {
        console.error("❌ Canvas missing");
        return;
    }

    const ctx = canvas.getContext("2d");

    if (!ctx) {
        console.error("❌ Context failed");
        return;
    }

    start(canvas, ctx);
});

async function start(canvas, ctx) {
    canvas.width = canvas.offsetWidth;
    canvas.height = canvas.offsetHeight;

    let agents;

    try {
        const res = await getAgents();
        agents = res.data || res;
        console.log("AGENTS:", agents);
    } catch (err) {
        console.error("❌ getAgents failed:", err);
        agents = [];
    }

    if (!agents || agents.length === 0) {
        agents = [
            { name: "Strategist" },
            { name: "Researcher" },
            { name: "Builder" }
        ];
    }

    agents = agents.map((a, i) => ({
        name: a.name,
        orbit: 100 + i * 60,
        speed: 0.001 + i * 0.0004,
        activity: Math.floor(Math.random() * 10),
        insights: Math.floor(Math.random() * 5),
        tasks: Math.floor(Math.random() * 6)
    }));

    updateUI(agents);
    renderAgentList(agents);

    let time = 0;

    function draw() {
        ctx.clearRect(0, 0, canvas.width, canvas.height);

        const cx = canvas.width / 2;
        const cy = canvas.height / 2;

        // center
        ctx.beginPath();
        ctx.arc(cx, cy, 15, 0, Math.PI * 2);
        ctx.fillStyle = "red";
        ctx.fill();

        agents.forEach((a, i) => {
            const angle = time * a.speed;

            const x = cx + Math.cos(angle) * a.orbit;
            const y = cy + Math.sin(angle) * a.orbit;

            ctx.beginPath();
            ctx.arc(x, y, 14, 0, Math.PI * 2);

            ctx.fillStyle = [
                "#00ffff",
                "#ff00ff",
                "#00ff88",
                "#ffaa00",
                "#ffffff"
            ][i % 5];

            ctx.fill();

            ctx.fillStyle = "#ffffff";
            ctx.font = "12px Arial";
            ctx.fillText(a.name, x + 10, y);
        });

        time++;
        requestAnimationFrame(draw);
    }

    draw();
}

/* =========================
   UI SYSTEM
========================= */

function updateUI(agents) {
    const population = document.getElementById("entity-count");
    if (population) population.textContent = agents.length;

    const mostActive = [...agents].sort((a, b) => b.activity - a.activity)[0];

    const mostActiveEl = document.getElementById("most-active-agent");
    if (mostActiveEl && mostActive) {
        mostActiveEl.textContent = mostActive.name;
    }

    const loopStatus = document.getElementById("loop-status");
    if (loopStatus) loopStatus.textContent = "online";

    const lastUpdate = document.getElementById("last-update");
    if (lastUpdate) lastUpdate.textContent = new Date().toLocaleTimeString();

    const entryCount = document.getElementById("entry-count");
    if (entryCount) entryCount.textContent = agents.length;
}

function renderAgentList(agents) {
    const container = document.getElementById("agent-list");
    if (!container) return;

    container.innerHTML = "";

    agents.forEach(agent => {
        const el = document.createElement("div");
        el.className = "agent-item";
        el.textContent = agent.name;

        el.onclick = () => selectAgent(agent);

        container.appendChild(el);
    });
}

function selectAgent(agent) {
    const name = document.getElementById("selected-agent-name");
    const state = document.getElementById("selected-agent-state");
    const desc = document.getElementById("selected-agent-description");

    const taskCount = document.getElementById("selected-agent-task-count");
    const insightCount = document.getElementById("selected-agent-insight-count");
    const activityCount = document.getElementById("selected-agent-activity-count");

    if (name) name.textContent = agent.name;
    if (state) {
        state.textContent = "ACTIVE";
        state.className = "agent-state-pill active";
    }

    if (desc) desc.textContent = `${agent.name} is actively processing habitat signals.`;

    if (taskCount) taskCount.textContent = agent.tasks;
    if (insightCount) insightCount.textContent = agent.insights;
    if (activityCount) activityCount.textContent = agent.activity;
}
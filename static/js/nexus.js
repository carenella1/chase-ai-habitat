/* ================================================
   NEXUS.JS — Command Interface Logic
   Chase AI Habitat · Phase UI
================================================ */

'use strict';

// ── STATE ────────────────────────────────────────
const state = {
    activeMemTab: 'facts',
    graphData: { nodes: [], edges: [] },
    agentColors: {
        Researcher: '#00f0ff',
        Explorer: '#ff66cc',
        Strategist: '#ffaa33',
        Curator: '#66ff99',
        Archivist: '#aa88ff',
        HypothesisAgent: '#ff8866',
        Builder: '#44ddff',
    },
};

// ── BOOT ─────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
    refreshAll();
    setInterval(refreshAll, 15000);
});

async function refreshAll() {
    await Promise.allSettled([
        loadIntelStatus(),
        loadSandboxActivity(),
        loadSandboxAgents(),
        loadGraphStats(),
    ]);
}

// ── SECTION 1: INTEL STATUS ──────────────────────

async function loadIntelStatus() {
    try {
        const [llm, memory, graph, scores] = await Promise.all([
            fetchJSON('/api/llm/status'),
            fetchJSON('/api/memory/stats'),
            fetchJSON('/api/graph/stats'),
            fetchJSON('/api/optimizer/scores'),
        ]);

        // Brain tile
        if (llm) {
            const modelShort = (llm.active_model || '—').replace('deepseek-r1:', 'R1:').replace(':latest', '');
            setText('it-model', modelShort);
            setText('it-thinking', llm.is_thinking_model ? '⚡ thinking mode active' : 'standard mode');
            setText('ss-model-name', modelShort);
            setDot('ss-brain', llm.status === 'ok' ? 'online' : 'error');
        }

        // Memory tile
        if (memory) {
            const total = (memory.world_facts || 0) + (memory.episodic || 0) + (memory.beliefs || 0) + (memory.entities || 0);
            setText('it-mem-total', total.toLocaleString());
            setText('it-mem-detail', `${memory.world_facts} facts · ${memory.episodic} episodic · ${memory.entities} entities`);
            setText('ss-memory-count', `${total} memories`);
            setDot('ss-memory', total > 0 ? 'online' : 'thinking');
        }

        // Graph tile
        if (graph) {
            setText('it-graph-nodes', graph.total_nodes || '0');
            setText('it-graph-edges', `${graph.total_edges || 0} edges`);
            setText('ss-graph-count', `${graph.total_nodes || 0} nodes`);
            setDot('ss-graph', graph.total_nodes > 0 ? 'online' : 'thinking');

            // Render D3 graph if data exists
            if (graph.total_nodes > 0) {
                await renderKnowledgeGraph();
            }
        }

        // Optimizer scores
        if (scores) {
            const vals = Object.values(scores).map(Number);
            const avg = vals.length ? vals.reduce((a, b) => a + b, 0) / vals.length : 0.5;
            const pct = Math.round(avg * 100);
            setText('it-opt-avg', `${pct}%`);
            setText('it-opt-detail', avg <= 0.5 ? 'awaiting cycles...' : avg > 0.7 ? 'performing well' : 'optimizing');
            renderAgentBars(scores);
        }

    } catch (e) {
        console.error('Intel load error:', e);
    }
}

function renderAgentBars(scores) {
    const container = document.getElementById('agent-bars');
    if (!container) return;

    const entries = Object.entries(scores).sort((a, b) => b[1] - a[1]);
    const allBaseline = entries.every(([, v]) => v === 0.5);

    if (allBaseline) {
        container.innerHTML = '<div class="agent-bar-loading">Awaiting cycle data — scores populate after first 5 cycles per agent.</div>';
        return;
    }

    container.innerHTML = entries.map(([name, score]) => {
        const pct = Math.round(score * 100);
        const color = state.agentColors[name] || '#00f0ff';
        const width = Math.max(2, pct);
        return `
      <div class="agent-bar-row">
        <div class="agent-bar-name">${name.toUpperCase()}</div>
        <div class="agent-bar-track">
          <div class="agent-bar-fill" style="width:${width}%; background:${color}; box-shadow: 0 0 8px ${color}55;"></div>
        </div>
        <div class="agent-bar-score" style="color:${color}">${pct}%</div>
      </div>
    `;
    }).join('');
}

// ── SECTION 2: SANDBOX ───────────────────────────

async function loadSandboxActivity() {
    try {
        const [activity, status] = await Promise.all([
            fetchJSON('/api/sandbox/activity'),
            fetchJSON('/api/sandbox/status'),
        ]);

        if (status) {
            setText('ss-trust-level', `Trust Lv${status.trust_level}`);
            setText('trust-badge', `TRUST LVL ${status.trust_level}`);
            setDot('ss-sandbox', 'online');
        }

        const feed = document.getElementById('sandbox-activity-feed');
        if (!feed) return;

        if (!activity || activity.length === 0) {
            feed.innerHTML = '<div class="sandbox-empty">No sandbox activity yet.</div>';
            return;
        }

        feed.innerHTML = [...activity].reverse().map(task => {
            const statusClass = task.result_status === 'success' ? 'type-success'
                : task.result_status === 'blocked' ? 'type-blocked'
                    : 'type-error';
            const statusLabel = task.result_status?.toUpperCase() || 'UNKNOWN';
            const time = task.submitted_at ? new Date(task.submitted_at).toLocaleTimeString() : '—';
            const output = task.result_output || task.result_status || '';

            return `
        <div class="sandbox-task">
          <div class="sandbox-task-header">
            <span class="sandbox-task-type ${statusClass}">${statusLabel}</span>
            <span class="sandbox-task-time">${time} · ${task.duration || 0}s</span>
          </div>
          <div class="sandbox-task-desc">${escHtml(task.description || task.task_type || 'execution')}</div>
          ${output ? `<div class="sandbox-task-output">${escHtml(output.substring(0, 300))}</div>` : ''}
        </div>
      `;
        }).join('');

    } catch (e) {
        console.error('Sandbox activity error:', e);
    }
}

async function loadSandboxAgents() {
    try {
        const agents = await fetchJSON('/api/sandbox/agents');
        const container = document.getElementById('sandbox-agents-list');
        if (!container) return;

        if (!agents || agents.length === 0) {
            container.innerHTML = `
        <div class="sandbox-empty">
          <div class="sandbox-empty-icon">⬡</div>
          <div>No agents generated yet.</div>
          <div class="sandbox-empty-sub">Nex will propose agents here as it builds autonomously.</div>
        </div>`;
            return;
        }

        container.innerHTML = agents.map(agent => `
      <div class="sandbox-agent-card" id="agent-card-${escAttr(agent.name)}">
        <div class="sac-header">
          <div class="sac-name">⬡ ${escHtml(agent.name)}</div>
          <div class="sac-date">${agent.created ? new Date(agent.created).toLocaleDateString() : '—'}</div>
        </div>
        <div style="font-size:11px; color:rgba(255,255,255,0.4); font-family:'Share Tech Mono',monospace;">
          ${agent.size_bytes || 0} bytes · sandbox/agents/
        </div>
        <div class="sac-actions">
          <button class="btn-approve" onclick="promoteAgent('${escAttr(agent.name)}')">▲ PROMOTE</button>
          <button class="btn-reject"  onclick="rejectAgent('${escAttr(agent.name)}')">✕ REJECT</button>
        </div>
      </div>
    `).join('');

    } catch (e) {
        console.error('Sandbox agents error:', e);
    }
}

async function runSandboxCode() {
    const input = document.getElementById('sandbox-code-input');
    const code = input?.value?.trim();
    if (!code) return;

    const btn = document.querySelector('.sandbox-run-btn');
    if (btn) { btn.textContent = '⏳ RUNNING...'; btn.disabled = true; }

    try {
        const result = await fetch('/api/sandbox/run', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ code, description: 'Manual execution via Nexus' }),
        }).then(r => r.json());

        // Reload activity feed
        await loadSandboxActivity();
        if (input) input.value = '';
    } catch (e) {
        console.error('Sandbox run error:', e);
    } finally {
        if (btn) { btn.textContent = '▶ EXECUTE IN SANDBOX'; btn.disabled = false; }
    }
}

async function promoteAgent(name) {
    // Future: POST to /api/sandbox/promote/:name
    // For now, show a confirmation message
    const card = document.getElementById(`agent-card-${name}`);
    if (card) {
        card.style.borderColor = 'rgba(0,255,200,0.5)';
        card.style.background = 'rgba(0,255,200,0.05)';
        const btn = card.querySelector('.btn-approve');
        if (btn) btn.textContent = '✓ PROMOTION QUEUED';
    }
}

async function rejectAgent(name) {
    const card = document.getElementById(`agent-card-${name}`);
    if (card) {
        card.style.opacity = '0';
        card.style.transition = 'opacity 0.4s';
        setTimeout(() => card.remove(), 400);
    }
}

// ── SECTION 3: KNOWLEDGE GRAPH ───────────────────

async function loadGraphStats() {
    // Stats are loaded in loadIntelStatus, this handles graph empty state
    const graph = await fetchJSON('/api/graph/stats').catch(() => null);
    const emptyState = document.getElementById('graph-empty');
    if (emptyState) {
        emptyState.style.display = graph?.total_nodes > 0 ? 'none' : 'flex';
    }
}

async function renderKnowledgeGraph() {
    try {
        const data = await fetchJSON('/api/graph/visualize');
        if (!data || !data.nodes || data.nodes.length === 0) return;

        const svg = document.getElementById('nexus-graph');
        if (!svg) return;

        // Clear previous
        d3.select(svg).selectAll('*').remove();

        const container = svg.parentElement;
        const W = container.clientWidth || 700;
        const H = container.clientHeight || 380;

        const svgSel = d3.select(svg)
            .attr('width', W)
            .attr('height', H);

        // Defs: glow filter
        const defs = svgSel.append('defs');
        const filter = defs.append('filter').attr('id', 'glow');
        filter.append('feGaussianBlur').attr('stdDeviation', '3').attr('result', 'coloredBlur');
        const feMerge = filter.append('feMerge');
        feMerge.append('feMergeNode').attr('in', 'coloredBlur');
        feMerge.append('feMergeNode').attr('in', 'SourceGraphic');

        const g = svgSel.append('g');

        // Zoom
        svgSel.call(d3.zoom()
            .scaleExtent([0.3, 3])
            .on('zoom', e => g.attr('transform', e.transform))
        );

        // Limit nodes for performance
        const nodes = data.nodes.slice(0, 60).map(n => ({ ...n }));
        const nodeIds = new Set(nodes.map(n => n.id));
        const links = data.edges
            .filter(e => nodeIds.has(e.source) && nodeIds.has(e.target))
            .slice(0, 120)
            .map(e => ({ ...e }));

        // Color by type
        const typeColors = {
            concept: '#00f0ff',
            technology: '#ff66cc',
            topic: '#ffaa33',
            person: '#66ff99',
        };

        const colorFor = (node) => typeColors[node.node_type] || '#00f0ff';
        const sizeFor = (node) => Math.max(4, Math.min(14, 4 + (node.mention_count || 1) * 0.8));

        // Simulation
        const sim = d3.forceSimulation(nodes)
            .force('link', d3.forceLink(links).id(d => d.id).distance(80).strength(0.4))
            .force('charge', d3.forceManyBody().strength(-120))
            .force('center', d3.forceCenter(W / 2, H / 2))
            .force('collision', d3.forceCollide(20));

        // Links
        const link = g.append('g').selectAll('line')
            .data(links).join('line')
            .attr('class', 'graph-link')
            .style('stroke', 'rgba(0,240,255,0.12)')
            .style('stroke-width', 1);

        // Link labels
        const linkLabel = g.append('g').selectAll('text')
            .data(links).join('text')
            .attr('class', 'graph-link-label')
            .text(d => d.relationship || '')
            .style('fill', 'rgba(0,240,255,0.3)')
            .style('font-size', '8px')
            .style('font-family', "'Share Tech Mono', monospace");

        // Node groups
        const node = g.append('g').selectAll('g')
            .data(nodes).join('g')
            .attr('class', 'graph-node')
            .call(d3.drag()
                .on('start', (e, d) => { if (!e.active) sim.alphaTarget(0.3).restart(); d.fx = d.x; d.fy = d.y; })
                .on('drag', (e, d) => { d.fx = e.x; d.fy = e.y; })
                .on('end', (e, d) => { if (!e.active) sim.alphaTarget(0); d.fx = null; d.fy = null; })
            );

        node.append('circle')
            .attr('r', d => sizeFor(d))
            .style('fill', d => colorFor(d) + '22')
            .style('stroke', d => colorFor(d))
            .style('stroke-width', 1.5)
            .style('filter', 'url(#glow)')
            .on('mouseover', function (e, d) {
                d3.select(this).style('fill', colorFor(d) + '55').attr('r', sizeFor(d) + 3);
            })
            .on('mouseout', function (e, d) {
                d3.select(this).style('fill', colorFor(d) + '22').attr('r', sizeFor(d));
            });

        node.append('text')
            .text(d => d.name?.length > 18 ? d.name.substring(0, 16) + '…' : d.name)
            .attr('dy', d => sizeFor(d) + 11)
            .attr('text-anchor', 'middle')
            .style('fill', 'rgba(255,255,255,0.65)')
            .style('font-size', '9px')
            .style('font-family', "'Share Tech Mono', monospace");

        sim.on('tick', () => {
            link
                .attr('x1', d => d.source.x).attr('y1', d => d.source.y)
                .attr('x2', d => d.target.x).attr('y2', d => d.target.y);
            linkLabel
                .attr('x', d => (d.source.x + d.target.x) / 2)
                .attr('y', d => (d.source.y + d.target.y) / 2);
            node.attr('transform', d => `translate(${d.x},${d.y})`);
        });

        // Hide empty state
        const emptyState = document.getElementById('graph-empty');
        if (emptyState) emptyState.style.display = 'none';

        state.graphData = data;
    } catch (e) {
        console.error('Graph render error:', e);
    }
}

async function findGraphPath() {
    const a = document.getElementById('graph-search-a')?.value?.trim();
    const b = document.getElementById('graph-search-b')?.value?.trim();
    if (!a || !b) return;

    const result = document.getElementById('graph-path-result');
    if (result) {
        result.style.display = 'block';
        result.textContent = 'Searching...';
    }

    try {
        const data = await fetchJSON(`/api/graph/path?from=${encodeURIComponent(a)}&to=${encodeURIComponent(b)}`);
        if (result) result.textContent = data?.path || 'No path found.';
    } catch (e) {
        if (result) result.textContent = 'Error querying graph.';
    }
}

// ── SECTION 4: MEMORY INSPECTOR ──────────────────

function switchMemTab(btn, tab) {
    document.querySelectorAll('.mem-tab').forEach(t => t.classList.remove('active'));
    btn.classList.add('active');
    state.activeMemTab = tab;

    const input = document.getElementById('memory-search-input')?.value?.trim();
    if (input) searchMemory();
}

async function searchMemory() {
    const query = document.getElementById('memory-search-input')?.value?.trim();
    const container = document.getElementById('memory-results');
    if (!container) return;

    if (!query) {
        container.innerHTML = '<div class="memory-empty">Enter a search query to inspect Nex\'s memory.</div>';
        return;
    }

    container.innerHTML = '<div class="memory-empty">Searching...</div>';

    try {
        const data = await fetchJSON(`/api/memory/recall?q=${encodeURIComponent(query)}`);
        const results = data?.results || '';

        if (!results || results.length < 10) {
            container.innerHTML = '<div class="memory-empty">No memories found for that query.</div>';
            return;
        }

        // Parse the multi-line result string into entries
        const lines = results.split('\n').filter(l => l.trim());
        const entries = lines.map(line => {
            let tag = 'fact', tagClass = 'tag-fact', text = line;
            if (line.startsWith('[FACT]')) { tag = 'FACT'; tagClass = 'tag-fact'; text = line.replace('[FACT]', '').trim(); }
            if (line.startsWith('[MEMORY]')) { tag = 'EPISODIC'; tagClass = 'tag-episodic'; text = line.replace('[MEMORY]', '').trim(); }
            if (line.startsWith('[BELIEF')) { tag = 'BELIEF'; tagClass = 'tag-belief'; text = line.replace(/\[BELIEF[^\]]*\]/, '').trim(); }
            if (line.startsWith('[ENTITY]')) { tag = 'ENTITY'; tagClass = 'tag-entity'; text = line.replace('[ENTITY]', '').trim(); }
            return { tag, tagClass, text };
        });

        // Filter by active tab
        const tabFilter = {
            facts: e => e.tag === 'FACT',
            episodic: e => e.tag === 'EPISODIC',
            beliefs: e => e.tag === 'BELIEF',
            entities: e => e.tag === 'ENTITY',
        };

        const filtered = state.activeMemTab === 'all' ? entries
            : entries.filter(tabFilter[state.activeMemTab] || (() => true));

        if (filtered.length === 0) {
            container.innerHTML = `<div class="memory-empty">No ${state.activeMemTab} memories match this query.</div>`;
            return;
        }

        container.innerHTML = filtered.map(e => `
      <div class="memory-entry">
        <span class="memory-entry-tag ${e.tagClass}">${e.tag}</span>
        <div>${escHtml(e.text.substring(0, 400))}</div>
      </div>
    `).join('');

    } catch (err) {
        container.innerHTML = '<div class="memory-empty">Error retrieving memories.</div>';
        console.error('Memory search error:', err);
    }
}

// Enter key on search
document.addEventListener('DOMContentLoaded', () => {
    document.getElementById('memory-search-input')?.addEventListener('keydown', e => {
        if (e.key === 'Enter') searchMemory();
    });
    document.getElementById('graph-search-b')?.addEventListener('keydown', e => {
        if (e.key === 'Enter') findGraphPath();
    });
});

// ── UTILITIES ─────────────────────────────────────

async function fetchJSON(url) {
    const r = await fetch(url);
    if (!r.ok) throw new Error(`HTTP ${r.status} for ${url}`);
    return r.json();
}

function setText(id, text) {
    const el = document.getElementById(id);
    if (el) el.textContent = text;
}

function setDot(id, state) {
    const el = document.getElementById(id);
    if (!el) return;
    el.className = `nss-dot ${state}`;
}

function escHtml(str) {
    return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;');
}

function escAttr(str) {
    return String(str).replace(/[^a-zA-Z0-9_-]/g, '_');
}
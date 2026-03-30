import { apiGet } from "/static/js/core/apiClient.js";

/* =========================
   AGENTS DATA LAYER
========================= */

export async function getAgents() {
    try {
        const res = await apiGet("/api/agents");

        console.log("AGENTS API RESPONSE:", res);

        return res?.data?.agents || [];
    }
    catch (err) {
        console.error("Agents API failed:", err);
        return [];
    }
}
import { apiGet } from "/static/js/core/apiClient.js";
import {
    normalizeBuilderResponse
} from "/static/js/core/contracts.js";

/* =========================
   HABITAT DATA ACCESS
========================= */

export async function getCognitionFeed() {
    try {
        const res = await fetch("/api/cognition/all");
        const data = await res.json();

        console.log("🧪 API RESPONSE:", data);

        return data.entries || [];
    } catch (err) {
        console.error("Adapter error:", err);
        return [];
    }
}

export async function getBuilderFeed() {
    const data = await apiGet(`/api/build/pending?ts=${Date.now()}`);
    return normalizeBuilderResponse(data);
}


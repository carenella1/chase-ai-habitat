/* =========================
   CORE DATA NORMALIZATION
========================= */

export function normalizeCognitionResponse(res) {
    // new API shape
    if (res?.data?.entries) {
        return res.data.entries;
    }

    // fallback (legacy)
    if (res?.entries) {
        return res.entries;
    }

    console.error("Invalid cognition response shape:", res);
    return [];
}

export function normalizeBuilderResponse(res) {
    // new API shape
    if (res?.data?.pending) {
        return res.data.pending;
    }

    // fallback (legacy support)
    if (res?.pending) {
        return res.pending;
    }

    console.error("Invalid builder response shape:", res);
    return [];
}
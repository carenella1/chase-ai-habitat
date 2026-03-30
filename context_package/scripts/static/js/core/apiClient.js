
/* =========================
   API CLIENT (SINGLE ENTRY POINT)
========================= */

export async function apiGet(url) {
    const res = await fetch(url);

    if (!res.ok) {
        console.error("API ERROR:", url, res.status);
        return null;
    }

    return await res.json();
}

export async function apiPost(url, body = {}) {
    const res = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body)
    });

    if (!res.ok) {
        console.error("API POST ERROR:", url, res.status);
        return null;
    }

    return await res.json();
}
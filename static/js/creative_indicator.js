// Lights up a small dot on the "Creative" nav link when Nex has made
// something new on its own that hasn't been viewed yet. Not urgent, so
// polls infrequently. Mirrors digest_indicator.js's pattern exactly.
(function () {
    const STORAGE_KEY = "nex_creative_last_viewed_at";

    function checkCreative() {
        fetch("/creative/engine-status")
            .then((r) => r.json())
            .then((status) => {
                const dot = document.getElementById("creative-nav-dot");
                if (!dot) return;
                const lastViewed = parseInt(localStorage.getItem(STORAGE_KEY) || "0", 10);
                const lastCreatedAt = status.last_nex_creation_at
                    ? Math.floor(new Date(status.last_nex_creation_at + "Z").getTime() / 1000)
                    : 0;
                const hasNew = lastCreatedAt > lastViewed;
                dot.style.display = hasNew ? "inline-block" : "none";
            })
            .catch(() => {});
    }

    // Visiting the Creative page itself marks everything as viewed.
    if (window.location.pathname === "/creative") {
        localStorage.setItem(STORAGE_KEY, String(Math.floor(Date.now() / 1000)));
    }

    document.addEventListener("DOMContentLoaded", checkCreative);
    setInterval(checkCreative, 60000);
})();

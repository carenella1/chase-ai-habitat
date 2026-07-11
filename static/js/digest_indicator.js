// Lights up a small dot on the "Digest" nav link when a new briefing exists
// that hasn't been viewed yet. Not urgent, so polls infrequently.
(function () {
    const STORAGE_KEY = "nex_digest_last_viewed_at";

    function checkDigest() {
        fetch("/api/digest/status")
            .then((r) => r.json())
            .then((status) => {
                const dot = document.getElementById("digest-nav-dot");
                if (!dot) return;
                const lastViewed = parseInt(localStorage.getItem(STORAGE_KEY) || "0", 10);
                const hasNew = status.last_digest_at > lastViewed && status.total_entries > 0;
                dot.style.display = hasNew ? "inline-block" : "none";
            })
            .catch(() => {});
    }

    // Visiting the Digest page itself marks everything as viewed.
    if (window.location.pathname === "/digest") {
        localStorage.setItem(STORAGE_KEY, String(Math.floor(Date.now() / 1000)));
    }

    document.addEventListener("DOMContentLoaded", checkDigest);
    setInterval(checkDigest, 60000);
})();

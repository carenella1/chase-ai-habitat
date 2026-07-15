// Persistent Nex avatar, bottom-left on every page. Exposes window.NexFace.setState()
// so chat.js can drive it off the same idle/listening/thinking/speaking states as
// Orb Mode. Clicking it opens Orb Mode — on the chat page it just clicks the existing
// #mode-toggle button; on any other page it navigates to the chat page first.
(function () {
    document.addEventListener("DOMContentLoaded", () => {
        const widget = document.getElementById("nex-face-widget");
        if (!widget) return;

        window.NexFace = {
            setState(state) {
                widget.dataset.state = state || "idle";
            }
        };

        function openVoiceMode() {
            const modeBtn = document.getElementById("mode-toggle");
            if (modeBtn) {
                modeBtn.click();
            } else {
                window.location.href = "/chat?voice=1";
            }
        }

        widget.addEventListener("click", openVoiceMode);
        widget.addEventListener("keydown", (e) => {
            if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                openVoiceMode();
            }
        });
    });
})();

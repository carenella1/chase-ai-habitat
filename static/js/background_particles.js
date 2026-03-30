const container = document.getElementById("particle-background");

if (!container) {
    console.log("⛔ particles skipped (no container)");
} else {

    const canvas = document.createElement("canvas");
    canvas.id = "particles";
    container.appendChild(canvas);

    const ctx = canvas.getContext("2d");

    function resizeCanvas() {
        canvas.width = window.innerWidth;
        canvas.height = window.innerHeight;
    }

    resizeCanvas();
    window.addEventListener("resize", resizeCanvas);

    let particles = [];

    const BASE_SPEED = 0.4;
    let speedMultiplier = 1;

    for (let i = 0; i < 80; i++) {
        particles.push({
            x: Math.random() * canvas.width,
            y: Math.random() * canvas.height,
            vx: (Math.random() - 0.5) * BASE_SPEED,
            vy: (Math.random() - 0.5) * BASE_SPEED
        });
    }

    window.setSystemState = function (state) {
        speedMultiplier = state === "active" ? 3 :
                          state === "thinking" ? 2 : 1;
    };

    window.particleBurst = function () {
        particles.forEach(p => {
            p.vx += (Math.random() - 0.5) * 2;
            p.vy += (Math.random() - 0.5) * 2;
        });
    };

    function animate() {
        ctx.clearRect(0, 0, canvas.width, canvas.height);

        ctx.fillStyle = "#00eaff";

        particles.forEach(p => {
            p.x += p.vx * speedMultiplier;
            p.y += p.vy * speedMultiplier;

            if (p.x < 0 || p.x > canvas.width) p.vx *= -1;
            if (p.y < 0 || p.y > canvas.height) p.vy *= -1;

            ctx.beginPath();
            ctx.arc(p.x, p.y, 2, 0, Math.PI * 2);
            ctx.fill();
        });

        requestAnimationFrame(animate);
    }

    animate();
}
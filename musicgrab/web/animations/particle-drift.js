import { createAnimation, themeColor, INTENSITY_SCALE, rand } from "./_base.js";

export default function particleDrift() {
  let particles = [];
  let mouse = { x: -9999, y: -9999 };

  function onMove(e) {
    mouse.x = e.clientX;
    mouse.y = e.clientY;
  }

  function setup(ctx, canvas, intensity) {
    const w = canvas.width / window.devicePixelRatio;
    const h = canvas.height / window.devicePixelRatio;
    const count = Math.floor(70 * INTENSITY_SCALE[intensity]);
    particles = Array.from({ length: count }, () => ({
      x: rand(0, w),
      y: rand(0, h),
      vx: rand(-0.15, 0.15),
      vy: rand(-0.15, 0.15),
      r: rand(1, 2.5),
    }));
    window.removeEventListener("mousemove", onMove);
    window.addEventListener("mousemove", onMove);
  }

  function draw(ctx, canvas) {
    const w = canvas.width / window.devicePixelRatio;
    const h = canvas.height / window.devicePixelRatio;
    ctx.clearRect(0, 0, w, h);
    const color = themeColor("--accent-2", "#8af");
    particles.forEach((p) => {
      const dx = p.x - mouse.x;
      const dy = p.y - mouse.y;
      const dist = Math.hypot(dx, dy);
      if (dist < 100) {
        p.vx += (dx / dist) * 0.01;
        p.vy += (dy / dist) * 0.01;
      }
      p.x += p.vx;
      p.y += p.vy;
      p.vx *= 0.99;
      p.vy *= 0.99;
      if (p.x < 0 || p.x > w) p.vx *= -1;
      if (p.y < 0 || p.y > h) p.vy *= -1;
      ctx.beginPath();
      ctx.fillStyle = color;
      ctx.globalAlpha = 0.5;
      ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
      ctx.fill();
    });
    ctx.globalAlpha = 1;
  }

  return createAnimation({ setup, draw, teardown: () => window.removeEventListener("mousemove", onMove) });
}

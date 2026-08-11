import { createAnimation, themeColor, INTENSITY_SCALE, rand } from "./_base.js";

export default function fireflies() {
  let flies = [];

  function setup(ctx, canvas, intensity) {
    const w = canvas.width / window.devicePixelRatio;
    const h = canvas.height / window.devicePixelRatio;
    const count = Math.floor(35 * INTENSITY_SCALE[intensity]);
    flies = Array.from({ length: count }, () => ({
      x: rand(0, w),
      y: rand(0, h),
      vx: rand(-0.25, 0.25),
      vy: rand(-0.25, 0.25),
      r: rand(1.5, 3),
      phase: rand(0, Math.PI * 2),
      pulseSpeed: rand(0.02, 0.05),
    }));
  }

  function draw(ctx, canvas) {
    const w = canvas.width / window.devicePixelRatio;
    const h = canvas.height / window.devicePixelRatio;
    ctx.clearRect(0, 0, w, h);
    const accent = themeColor("--accent", "#ff0");
    flies.forEach((f) => {
      f.x += f.vx;
      f.y += f.vy;
      f.phase += f.pulseSpeed;
      if (f.x < 0 || f.x > w) f.vx *= -1;
      if (f.y < 0 || f.y > h) f.vy *= -1;

      const glow = (Math.sin(f.phase) + 1) / 2;
      const grad = ctx.createRadialGradient(f.x, f.y, 0, f.x, f.y, f.r * 6);
      grad.addColorStop(0, accent);
      grad.addColorStop(1, "transparent");
      ctx.globalAlpha = 0.15 + glow * 0.5;
      ctx.fillStyle = grad;
      ctx.beginPath();
      ctx.arc(f.x, f.y, f.r * 6, 0, Math.PI * 2);
      ctx.fill();
    });
    ctx.globalAlpha = 1;
  }

  return createAnimation({ setup, draw });
}

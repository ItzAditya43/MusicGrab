import { createAnimation, themeColor, INTENSITY_SCALE, rand } from "./_base.js";

export default function bokehLights() {
  let circles = [];

  function setup(ctx, canvas, intensity) {
    const w = canvas.width / window.devicePixelRatio;
    const h = canvas.height / window.devicePixelRatio;
    const count = Math.floor(18 * INTENSITY_SCALE[intensity]);
    circles = Array.from({ length: Math.max(6, count) }, () => ({
      x: rand(0, w),
      y: rand(0, h),
      r: rand(30, 90),
      vx: rand(-0.08, 0.08),
      vy: rand(-0.08, 0.08),
      alpha: rand(0.06, 0.18),
      useAccent2: Math.random() > 0.5,
    }));
  }

  function draw(ctx, canvas) {
    const w = canvas.width / window.devicePixelRatio;
    const h = canvas.height / window.devicePixelRatio;
    ctx.clearRect(0, 0, w, h);
    const accent = themeColor("--accent", "#0af");
    const accent2 = themeColor("--accent-2", "#0fa");

    circles.forEach((c) => {
      c.x += c.vx;
      c.y += c.vy;
      if (c.x < -c.r) c.x = w + c.r;
      if (c.x > w + c.r) c.x = -c.r;
      if (c.y < -c.r) c.y = h + c.r;
      if (c.y > h + c.r) c.y = -c.r;

      const grad = ctx.createRadialGradient(c.x, c.y, 0, c.x, c.y, c.r);
      grad.addColorStop(0, c.useAccent2 ? accent2 : accent);
      grad.addColorStop(1, "transparent");
      ctx.globalAlpha = c.alpha;
      ctx.fillStyle = grad;
      ctx.beginPath();
      ctx.arc(c.x, c.y, c.r, 0, Math.PI * 2);
      ctx.fill();
    });
    ctx.globalAlpha = 1;
  }

  return createAnimation({ setup, draw });
}

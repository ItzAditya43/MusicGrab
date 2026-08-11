import { createAnimation, themeColor, INTENSITY_SCALE, rand } from "./_base.js";

export default function starfield() {
  let stars = [];

  function setup(ctx, canvas, intensity) {
    const w = canvas.width / window.devicePixelRatio;
    const h = canvas.height / window.devicePixelRatio;
    const count = Math.floor(140 * INTENSITY_SCALE[intensity]);
    stars = Array.from({ length: count }, () => ({
      x: rand(0, w),
      y: rand(0, h),
      r: rand(0.4, 1.8),
      twinkleSpeed: rand(0.01, 0.05),
      phase: rand(0, Math.PI * 2),
      drift: rand(0.02, 0.12),
    }));
  }

  function draw(ctx, canvas) {
    const w = canvas.width / window.devicePixelRatio;
    const h = canvas.height / window.devicePixelRatio;
    ctx.clearRect(0, 0, w, h);
    const color = themeColor("--text", "#fff");
    stars.forEach((s) => {
      s.phase += s.twinkleSpeed;
      const alpha = 0.35 + Math.sin(s.phase) * 0.35 + 0.3;
      ctx.beginPath();
      ctx.fillStyle = color;
      ctx.globalAlpha = Math.max(0.1, Math.min(1, alpha));
      ctx.arc(s.x, s.y, s.r, 0, Math.PI * 2);
      ctx.fill();
      s.x -= s.drift;
      if (s.x < -2) s.x = w + 2;
    });
    ctx.globalAlpha = 1;
  }

  return createAnimation({ setup, draw });
}

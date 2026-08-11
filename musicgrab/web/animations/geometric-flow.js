import { createAnimation, themeColor, INTENSITY_SCALE, rand } from "./_base.js";

export default function geometricFlow() {
  let shapes = [];

  function setup(ctx, canvas, intensity) {
    const w = canvas.width / window.devicePixelRatio;
    const h = canvas.height / window.devicePixelRatio;
    const count = Math.floor(10 * INTENSITY_SCALE[intensity]);
    shapes = Array.from({ length: Math.max(4, count) }, () => ({
      x: rand(0, w),
      y: rand(0, h),
      size: rand(40, 140),
      sides: 3 + Math.floor(rand(0, 3)),
      rotation: rand(0, Math.PI * 2),
      rotSpeed: rand(-0.004, 0.004),
      vx: rand(-0.1, 0.1),
      vy: rand(-0.1, 0.1),
      useAccent2: Math.random() > 0.5,
    }));
  }

  function drawPolygon(ctx, x, y, size, sides, rotation) {
    ctx.beginPath();
    for (let i = 0; i <= sides; i++) {
      const angle = rotation + (i / sides) * Math.PI * 2;
      const px = x + Math.cos(angle) * size;
      const py = y + Math.sin(angle) * size;
      if (i === 0) ctx.moveTo(px, py);
      else ctx.lineTo(px, py);
    }
    ctx.closePath();
  }

  function draw(ctx, canvas) {
    const w = canvas.width / window.devicePixelRatio;
    const h = canvas.height / window.devicePixelRatio;
    ctx.clearRect(0, 0, w, h);
    const accent = themeColor("--accent", "#0af");
    const accent2 = themeColor("--accent-2", "#0fa");
    shapes.forEach((s) => {
      s.rotation += s.rotSpeed;
      s.x += s.vx;
      s.y += s.vy;
      if (s.x < -s.size) s.x = w + s.size;
      if (s.x > w + s.size) s.x = -s.size;
      if (s.y < -s.size) s.y = h + s.size;
      if (s.y > h + s.size) s.y = -s.size;

      ctx.strokeStyle = s.useAccent2 ? accent2 : accent;
      ctx.globalAlpha = 0.18;
      ctx.lineWidth = 1.2;
      drawPolygon(ctx, s.x, s.y, s.size, s.sides, s.rotation);
      ctx.stroke();
    });
    ctx.globalAlpha = 1;
  }

  return createAnimation({ setup, draw });
}

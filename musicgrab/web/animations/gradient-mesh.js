import { createAnimation, themeColor, INTENSITY_SCALE, rand } from "./_base.js";

export default function gradientMesh() {
  let blobs = [];
  let speed = 1;

  function setup(ctx, canvas, intensity) {
    const w = canvas.width / window.devicePixelRatio;
    const h = canvas.height / window.devicePixelRatio;
    speed = INTENSITY_SCALE[intensity];
    blobs = [
      { cx: w * 0.25, cy: h * 0.3, r: Math.max(w, h) * 0.35, useAccent2: false, phase: 0, sx: rand(0.1, 0.2), sy: rand(0.1, 0.2) },
      { cx: w * 0.75, cy: h * 0.35, r: Math.max(w, h) * 0.3, useAccent2: true, phase: 2, sx: rand(0.1, 0.2), sy: rand(0.1, 0.2) },
      { cx: w * 0.5, cy: h * 0.75, r: Math.max(w, h) * 0.32, useAccent2: false, phase: 4, sx: rand(0.1, 0.2), sy: rand(0.1, 0.2) },
    ];
  }

  function draw(ctx, canvas) {
    const w = canvas.width / window.devicePixelRatio;
    const h = canvas.height / window.devicePixelRatio;
    ctx.clearRect(0, 0, w, h);
    const accent = themeColor("--accent", "#0af");
    const accent2 = themeColor("--accent-2", "#0fa");

    ctx.filter = "blur(60px)";
    blobs.forEach((b) => {
      b.phase += 0.003 * speed;
      const x = b.cx + Math.sin(b.phase) * w * b.sx;
      const y = b.cy + Math.cos(b.phase * 1.3) * h * b.sy;
      const grad = ctx.createRadialGradient(x, y, 0, x, y, b.r);
      grad.addColorStop(0, b.useAccent2 ? accent2 : accent);
      grad.addColorStop(1, "transparent");
      ctx.globalAlpha = 0.35;
      ctx.fillStyle = grad;
      ctx.beginPath();
      ctx.arc(x, y, b.r, 0, Math.PI * 2);
      ctx.fill();
    });
    ctx.filter = "none";
    ctx.globalAlpha = 1;
  }

  return createAnimation({ setup, draw });
}

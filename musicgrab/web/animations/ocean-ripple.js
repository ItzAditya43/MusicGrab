import { createAnimation, themeColor, INTENSITY_SCALE, rand } from "./_base.js";

export default function oceanRipple() {
  let ripples = [];
  let spawnTimer = 0;
  let spawnEvery = 60;

  function setup(ctx, canvas, intensity) {
    ripples = [];
    spawnEvery = Math.max(15, Math.floor(70 / INTENSITY_SCALE[intensity]));
  }

  function draw(ctx, canvas) {
    const w = canvas.width / window.devicePixelRatio;
    const h = canvas.height / window.devicePixelRatio;
    ctx.clearRect(0, 0, w, h);
    const accent = themeColor("--accent-2", "#0af");

    spawnTimer++;
    if (spawnTimer >= spawnEvery) {
      spawnTimer = 0;
      ripples.push({ x: rand(0, w), y: rand(0, h), r: 0, maxR: rand(80, 220) });
    }

    ripples = ripples.filter((r) => r.r < r.maxR);
    ripples.forEach((r) => {
      r.r += 1.2;
      const alpha = Math.max(0, 1 - r.r / r.maxR) * 0.35;
      ctx.strokeStyle = accent;
      ctx.globalAlpha = alpha;
      ctx.lineWidth = 1.5;
      ctx.beginPath();
      ctx.arc(r.x, r.y, r.r, 0, Math.PI * 2);
      ctx.stroke();
    });
    ctx.globalAlpha = 1;
  }

  return createAnimation({ setup, draw });
}

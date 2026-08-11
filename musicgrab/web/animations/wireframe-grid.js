import { createAnimation, themeColor, INTENSITY_SCALE } from "./_base.js";

export default function wireframeGrid() {
  let offset = 0;
  let speed = 1;

  function setup(ctx, canvas, intensity) {
    speed = INTENSITY_SCALE[intensity];
  }

  function draw(ctx, canvas) {
    const w = canvas.width / window.devicePixelRatio;
    const h = canvas.height / window.devicePixelRatio;
    ctx.clearRect(0, 0, w, h);
    const accent = themeColor("--accent-2", "#0af");
    const horizon = h * 0.55;
    offset = (offset + 0.6 * speed) % 40;

    ctx.strokeStyle = accent;
    ctx.globalAlpha = 0.3;
    ctx.lineWidth = 1;

    // Horizontal lines receding toward the horizon.
    for (let i = 0; i < 22; i++) {
      const y = horizon + (i * i) * 1.1 + offset;
      if (y > h) continue;
      ctx.globalAlpha = 0.3 * (1 - y / h);
      ctx.beginPath();
      ctx.moveTo(0, y);
      ctx.lineTo(w, y);
      ctx.stroke();
    }

    // Vertical perspective lines converging toward a center vanishing point.
    const vpX = w / 2;
    ctx.globalAlpha = 0.25;
    for (let i = -12; i <= 12; i++) {
      const xBottom = vpX + i * (w / 16);
      ctx.beginPath();
      ctx.moveTo(vpX, horizon);
      ctx.lineTo(xBottom, h);
      ctx.stroke();
    }
    ctx.globalAlpha = 1;
  }

  return createAnimation({ setup, draw });
}

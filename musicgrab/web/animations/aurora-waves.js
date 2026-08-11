import { createAnimation, themeColor, INTENSITY_SCALE } from "./_base.js";

export default function auroraWaves() {
  let t = 0;
  let speed = 1;

  function setup(ctx, canvas, intensity) {
    speed = INTENSITY_SCALE[intensity];
  }

  function draw(ctx, canvas) {
    const w = canvas.width / window.devicePixelRatio;
    const h = canvas.height / window.devicePixelRatio;
    ctx.clearRect(0, 0, w, h);
    t += 0.006 * speed;

    const accent = themeColor("--accent", "#0af");
    const accent2 = themeColor("--accent-2", "#0fa");
    const bands = [
      { color: accent, amp: h * 0.12, freq: 1.3, yBase: h * 0.35, offset: 0 },
      { color: accent2, amp: h * 0.1, freq: 1.7, yBase: h * 0.5, offset: 2 },
      { color: accent, amp: h * 0.08, freq: 2.1, yBase: h * 0.62, offset: 4 },
    ];

    bands.forEach((band) => {
      const grad = ctx.createLinearGradient(0, band.yBase - band.amp, 0, band.yBase + band.amp);
      grad.addColorStop(0, "transparent");
      grad.addColorStop(0.5, band.color);
      grad.addColorStop(1, "transparent");
      ctx.globalAlpha = 0.18;
      ctx.fillStyle = grad;
      ctx.beginPath();
      ctx.moveTo(0, band.yBase);
      for (let x = 0; x <= w; x += 20) {
        const y = band.yBase + Math.sin(x * 0.004 * band.freq + t + band.offset) * band.amp;
        ctx.lineTo(x, y);
      }
      ctx.lineTo(w, h);
      ctx.lineTo(0, h);
      ctx.closePath();
      ctx.fill();
    });
    ctx.globalAlpha = 1;
  }

  return createAnimation({ setup, draw });
}

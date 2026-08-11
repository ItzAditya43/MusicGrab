import { createAnimation, themeColor, INTENSITY_SCALE, rand } from "./_base.js";

export default function rainfall() {
  let drops = [];

  function setup(ctx, canvas, intensity) {
    const w = canvas.width / window.devicePixelRatio;
    const h = canvas.height / window.devicePixelRatio;
    const count = Math.floor(160 * INTENSITY_SCALE[intensity]);
    drops = Array.from({ length: count }, () => ({
      x: rand(0, w),
      y: rand(0, h),
      len: rand(10, 26),
      speed: rand(6, 16),
      depth: rand(0.3, 1),
    }));
  }

  function draw(ctx, canvas) {
    const w = canvas.width / window.devicePixelRatio;
    const h = canvas.height / window.devicePixelRatio;
    ctx.clearRect(0, 0, w, h);
    const accent = themeColor("--accent-2", "#8fd");
    drops.forEach((d) => {
      ctx.strokeStyle = accent;
      ctx.globalAlpha = 0.15 + d.depth * 0.35;
      ctx.lineWidth = d.depth;
      ctx.beginPath();
      ctx.moveTo(d.x, d.y);
      ctx.lineTo(d.x - d.depth * 2, d.y + d.len);
      ctx.stroke();
      d.y += d.speed * d.depth;
      d.x -= d.depth * 0.6;
      if (d.y > h) {
        d.y = -d.len;
        d.x = rand(0, w);
      }
    });
    ctx.globalAlpha = 1;
  }

  return createAnimation({ setup, draw });
}

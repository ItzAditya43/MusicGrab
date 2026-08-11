import { createAnimation, themeColor, INTENSITY_SCALE, rand } from "./_base.js";

export default function snowfall() {
  let flakes = [];

  function setup(ctx, canvas, intensity) {
    const w = canvas.width / window.devicePixelRatio;
    const h = canvas.height / window.devicePixelRatio;
    const count = Math.floor(90 * INTENSITY_SCALE[intensity]);
    flakes = Array.from({ length: count }, () => ({
      x: rand(0, w),
      y: rand(0, h),
      r: rand(1, 3.5),
      speed: rand(0.4, 1.6),
      sway: rand(0.3, 1.2),
      phase: rand(0, Math.PI * 2),
    }));
  }

  function draw(ctx, canvas) {
    const w = canvas.width / window.devicePixelRatio;
    const h = canvas.height / window.devicePixelRatio;
    ctx.clearRect(0, 0, w, h);
    const color = themeColor("--text", "#fff");
    flakes.forEach((f) => {
      ctx.beginPath();
      ctx.fillStyle = color;
      ctx.globalAlpha = 0.25 + f.r / 5;
      ctx.arc(f.x + Math.sin(f.phase) * f.sway * 4, f.y, f.r, 0, Math.PI * 2);
      ctx.fill();
      f.y += f.speed;
      f.phase += 0.01;
      if (f.y > h + 5) {
        f.y = -5;
        f.x = rand(0, w);
      }
    });
    ctx.globalAlpha = 1;
  }

  return createAnimation({ setup, draw });
}

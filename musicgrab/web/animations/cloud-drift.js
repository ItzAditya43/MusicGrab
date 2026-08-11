import { createAnimation, themeColor, INTENSITY_SCALE, rand } from "./_base.js";

export default function cloudDrift() {
  let clouds = [];

  function setup(ctx, canvas, intensity) {
    const w = canvas.width / window.devicePixelRatio;
    const h = canvas.height / window.devicePixelRatio;
    const count = Math.floor(6 * INTENSITY_SCALE[intensity]);
    clouds = Array.from({ length: Math.max(3, count) }, () => ({
      x: rand(-200, w),
      y: rand(0, h),
      w: rand(200, 420),
      h: rand(60, 120),
      speed: rand(0.06, 0.18),
      alpha: rand(0.05, 0.14),
    }));
  }

  function draw(ctx, canvas) {
    const w = canvas.width / window.devicePixelRatio;
    const h = canvas.height / window.devicePixelRatio;
    ctx.clearRect(0, 0, w, h);
    const color = themeColor("--text", "#fff");
    ctx.filter = "blur(30px)";
    clouds.forEach((c) => {
      c.x += c.speed;
      if (c.x > w + c.w) c.x = -c.w;
      const grad = ctx.createRadialGradient(c.x, c.y, 0, c.x, c.y, c.w / 2);
      grad.addColorStop(0, color);
      grad.addColorStop(1, "transparent");
      ctx.globalAlpha = c.alpha;
      ctx.fillStyle = grad;
      ctx.beginPath();
      ctx.ellipse(c.x, c.y, c.w / 2, c.h / 2, 0, 0, Math.PI * 2);
      ctx.fill();
    });
    ctx.filter = "none";
    ctx.globalAlpha = 1;
  }

  return createAnimation({ setup, draw });
}

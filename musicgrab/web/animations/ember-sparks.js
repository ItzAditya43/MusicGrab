import { createAnimation, themeColor, INTENSITY_SCALE, rand } from "./_base.js";

export default function emberSparks() {
  let embers = [];

  function spawn(w, h) {
    return { x: rand(0, w), y: h + rand(0, 30), vy: rand(0.6, 1.8), vx: rand(-0.3, 0.3), r: rand(1, 2.5), life: 1, decay: rand(0.003, 0.008) };
  }

  function setup(ctx, canvas, intensity) {
    const w = canvas.width / window.devicePixelRatio;
    const h = canvas.height / window.devicePixelRatio;
    const count = Math.floor(45 * INTENSITY_SCALE[intensity]);
    embers = Array.from({ length: count }, () => ({ ...spawn(w, h), y: rand(0, h) }));
  }

  function draw(ctx, canvas) {
    const w = canvas.width / window.devicePixelRatio;
    const h = canvas.height / window.devicePixelRatio;
    ctx.clearRect(0, 0, w, h);
    const accent = themeColor("--accent", "#f80");
    embers.forEach((e, i) => {
      e.y -= e.vy;
      e.x += e.vx + Math.sin(e.y * 0.05) * 0.2;
      e.life -= e.decay;
      if (e.life <= 0 || e.y < -10) {
        embers[i] = spawn(w, h);
        return;
      }
      const grad = ctx.createRadialGradient(e.x, e.y, 0, e.x, e.y, e.r * 4);
      grad.addColorStop(0, accent);
      grad.addColorStop(1, "transparent");
      ctx.globalAlpha = e.life * 0.7;
      ctx.fillStyle = grad;
      ctx.beginPath();
      ctx.arc(e.x, e.y, e.r * 4, 0, Math.PI * 2);
      ctx.fill();
    });
    ctx.globalAlpha = 1;
  }

  return createAnimation({ setup, draw });
}

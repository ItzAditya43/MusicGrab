import { createAnimation, themeColor, INTENSITY_SCALE, rand } from "./_base.js";

const CHARS = "アイウエオカキクケコサシスセソタチツテト0123456789";

export default function digitalRain() {
  let columns = [];
  let fontSize = 16;

  function setup(ctx, canvas, intensity) {
    fontSize = 15;
    const cols = Math.floor(canvas.width / (window.devicePixelRatio * fontSize) * INTENSITY_SCALE[intensity]);
    columns = Array.from({ length: Math.max(1, cols) }, () => ({
      y: rand(-50, 0),
      speed: rand(4, 12),
    }));
    ctx.fillStyle = themeColor("--bg", "#000");
    ctx.fillRect(0, 0, canvas.width, canvas.height);
  }

  function draw(ctx, canvas) {
    const w = canvas.width / window.devicePixelRatio;
    const h = canvas.height / window.devicePixelRatio;
    ctx.fillStyle = "rgba(0,0,0,0.08)";
    ctx.globalCompositeOperation = "source-over";
    ctx.fillStyle = themeColor("--bg", "#000") + "";
    ctx.save();
    ctx.globalAlpha = 0.12;
    ctx.fillRect(0, 0, w, h);
    ctx.restore();

    const accent = themeColor("--accent", "#0f0");
    ctx.fillStyle = accent;
    ctx.font = `${fontSize}px monospace`;
    columns.forEach((col, i) => {
      const x = i * fontSize;
      const char = CHARS[Math.floor(Math.random() * CHARS.length)];
      ctx.fillText(char, x, col.y);
      col.y += col.speed;
      if (col.y > h + fontSize) col.y = rand(-100, 0);
    });
  }

  return createAnimation({ setup, draw });
}

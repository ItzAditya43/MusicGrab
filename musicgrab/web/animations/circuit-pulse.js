import { createAnimation, themeColor, INTENSITY_SCALE, rand } from "./_base.js";

export default function circuitPulse() {
  let nodes = [];
  let edges = [];
  let pulses = [];

  function setup(ctx, canvas, intensity) {
    const w = canvas.width / window.devicePixelRatio;
    const h = canvas.height / window.devicePixelRatio;
    const cols = 8;
    const rows = 5;
    nodes = [];
    for (let i = 0; i < cols; i++) {
      for (let j = 0; j < rows; j++) {
        nodes.push({
          x: (i / (cols - 1)) * w + rand(-20, 20),
          y: (j / (rows - 1)) * h + rand(-20, 20),
        });
      }
    }
    edges = [];
    nodes.forEach((n, i) => {
      const candidates = nodes
        .map((m, j) => ({ j, d: Math.hypot(n.x - m.x, n.y - m.y) }))
        .filter((c) => c.j !== i)
        .sort((a, b) => a.d - b.d)
        .slice(0, 2);
      candidates.forEach((c) => edges.push([i, c.j]));
    });
    const pulseCount = Math.floor(6 * INTENSITY_SCALE[intensity]);
    pulses = Array.from({ length: Math.max(2, pulseCount) }, () => spawnPulse());
  }

  function spawnPulse() {
    const edge = edges[Math.floor(Math.random() * edges.length)];
    return { edge, t: 0, speed: rand(0.006, 0.015) };
  }

  function draw(ctx, canvas) {
    const w = canvas.width / window.devicePixelRatio;
    const h = canvas.height / window.devicePixelRatio;
    ctx.clearRect(0, 0, w, h);
    const border = themeColor("--border", "#333");
    const accent = themeColor("--accent", "#0af");

    ctx.strokeStyle = border;
    ctx.globalAlpha = 0.5;
    ctx.lineWidth = 1;
    edges.forEach(([a, b]) => {
      ctx.beginPath();
      ctx.moveTo(nodes[a].x, nodes[a].y);
      ctx.lineTo(nodes[b].x, nodes[b].y);
      ctx.stroke();
    });

    ctx.fillStyle = accent;
    ctx.globalAlpha = 0.6;
    nodes.forEach((n) => {
      ctx.beginPath();
      ctx.arc(n.x, n.y, 1.5, 0, Math.PI * 2);
      ctx.fill();
    });

    pulses.forEach((p) => {
      if (!edges.length) return;
      const [a, b] = p.edge;
      const na = nodes[a];
      const nb = nodes[b];
      const x = na.x + (nb.x - na.x) * p.t;
      const y = na.y + (nb.y - na.y) * p.t;
      const grad = ctx.createRadialGradient(x, y, 0, x, y, 8);
      grad.addColorStop(0, accent);
      grad.addColorStop(1, "transparent");
      ctx.globalAlpha = 0.9;
      ctx.fillStyle = grad;
      ctx.beginPath();
      ctx.arc(x, y, 8, 0, Math.PI * 2);
      ctx.fill();
      p.t += p.speed;
      if (p.t >= 1) Object.assign(p, spawnPulse());
    });
    ctx.globalAlpha = 1;
  }

  return createAnimation({ setup, draw });
}

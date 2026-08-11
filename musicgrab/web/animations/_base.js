// Shared scaffolding for every animation module: canvas sizing, an
// animation loop gated on `running`, and theme-color lookup. Each concrete
// animation supplies `setup()` (build state, called on init/resize/intensity
// change) and `draw()` (render one frame); this wrapper handles the rest of
// the { init, start, stop, setIntensity, destroy } contract.
export function createAnimation({ setup, draw, teardown }) {
  let canvas = null;
  let ctx = null;
  let raf = null;
  let running = false;
  let intensity = "medium";

  function resize() {
    if (!canvas) return;
    canvas.width = window.innerWidth * window.devicePixelRatio;
    canvas.height = window.innerHeight * window.devicePixelRatio;
    canvas.style.width = "100%";
    canvas.style.height = "100%";
    ctx.setTransform(window.devicePixelRatio, 0, 0, window.devicePixelRatio, 0, 0);
    setup(ctx, canvas, intensity);
  }

  function frame() {
    if (!running) return;
    draw(ctx, canvas, intensity);
    raf = requestAnimationFrame(frame);
  }

  return {
    init(c) {
      canvas = c;
      ctx = canvas.getContext("2d");
      window.addEventListener("resize", resize);
      resize();
    },
    start() {
      if (running) return;
      running = true;
      frame();
    },
    stop() {
      running = false;
      if (raf) cancelAnimationFrame(raf);
      raf = null;
    },
    setIntensity(level) {
      intensity = level;
      setup(ctx, canvas, intensity);
    },
    destroy() {
      running = false;
      if (raf) cancelAnimationFrame(raf);
      window.removeEventListener("resize", resize);
      if (teardown) teardown();
      if (ctx && canvas) ctx.clearRect(0, 0, canvas.width, canvas.height);
      canvas = null;
      ctx = null;
    },
  };
}

export function themeColor(varName, fallback) {
  const v = getComputedStyle(document.documentElement).getPropertyValue(varName).trim();
  return v || fallback;
}

export const INTENSITY_SCALE = { low: 0.5, medium: 1, high: 1.8 };

export function rand(min, max) {
  return min + Math.random() * (max - min);
}

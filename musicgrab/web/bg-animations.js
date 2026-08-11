export const ANIMATIONS = [
  { id: "none", name: "None" },
  { id: "digital-rain", name: "Digital Rain", module: "/animations/digital-rain.js" },
  { id: "rainfall", name: "Rainfall", module: "/animations/rainfall.js" },
  { id: "snowfall", name: "Snowfall", module: "/animations/snowfall.js" },
  { id: "starfield", name: "Starfield", module: "/animations/starfield.js" },
  { id: "aurora-waves", name: "Aurora Waves", module: "/animations/aurora-waves.js" },
  { id: "particle-drift", name: "Particle Drift", module: "/animations/particle-drift.js" },
  { id: "geometric-flow", name: "Geometric Flow", module: "/animations/geometric-flow.js" },
  { id: "fireflies", name: "Fireflies", module: "/animations/fireflies.js" },
  { id: "ocean-ripple", name: "Ocean Ripple", module: "/animations/ocean-ripple.js" },
  { id: "circuit-pulse", name: "Circuit Pulse", module: "/animations/circuit-pulse.js" },
  { id: "gradient-mesh", name: "Gradient Mesh", module: "/animations/gradient-mesh.js" },
  { id: "bokeh-lights", name: "Bokeh Lights", module: "/animations/bokeh-lights.js" },
  { id: "ember-sparks", name: "Ember Sparks", module: "/animations/ember-sparks.js" },
  { id: "wireframe-grid", name: "Wireframe Grid", module: "/animations/wireframe-grid.js" },
  { id: "cloud-drift", name: "Cloud Drift", module: "/animations/cloud-drift.js" },
];

const ANIM_KEY = "musicgrab.animation";
const INTENSITY_KEY = "musicgrab.animationIntensity";
const ENABLED_KEY = "musicgrab.animationsEnabled";

const prefersReducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

class AnimationManager {
  constructor() {
    this.canvas = null;
    this.instance = null;
    this.activeId = "none";
    this.intensity = localStorage.getItem(INTENSITY_KEY) || "medium";
    this.enabled = this._loadEnabled();
    this._visHandler = () => this._onVisibility();
    document.addEventListener("visibilitychange", this._visHandler);
    window.addEventListener("blur", this._visHandler);
    window.addEventListener("focus", this._visHandler);
  }

  _loadEnabled() {
    const stored = localStorage.getItem(ENABLED_KEY);
    if (stored !== null) return stored === "true";
    // No explicit choice yet: respect the OS reduced-motion setting by
    // default, but don't forbid the user from opting in later.
    return !prefersReducedMotion;
  }

  _ensureCanvas() {
    if (this.canvas) return;
    this.canvas = document.createElement("canvas");
    this.canvas.id = "bg-canvas";
    document.body.prepend(this.canvas);
  }

  _onVisibility() {
    if (!this.instance) return;
    const visible = document.visibilityState === "visible" && document.hasFocus();
    if (visible) this.instance.start();
    else this.instance.stop();
  }

  getSavedId() {
    return localStorage.getItem(ANIM_KEY) || "none";
  }

  async init() {
    const id = this.enabled ? this.getSavedId() : "none";
    await this.setAnimation(id, { persist: false });
  }

  async setAnimation(id, { persist = true } = {}) {
    if (this.instance) {
      this.instance.destroy();
      this.instance = null;
    }
    this.activeId = id;
    document.documentElement.classList.toggle("has-bg-animation", id !== "none");
    if (persist) localStorage.setItem(ANIM_KEY, id);

    if (id === "none" || !this.enabled) return;

    const def = ANIMATIONS.find((a) => a.id === id);
    if (!def || !def.module) return;

    this._ensureCanvas();
    try {
      const mod = await import(def.module);
      this.instance = mod.default();
      this.instance.init(this.canvas);
      this.instance.setIntensity(this.intensity);
      if (document.visibilityState === "visible") this.instance.start();
    } catch (err) {
      console.error("Failed to load animation", id, err);
    }
  }

  setIntensity(level) {
    this.intensity = level;
    localStorage.setItem(INTENSITY_KEY, level);
    if (this.instance) this.instance.setIntensity(level);
  }

  setEnabled(enabled) {
    this.enabled = enabled;
    localStorage.setItem(ENABLED_KEY, String(enabled));
    if (!enabled) {
      this.setAnimation("none", { persist: false });
    } else {
      this.setAnimation(this.getSavedId(), { persist: false });
    }
  }

  // Reapply the current animation so it re-reads theme colors (--accent
  // etc.) after the user switches color themes.
  refreshForThemeChange() {
    if (this.activeId !== "none" && this.enabled) {
      this.setAnimation(this.activeId, { persist: false });
    }
  }
}

export const animationManager = new AnimationManager();
export const prefersReducedMotionDefault = prefersReducedMotion;

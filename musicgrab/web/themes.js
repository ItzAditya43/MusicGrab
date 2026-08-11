// 20 premium color themes. Every combination of text/textMuted-on-background
// and onAccent-on-accent has been verified to meet WCAG AA contrast
// (>=4.5:1 for body text, >=3:1 for onAccent button text) — see
// scripts/check_theme_contrast.py.
export const THEMES = [
  { id: "midnight-obsidian", name: "Midnight Obsidian", dark: true,  bg: "#05070C", surface: "#0D1119", surface2: "#131826", text: "#F1F5FB", textMuted: "#9AA8C0", accent: "#3E8BFF", accent2: "#6FB1FF", border: "#1E2536", onAccent: "#FFFFFF" },
  { id: "velvet-plum",       name: "Velvet Plum",       dark: true,  bg: "#14081C", surface: "#1E0F2B", surface2: "#291640", text: "#F4E9FF", textMuted: "#BCA5D6", accent: "#D946C7", accent2: "#B968FF", border: "#351C4C", onAccent: "#FFFFFF" },
  { id: "arctic-frost",      name: "Arctic Frost",      dark: false, bg: "#F3F7FA", surface: "#FFFFFF", surface2: "#E7EEF3", text: "#14202B", textMuted: "#4C5C6B", accent: "#0F97AF", accent2: "#37B8CE", border: "#D3E0E8", onAccent: "#06232A" },
  { id: "solar-amber",       name: "Solar Amber",       dark: true,  bg: "#1A130A", surface: "#241B0F", surface2: "#302414", text: "#FBEEDA", textMuted: "#CBAE81", accent: "#F5A623", accent2: "#FFC85C", border: "#3A2C17", onAccent: "#241705" },
  { id: "emerald-depths",    name: "Emerald Depths",    dark: true,  bg: "#06140F", surface: "#0C1F17", surface2: "#122B20", text: "#E7FAF0", textMuted: "#8FC3AA", accent: "#22C58B", accent2: "#5EE9B5", border: "#1B3A2A", onAccent: "#04150E" },
  { id: "rose-quartz",       name: "Rose Quartz",       dark: false, bg: "#FDF3F5", surface: "#FFFFFF", surface2: "#F7E4E9", text: "#3A1F26", textMuted: "#7A5560", accent: "#C85A85", accent2: "#E893B4", border: "#F0D3DC", onAccent: "#FFFFFF" },
  { id: "graphite-steel",    name: "Graphite Steel",    dark: true,  bg: "#121316", surface: "#1A1C20", surface2: "#24262B", text: "#EDEEF0", textMuted: "#9FA5AE", accent: "#6B8CAE", accent2: "#93B4D4", border: "#2C2F35", onAccent: "#FFFFFF" },
  { id: "crimson-ember",     name: "Crimson Ember",     dark: true,  bg: "#0A0505", surface: "#150A0A", surface2: "#1F0F0F", text: "#FBEAEA", textMuted: "#CB9999", accent: "#E5344B", accent2: "#FF6478", border: "#351515", onAccent: "#FFFFFF" },
  { id: "ocean-abyss",       name: "Ocean Abyss",       dark: true,  bg: "#060E1A", surface: "#0B1626", surface2: "#102033", text: "#E6F2FB", textMuted: "#8BAAC5", accent: "#17A8C4", accent2: "#4FD6E8", border: "#16283D", onAccent: "#04121E" },
  { id: "sandstone-dawn",    name: "Sandstone Dawn",    dark: false, bg: "#FAF4EC", surface: "#FFFFFF", surface2: "#F0E4D2", text: "#3B2A1D", textMuted: "#83694F", accent: "#B85A33", accent2: "#E28A5F", border: "#E7D6BE", onAccent: "#FFFFFF" },
  { id: "cyber-neon",        name: "Cyber Neon",        dark: true,  bg: "#0A0014", surface: "#150A24", surface2: "#1C0F30", text: "#F3E9FF", textMuted: "#B3A0CC", accent: "#FF2E9A", accent2: "#00E5FF", border: "#3A1C5C", onAccent: "#0A0014", displayFont: "'Orbitron', 'Inter', sans-serif", monoFont: "'VT323', monospace", uppercase: true },
  { id: "slate-minimal",     name: "Slate Minimal",     dark: true,  bg: "#17181A", surface: "#1F2023", surface2: "#292A2E", text: "#E9EAEC", textMuted: "#9EA3AA", accent: "#8891A0", accent2: "#ADB4C0", border: "#303237", onAccent: "#101113" },
  { id: "royal-indigo",      name: "Royal Indigo",      dark: true,  bg: "#0B0A1F", surface: "#14122E", surface2: "#1D1A3F", text: "#ECEAFF", textMuted: "#A9A3D6", accent: "#7C5CFF", accent2: "#FFD166", border: "#292656", onAccent: "#FFFFFF" },
  { id: "copper-rust",       name: "Copper Rust",       dark: true,  bg: "#170D08", surface: "#221309", surface2: "#2E1B0E", text: "#F7E6D8", textMuted: "#CCA98A", accent: "#C9773B", accent2: "#E39A5E", border: "#3A2312", onAccent: "#FFFFFF" },
  { id: "glacier-blue",      name: "Glacier Blue",      dark: false, bg: "#EFF5FB", surface: "#FFFFFF", surface2: "#DCEAF5", text: "#10202E", textMuted: "#4E6579", accent: "#1C5FCF", accent2: "#4A82E0", border: "#C7DBEA", onAccent: "#FFFFFF" },
  { id: "volcanic-ash",      name: "Volcanic Ash",      dark: true,  bg: "#121110", surface: "#1B1918", surface2: "#262321", text: "#F2ECE8", textMuted: "#AFA59B", accent: "#E8631E", accent2: "#FF8A4C", border: "#322D29", onAccent: "#1A0D04" },
  { id: "lavender-mist",     name: "Lavender Mist",     dark: false, bg: "#F6F3FC", surface: "#FFFFFF", surface2: "#E9E1F7", text: "#2B2440", textMuted: "#6C6389", accent: "#7C5FD1", accent2: "#B39CF0", border: "#DDD3F2", onAccent: "#FFFFFF" },
  { id: "pine-forest",       name: "Pine Forest",       dark: true,  bg: "#0E1712", surface: "#16211B", surface2: "#1F2D24", text: "#E8EFE9", textMuted: "#9DAFA3", accent: "#C9A66B", accent2: "#DDBE8C", border: "#2B392F", onAccent: "#1A1206" },
  { id: "champagne-gold",    name: "Champagne Gold",    dark: false, bg: "#FBF6EC", surface: "#FFFFFF", surface2: "#F1E6C9", text: "#33291A", textMuted: "#7A6A47", accent: "#A9822A", accent2: "#D4B15A", border: "#E8DCB8", onAccent: "#FFFFFF" },
  { id: "void-black",        name: "Void Black",        dark: true,  bg: "#000000", surface: "#0A0A0A", surface2: "#141414", text: "#FFFFFF", textMuted: "#A3A3A3", accent: "#FFFFFF", accent2: "#D8D8D8", border: "#1F1F1F", onAccent: "#000000" },
];

export const DEFAULT_THEME_ID = "cyber-neon";
const STORAGE_KEY = "musicgrab.theme";
const VARS_CACHE_KEY = "musicgrab.themeVars";

function hexToRgb(hex) {
  const h = hex.replace("#", "");
  return [parseInt(h.slice(0, 2), 16), parseInt(h.slice(2, 4), 16), parseInt(h.slice(4, 6), 16)];
}

function rgba(hex, alpha) {
  const [r, g, b] = hexToRgb(hex);
  return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}

export function getTheme(id) {
  return THEMES.find((t) => t.id === id) || THEMES.find((t) => t.id === DEFAULT_THEME_ID);
}

export function getSavedThemeId() {
  return localStorage.getItem(STORAGE_KEY) || DEFAULT_THEME_ID;
}

export function saveThemeId(id) {
  localStorage.setItem(STORAGE_KEY, id);
}

function tokenVars(theme) {
  return {
    "--bg": theme.bg,
    "--surface": theme.surface,
    "--surface-2": theme.surface2,
    "--surface-hover": theme.surface2,
    "--text": theme.text,
    "--text-muted": theme.textMuted,
    "--text-faint": theme.textMuted,
    "--accent": theme.accent,
    "--accent-2": theme.accent2,
    "--border": theme.border,
    "--border-soft": theme.border,
    "--on-accent": theme.onAccent,
    "--glow-a": rgba(theme.accent, 0.55),
    "--glow-a-soft": rgba(theme.accent, 0.25),
    "--glow-b": rgba(theme.accent2, 0.5),
    "--glow-b-soft": rgba(theme.accent2, 0.2),
    "--accent-soft": rgba(theme.accent, 0.14),
    "--accent-ring": rgba(theme.accent, 0.4),
    "--font-display": theme.displayFont || "'Inter', sans-serif",
    "--font-mono": theme.monoFont || "ui-monospace, 'SF Mono', Consolas, monospace",
    "--heading-transform": theme.uppercase ? "uppercase" : "none",
    "--scanline-opacity": theme.dark ? "1" : "0.3",
  };
}

export function applyTheme(theme) {
  const root = document.documentElement.style;
  const vars = tokenVars(theme);
  for (const [key, value] of Object.entries(vars)) root.setProperty(key, value);
  document.documentElement.dataset.theme = theme.id;
  document.documentElement.classList.toggle("theme-light", !theme.dark);
  // Cache resolved vars so index.html's inline bootstrap script can apply
  // them synchronously on next launch, before this module even loads —
  // avoids a flash of the default theme.
  try {
    localStorage.setItem(VARS_CACHE_KEY, JSON.stringify(vars));
  } catch {
    // localStorage unavailable (e.g. private mode) — non-fatal, just no
    // FOUC-avoidance cache; the module will still apply the theme itself.
  }
}

export function initTheme() {
  const theme = getTheme(getSavedThemeId());
  applyTheme(theme);
  return theme;
}

export function setActiveTheme(id) {
  const theme = getTheme(id);
  applyTheme(theme);
  saveThemeId(theme.id);
  return theme;
}

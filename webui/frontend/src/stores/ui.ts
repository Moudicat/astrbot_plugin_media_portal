import { defineStore } from "pinia";
import { safeGet, safeSet } from "@/utils/storage";
import type { ContextMenuEntry } from "@/api/types";

const THEME_KEY = "media_portal_theme";
const STAT_VISIBILITY_KEY = "media_portal_stat_visibility";
const THEME_COLOR_KEY = "media_portal_theme_color";
const PAGE_SIZE_KEY = "media_portal_page_size";
const GRID_DENSITY_KEY = "media_portal_grid_density";
const GRID_MODE_KEY = "media_portal_grid_mode";

export const STAT_VISIBILITY_KEYS = ["total", "image", "video", "audio", "cat", "size"] as const;
export type StatKey = (typeof STAT_VISIBILITY_KEYS)[number];
export type StatVisibility = Record<StatKey, boolean>;

export type ThemeColor = "indigo" | "violet" | "sky" | "emerald" | "rose" | "amber" | "slate";
export const THEME_COLOR_KEYS: ThemeColor[] = [
  "indigo",
  "violet",
  "sky",
  "emerald",
  "rose",
  "amber",
  "slate",
];
export interface ThemeColorPreset {
  primary: string;
  soft: string;
  strong: string;
  gradient: string;
  gradientHover: string;
  bgDark: string;
  bgLight: string;
}

export const THEME_COLOR_PRESETS: Record<ThemeColor, ThemeColorPreset> = {
  indigo: {
    primary: "#6366f1",
    soft: "rgba(99, 102, 241, 0.16)",
    strong: "#4f46e5",
    gradient: "linear-gradient(135deg, #6366f1, #8b5cf6)",
    gradientHover: "linear-gradient(135deg, #4f46e5, #7c3aed)",
    bgDark:
      "radial-gradient(circle at 10% -10%, rgba(99, 102, 241, 0.22), transparent 40%), radial-gradient(circle at 110% 10%, rgba(34, 197, 94, 0.18), transparent 45%), radial-gradient(circle at 50% 120%, rgba(139, 92, 246, 0.18), transparent 45%)",
    bgLight:
      "radial-gradient(circle at 8% -10%, rgba(99, 102, 241, 0.18), transparent 40%), radial-gradient(circle at 110% 10%, rgba(14, 165, 233, 0.14), transparent 45%), radial-gradient(circle at 50% 120%, rgba(244, 114, 182, 0.14), transparent 45%)",
  },
  violet: {
    primary: "#8b5cf6",
    soft: "rgba(139, 92, 246, 0.18)",
    strong: "#7c3aed",
    gradient: "linear-gradient(135deg, #8b5cf6, #ec4899)",
    gradientHover: "linear-gradient(135deg, #7c3aed, #db2777)",
    bgDark:
      "radial-gradient(circle at 10% -10%, rgba(139, 92, 246, 0.26), transparent 42%), radial-gradient(circle at 110% 10%, rgba(236, 72, 153, 0.2), transparent 45%), radial-gradient(circle at 50% 120%, rgba(99, 102, 241, 0.18), transparent 45%)",
    bgLight:
      "radial-gradient(circle at 8% -10%, rgba(139, 92, 246, 0.18), transparent 42%), radial-gradient(circle at 110% 10%, rgba(236, 72, 153, 0.14), transparent 45%), radial-gradient(circle at 50% 120%, rgba(168, 85, 247, 0.14), transparent 45%)",
  },
  sky: {
    primary: "#0ea5e9",
    soft: "rgba(14, 165, 233, 0.18)",
    strong: "#0284c7",
    gradient: "linear-gradient(135deg, #0ea5e9, #6366f1)",
    gradientHover: "linear-gradient(135deg, #0284c7, #4f46e5)",
    bgDark:
      "radial-gradient(circle at 10% -10%, rgba(14, 165, 233, 0.25), transparent 42%), radial-gradient(circle at 110% 10%, rgba(99, 102, 241, 0.2), transparent 45%), radial-gradient(circle at 50% 120%, rgba(56, 189, 248, 0.18), transparent 45%)",
    bgLight:
      "radial-gradient(circle at 8% -10%, rgba(14, 165, 233, 0.2), transparent 42%), radial-gradient(circle at 110% 10%, rgba(99, 102, 241, 0.14), transparent 45%), radial-gradient(circle at 50% 120%, rgba(186, 230, 253, 0.5), transparent 55%)",
  },
  emerald: {
    primary: "#10b981",
    soft: "rgba(16, 185, 129, 0.18)",
    strong: "#059669",
    gradient: "linear-gradient(135deg, #10b981, #06b6d4)",
    gradientHover: "linear-gradient(135deg, #059669, #0891b2)",
    bgDark:
      "radial-gradient(circle at 10% -10%, rgba(16, 185, 129, 0.24), transparent 42%), radial-gradient(circle at 110% 10%, rgba(6, 182, 212, 0.22), transparent 45%), radial-gradient(circle at 50% 120%, rgba(34, 197, 94, 0.18), transparent 45%)",
    bgLight:
      "radial-gradient(circle at 8% -10%, rgba(16, 185, 129, 0.18), transparent 42%), radial-gradient(circle at 110% 10%, rgba(6, 182, 212, 0.14), transparent 45%), radial-gradient(circle at 50% 120%, rgba(190, 242, 100, 0.2), transparent 50%)",
  },
  rose: {
    primary: "#f43f5e",
    soft: "rgba(244, 63, 94, 0.18)",
    strong: "#e11d48",
    gradient: "linear-gradient(135deg, #f43f5e, #f97316)",
    gradientHover: "linear-gradient(135deg, #e11d48, #ea580c)",
    bgDark:
      "radial-gradient(circle at 10% -10%, rgba(244, 63, 94, 0.24), transparent 42%), radial-gradient(circle at 110% 10%, rgba(249, 115, 22, 0.2), transparent 45%), radial-gradient(circle at 50% 120%, rgba(236, 72, 153, 0.18), transparent 45%)",
    bgLight:
      "radial-gradient(circle at 8% -10%, rgba(244, 63, 94, 0.18), transparent 42%), radial-gradient(circle at 110% 10%, rgba(251, 146, 60, 0.14), transparent 45%), radial-gradient(circle at 50% 120%, rgba(253, 164, 175, 0.2), transparent 50%)",
  },
  amber: {
    primary: "#f59e0b",
    soft: "rgba(245, 158, 11, 0.18)",
    strong: "#d97706",
    gradient: "linear-gradient(135deg, #f59e0b, #ef4444)",
    gradientHover: "linear-gradient(135deg, #d97706, #dc2626)",
    bgDark:
      "radial-gradient(circle at 10% -10%, rgba(245, 158, 11, 0.24), transparent 42%), radial-gradient(circle at 110% 10%, rgba(239, 68, 68, 0.2), transparent 45%), radial-gradient(circle at 50% 120%, rgba(250, 204, 21, 0.18), transparent 45%)",
    bgLight:
      "radial-gradient(circle at 8% -10%, rgba(245, 158, 11, 0.2), transparent 42%), radial-gradient(circle at 110% 10%, rgba(253, 186, 116, 0.18), transparent 45%), radial-gradient(circle at 50% 120%, rgba(254, 240, 138, 0.28), transparent 50%)",
  },
  slate: {
    primary: "#64748b",
    soft: "rgba(100, 116, 139, 0.18)",
    strong: "#475569",
    gradient: "linear-gradient(135deg, #64748b, #334155)",
    gradientHover: "linear-gradient(135deg, #475569, #1e293b)",
    bgDark:
      "radial-gradient(circle at 10% -10%, rgba(100, 116, 139, 0.22), transparent 42%), radial-gradient(circle at 110% 10%, rgba(71, 85, 105, 0.22), transparent 45%), radial-gradient(circle at 50% 120%, rgba(148, 163, 184, 0.14), transparent 45%)",
    bgLight:
      "radial-gradient(circle at 8% -10%, rgba(100, 116, 139, 0.16), transparent 42%), radial-gradient(circle at 110% 10%, rgba(148, 163, 184, 0.14), transparent 45%), radial-gradient(circle at 50% 120%, rgba(203, 213, 225, 0.28), transparent 50%)",
  },
};

export type GridDensity = "compact" | "cozy" | "comfortable";
export const GRID_DENSITY_KEYS: GridDensity[] = ["compact", "cozy", "comfortable"];

export type GridMode = "card" | "list";
export const GRID_MODE_KEYS: GridMode[] = ["card", "list"];

export const PAGE_SIZE_OPTIONS = [20, 40, 60, 80, 120] as const;
export type PageSize = (typeof PAGE_SIZE_OPTIONS)[number];

function getInitialTheme(): "dark" | "light" {
  try {
    const saved = localStorage.getItem(THEME_KEY);
    if (saved === "light" || saved === "dark") return saved;
    const prefersDark =
      window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches;
    return prefersDark ? "dark" : "light";
  } catch (_e) {
    return "dark";
  }
}

function defaultStatVisibility(): StatVisibility {
  return STAT_VISIBILITY_KEYS.reduce((acc, key) => {
    acc[key] = true;
    return acc;
  }, {} as StatVisibility);
}

function loadStatVisibility(): StatVisibility {
  const fallback = defaultStatVisibility();
  const raw = safeGet<Partial<StatVisibility>>(STAT_VISIBILITY_KEY, {});
  const merged: StatVisibility = { ...fallback };
  for (const key of STAT_VISIBILITY_KEYS) {
    if (typeof raw[key] === "boolean") merged[key] = raw[key] as boolean;
  }
  return merged;
}

function persistStatVisibility(state: StatVisibility) {
  const payload: Record<string, boolean> = {};
  for (const key of STAT_VISIBILITY_KEYS) {
    payload[key] = state[key] !== false;
  }
  safeSet(STAT_VISIBILITY_KEY, payload);
}

function loadThemeColor(): ThemeColor {
  const raw = safeGet<string>(THEME_COLOR_KEY, "indigo");
  return (THEME_COLOR_KEYS as string[]).includes(raw) ? (raw as ThemeColor) : "indigo";
}

function loadPageSize(): PageSize {
  const raw = safeGet<number>(PAGE_SIZE_KEY, 40);
  return ((PAGE_SIZE_OPTIONS as readonly number[]).includes(raw) ? raw : 40) as PageSize;
}

function loadGridDensity(): GridDensity {
  const raw = safeGet<string>(GRID_DENSITY_KEY, "cozy");
  return (GRID_DENSITY_KEYS as string[]).includes(raw) ? (raw as GridDensity) : "cozy";
}

function loadGridMode(): GridMode {
  const raw = safeGet<string>(GRID_MODE_KEY, "card");
  return (GRID_MODE_KEYS as string[]).includes(raw) ? (raw as GridMode) : "card";
}

function hexToRgbTriplet(input: string): string {
  const m = /^#?([0-9a-fA-F]{3}|[0-9a-fA-F]{6})$/.exec(input.trim());
  if (!m) return "99, 102, 241";
  let hex = m[1];
  if (hex.length === 3) hex = hex.split("").map((c) => c + c).join("");
  const n = parseInt(hex, 16);
  return `${(n >> 16) & 0xff}, ${(n >> 8) & 0xff}, ${n & 0xff}`;
}

interface ContextMenuState {
  visible: boolean;
  x: number;
  y: number;
  items: ContextMenuEntry[];
  payload: any;
}

export const useUiStore = defineStore("ui", {
  state: () => ({
    theme: getInitialTheme(),
    sidebarOpen: false,
    statVisibility: loadStatVisibility(),
    themeColor: loadThemeColor() as ThemeColor,
    pageSize: loadPageSize() as PageSize,
    gridDensity: loadGridDensity() as GridDensity,
    gridMode: loadGridMode() as GridMode,
    contextMenu: {
      visible: false,
      x: 0,
      y: 0,
      items: [] as ContextMenuEntry[],
      payload: null,
    } as ContextMenuState,
  }),
  actions: {
    applyTheme() {
      const root = document.documentElement;
      root.setAttribute("data-theme", this.theme);
      root.setAttribute("data-theme-color", this.themeColor);
      root.setAttribute("data-grid-density", this.gridDensity);
      root.setAttribute("data-grid-mode", this.gridMode);
      const preset = THEME_COLOR_PRESETS[this.themeColor] || THEME_COLOR_PRESETS.indigo;
      root.style.setProperty("--primary", preset.primary);
      root.style.setProperty("--primary-soft", preset.soft);
      root.style.setProperty("--primary-strong", preset.strong);
      root.style.setProperty("--primary-gradient", preset.gradient);
      root.style.setProperty("--primary-gradient-hover", preset.gradientHover);
      root.style.setProperty(
        "--bg-gradient",
        this.theme === "light" ? preset.bgLight : preset.bgDark,
      );
      const rgb = hexToRgbTriplet(preset.primary);
      root.style.setProperty("--primary-rgb", rgb);
      root.style.setProperty("--primary-border", `rgba(${rgb}, 0.3)`);
      root.style.setProperty("--primary-border-strong", `rgba(${rgb}, 0.35)`);
      root.style.setProperty(
        "--glow-primary",
        `0 0 0 1px rgba(${rgb}, 0.35), 0 12px 30px rgba(${rgb}, 0.25)`,
      );
      root.style.setProperty("--ring-primary", `0 0 0 3px rgba(${rgb}, 0.22)`);
      try {
        localStorage.setItem(THEME_KEY, this.theme);
      } catch (_e) {
        // ignore
      }
    },
    toggleTheme() {
      this.theme = this.theme === "dark" ? "light" : "dark";
      this.applyTheme();
    },
    updateStatVisibility(next: Partial<StatVisibility>) {
      if (!next || typeof next !== "object") return;
      const merged = { ...this.statVisibility };
      for (const key of Object.keys(next) as StatKey[]) {
        if (typeof next[key] === "boolean") merged[key] = next[key] as boolean;
      }
      this.statVisibility = merged;
      persistStatVisibility(merged);
    },
    setThemeColor(color: ThemeColor) {
      if (!(THEME_COLOR_KEYS as string[]).includes(color)) return;
      this.themeColor = color;
      safeSet(THEME_COLOR_KEY, color);
      this.applyTheme();
    },
    setPageSize(size: number) {
      if (!(PAGE_SIZE_OPTIONS as readonly number[]).includes(size)) return;
      this.pageSize = size as PageSize;
      safeSet(PAGE_SIZE_KEY, size);
    },
    setGridDensity(density: GridDensity) {
      if (!(GRID_DENSITY_KEYS as string[]).includes(density)) return;
      this.gridDensity = density;
      safeSet(GRID_DENSITY_KEY, density);
      this.applyTheme();
    },
    setGridMode(mode: GridMode) {
      if (!(GRID_MODE_KEYS as string[]).includes(mode)) return;
      this.gridMode = mode;
      safeSet(GRID_MODE_KEY, mode);
      this.applyTheme();
    },
    toggleGridMode() {
      this.setGridMode(this.gridMode === "card" ? "list" : "card");
    },
    setSidebarOpen(open: boolean) {
      this.sidebarOpen = open;
    },
    isPcHoverDevice(): boolean {
      try {
        return (
          typeof window !== "undefined" &&
          typeof window.matchMedia === "function" &&
          window.matchMedia("(hover: hover) and (pointer: fine)").matches
        );
      } catch (_e) {
        return false;
      }
    },
    openContextMenu(event: MouseEvent, items: ContextMenuEntry[], payload: any = null) {
      if (!this.isPcHoverDevice()) return;
      if (!Array.isArray(items) || !items.length) return;
      const x = event && typeof event.clientX === "number" ? event.clientX : 0;
      const y = event && typeof event.clientY === "number" ? event.clientY : 0;
      this.contextMenu = { visible: true, x, y, items, payload };
    },
    closeContextMenu() {
      if (this.contextMenu.visible) {
        this.contextMenu = { visible: false, x: 0, y: 0, items: [], payload: null };
      }
    },
  },
});

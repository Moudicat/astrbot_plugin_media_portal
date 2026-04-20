import { defineStore } from "pinia";
import { safeGet, safeSet } from "@/utils/storage";
import type { ContextMenuEntry } from "@/api/types";

const THEME_KEY = "media_portal_theme";
const STAT_VISIBILITY_KEY = "media_portal_stat_visibility";

export const STAT_VISIBILITY_KEYS = ["total", "image", "video", "audio", "cat", "size"] as const;
export type StatKey = (typeof STAT_VISIBILITY_KEYS)[number];
export type StatVisibility = Record<StatKey, boolean>;

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
      document.documentElement.setAttribute("data-theme", this.theme);
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

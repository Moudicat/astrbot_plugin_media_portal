import { defineStore } from "pinia";
import type { ConfirmOptions } from "@/api/types";

interface ConfirmState extends Required<Omit<ConfirmOptions, "message" | "detail">> {
  visible: boolean;
  message: string;
  detail: string;
}

function defaultState(): ConfirmState {
  return {
    visible: false,
    title: "请确认",
    message: "",
    detail: "",
    confirmText: "确认",
    cancelText: "取消",
    tone: "primary",
    icon: "",
  };
}

export const useConfirmStore = defineStore("confirm", {
  state: () => ({
    ...defaultState(),
    _resolver: null as ((value: boolean) => void) | null,
  }),
  actions: {
    confirm(options: ConfirmOptions = {}): Promise<boolean> {
      return new Promise((resolve) => {
        if (this._resolver) {
          try {
            this._resolver(false);
          } catch (_e) {
            // ignore
          }
        }
        this._resolver = resolve;
        this.visible = true;
        this.title = options.title || "请确认";
        this.message = options.message || "";
        this.detail = options.detail || "";
        this.confirmText = options.confirmText || "确认";
        this.cancelText = options.cancelText || "取消";
        this.tone = options.tone || "primary";
        this.icon = options.icon || "";
      });
    },
    resolve(result: boolean) {
      this.visible = false;
      const resolver = this._resolver;
      this._resolver = null;
      if (resolver) {
        try {
          resolver(!!result);
        } catch (_e) {
          // ignore
        }
      }
    },
  },
});

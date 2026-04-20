import { defineStore } from "pinia";
import type { ToastMessage, ToastType } from "@/api/types";
import { i18n } from "@/i18n";

export const useToastStore = defineStore("toast", {
  state: () => ({
    messages: [] as ToastMessage[],
  }),
  actions: {
    push(text: string, type: ToastType = "info", title = "") {
      const translate = (i18n.global as unknown as { t: (key: string) => string }).t;
      const displayTitle = title || translate(`toast.${type}`);
      const id = `${Date.now()}_${Math.random()}`;
      this.messages.push({ id, text, type, title: displayTitle });
      setTimeout(() => {
        this.messages = this.messages.filter((item) => item.id !== id);
      }, 2800);
    },
    remove(id: string) {
      this.messages = this.messages.filter((item) => item.id !== id);
    },
  },
});

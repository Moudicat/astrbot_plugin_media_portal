import { defineStore } from "pinia";
import { dataApi } from "@/api/data";
import type { DataTextResp, DataTreeItem } from "@/api/types";

interface PreviewState {
  loading: boolean;
  item: DataTreeItem | null;
  name: string;
  path: string;
  size: number;
  mime: string;
  kind: string;
  suffix?: string;
  isText: boolean;
  content: string;
  truncated: boolean;
  encoding: string;
  downloadUrl: string;
  message?: string;
}

export const useDataBrowserStore = defineStore("dataBrowser", {
  state: () => ({
    items: [] as DataTreeItem[],
    path: "",
    parent: "",
    loading: false,
    preview: null as PreviewState | null,
    previewLoading: false,
  }),
  actions: {
    async fetchTree(path = "") {
      this.loading = true;
      try {
        const data = await dataApi.tree(path);
        this.items = data.items || [];
        this.path = data.path || "";
        this.parent = data.parent || "";
      } finally {
        this.loading = false;
      }
    },
    async openText(item: DataTreeItem, buildUrl: (path: string) => string) {
      this.previewLoading = true;
      this.preview = {
        loading: true,
        item,
        name: item.name,
        path: item.path,
        size: item.size || 0,
        mime: item.mime || "",
        kind: item.kind || "",
        isText: false,
        content: "",
        truncated: false,
        encoding: "",
        downloadUrl: buildUrl(item.path),
      };
      try {
        const data = await dataApi.text(item.path);
        this.preview = {
          loading: false,
          item,
          name: data.name || item.name,
          path: data.path || item.path,
          size: data.size ?? item.size ?? 0,
          mime: data.mime || item.mime || "",
          kind: data.kind || item.kind || "",
          suffix: data.suffix || "",
          isText: !!data.is_text,
          content: data.content || "",
          truncated: !!data.truncated,
          encoding: data.encoding || "",
          downloadUrl: buildUrl(data.path || item.path),
        };
      } catch (error) {
        const err = error as Error;
        this.preview = {
          ...(this.preview as PreviewState),
          loading: false,
          isText: false,
          content: "",
          message: err.message,
        };
        throw err;
      } finally {
        this.previewLoading = false;
      }
    },
    closePreview() {
      this.preview = null;
    },
  },
});

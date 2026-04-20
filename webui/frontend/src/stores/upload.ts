import { defineStore } from "pinia";
import type { UploadJob } from "@/api/types";
import { useAuthStore } from "./auth";

type RefreshCallback = () => void;

export const useUploadStore = defineStore("upload", {
  state: () => ({
    jobs: [] as UploadJob[],
    panelOpen: false,
    _autoClearTimer: null as ReturnType<typeof setTimeout> | null,
    _refreshTimer: null as ReturnType<typeof setTimeout> | null,
    _refreshCb: null as RefreshCallback | null,
    _errorCb: null as ((text: string) => void) | null,
  }),
  actions: {
    setRefreshHandler(cb: RefreshCallback | null) {
      this._refreshCb = cb;
    },
    setErrorHandler(cb: ((text: string) => void) | null) {
      this._errorCb = cb;
    },
    toggle() {
      this.panelOpen = !this.panelOpen;
    },
    getJob(id: string): UploadJob | null {
      return this.jobs.find((item) => item && item.id === id) || null;
    },
    enqueue(file: File, category: string, description: string) {
      const id = `${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
      const job: UploadJob = {
        id,
        name: file.name,
        size: file.size,
        category,
        description,
        progress: 0,
        loaded: 0,
        status: "uploading",
        message: "",
        xhr: null,
      };
      this.jobs.push(job);
      this.panelOpen = true;
      this.start(id, file);
    },
    start(id: string, file: File) {
      const job = this.getJob(id);
      if (!job) return;
      const form = new FormData();
      form.append("category", job.category || "default");
      form.append("description", job.description || "");
      form.append("files", file, file.name);

      const xhr = new XMLHttpRequest();
      job.xhr = xhr;
      xhr.open("POST", "/api/media/upload");
      const authStore = useAuthStore();
      if (authStore.token) {
        xhr.setRequestHeader("Authorization", `Bearer ${authStore.token}`);
      }
      xhr.upload.addEventListener("progress", (event) => {
        if (!event.lengthComputable) return;
        const cur = this.getJob(id);
        if (!cur) return;
        cur.loaded = event.loaded;
        cur.progress = Math.min(100, Math.round((event.loaded / event.total) * 100));
      });
      xhr.upload.addEventListener("load", () => {
        const cur = this.getJob(id);
        if (!cur) return;
        if (cur.status === "uploading") {
          cur.loaded = cur.size;
          cur.progress = Math.max(cur.progress || 0, 99);
        }
      });
      xhr.addEventListener("load", () => {
        const cur = this.getJob(id);
        if (!cur) return;
        let payload: any = null;
        try {
          payload = JSON.parse(xhr.responseText || "null");
        } catch (_e) {
          payload = null;
        }
        if (xhr.status >= 200 && xhr.status < 300 && payload) {
          const savedList = Array.isArray(payload.saved) ? payload.saved : [];
          const errorsList = Array.isArray(payload.errors) ? payload.errors : [];
          if (savedList.length) {
            cur.status = "done";
            cur.progress = 100;
            cur.loaded = cur.size;
            cur.message = "已保存";
          } else if (errorsList.length) {
            cur.status = "error";
            cur.message = extractErrorText(errorsList[0], file.name);
            this._errorCb?.(`${file.name} 上传失败：${cur.message}`);
          } else {
            cur.status = "error";
            cur.message = "未返回结果";
          }
          if (savedList.length || errorsList.length) {
            this.scheduleRefresh();
          }
        } else {
          let detail = "上传失败";
          if (payload && payload.detail) detail = payload.detail;
          else if (xhr.statusText) detail = xhr.statusText;
          cur.status = "error";
          cur.message = detail;
          this._errorCb?.(`${file.name} 上传失败：${detail}`);
        }
        this.scheduleAutoClear();
      });
      xhr.addEventListener("error", () => {
        const cur = this.getJob(id);
        if (!cur) return;
        cur.status = "error";
        cur.message = "网络错误";
        this._errorCb?.(`${file.name} 上传失败：网络错误`);
        this.scheduleAutoClear();
      });
      xhr.addEventListener("abort", () => {
        const cur = this.getJob(id);
        if (!cur) return;
        if (cur.status !== "done") {
          cur.status = "cancelled";
          cur.message = "已取消";
        }
        this.scheduleAutoClear();
      });
      xhr.send(form);
    },
    cancel(id: string) {
      const job = this.getJob(id);
      if (!job) return;
      if (job.xhr && job.status === "uploading") {
        try {
          job.xhr.abort();
        } catch (_e) {
          // ignore
        }
      }
    },
    dismiss(id: string) {
      this.jobs = this.jobs.filter((item) => item.id !== id);
    },
    clearFinished() {
      this.jobs = this.jobs.filter((item) => item.status === "uploading");
      if (!this.jobs.length) this.panelOpen = false;
    },
    scheduleAutoClear() {
      if (this._autoClearTimer) clearTimeout(this._autoClearTimer);
      this._autoClearTimer = setTimeout(() => {
        this._autoClearTimer = null;
        if (this.jobs.some((job) => job.status === "uploading")) return;
        const hasError = this.jobs.some(
          (job) => job.status === "error" || job.status === "cancelled",
        );
        if (hasError) return;
        this.jobs = [];
        this.panelOpen = false;
      }, 2400);
    },
    scheduleRefresh() {
      if (this._refreshTimer) clearTimeout(this._refreshTimer);
      this._refreshTimer = setTimeout(() => {
        this._refreshTimer = null;
        this._refreshCb?.();
      }, 400);
    },
  },
});

function extractErrorText(raw: unknown, fallbackName: string): string {
  const text = String(raw || "").trim();
  if (!text) return "未知错误";
  const prefix = `${fallbackName}: `;
  if (text.startsWith(prefix)) return text.slice(prefix.length);
  const colonIdx = text.indexOf(": ");
  if (colonIdx > 0 && text.slice(0, colonIdx) === fallbackName) {
    return text.slice(colonIdx + 2);
  }
  return text;
}

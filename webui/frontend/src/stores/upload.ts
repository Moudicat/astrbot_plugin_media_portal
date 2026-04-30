import { defineStore } from "pinia";
import type { ConfirmOptions, UploadJob } from "@/api/types";
import { useAuthStore } from "./auth";
import { useConfirmStore } from "./confirm";
import { useProgressStore } from "./progress";
import { i18n } from "@/i18n";

type ConfirmFn = (options?: ConfirmOptions) => Promise<boolean>;
type TFn = (key: string, named?: Record<string, unknown>) => string;

const translate: TFn = (key, named) => {
  const fn = (i18n.global as any).t as (...args: any[]) => string;
  return named ? fn(key, named) : fn(key);
};

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
      this.start(id, file, "error");
    },
    start(id: string, file: File, duplicatePolicy: "error" | "force" | "reuse" = "error") {
      const job = this.getJob(id);
      if (!job) return;
      job.status = "uploading";
      job.message = "";
      job.progress = 0;
      job.loaded = 0;
      const form = new FormData();
      form.append("category", job.category || "default");
      form.append("description", job.description || "");
      form.append("duplicate_policy", duplicatePolicy);
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
      xhr.addEventListener("load", async () => {
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
          const duplicatesList = Array.isArray(payload.duplicates) ? payload.duplicates : [];
          if (savedList.length) {
            cur.status = "done";
            cur.progress = 100;
            cur.loaded = cur.size;
            cur.message = "已保存";
          } else if (duplicatesList.length) {
            const t = translate;
            const first = duplicatesList[0] || {};
            const existing = first?.existing || {};
            const existedName = existing.filename || file.name;
            const existedCategory = existing.category || "";
            const detailLines = [t("upload.duplicateDetail")];
            if (existedCategory) {
              detailLines.unshift(
                t("upload.duplicateExistingHint", { category: existedCategory }),
              );
            }
            cur.status = "uploading";
            cur.message = t("upload.duplicateAwaiting");
            const confirmStore = useConfirmStore() as unknown as { confirm: ConfirmFn };
            const ok = await confirmStore.confirm({
              title: t("upload.duplicateTitle"),
              message: t("upload.duplicateMessage", { name: existedName }),
              detail: detailLines.join("\n"),
              confirmText: t("upload.duplicateContinue"),
              cancelText: t("upload.duplicateCancel"),
              tone: "warning",
              icon: "alert-triangle",
            });
            const fresh = this.getJob(id);
            if (!fresh) return;
            if (ok) {
              this.start(id, file, "force");
              return;
            }
            fresh.status = "cancelled";
            fresh.message = t("upload.duplicateCancelled");
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
          if (savedList.length) {
            // 上传成功后让进度中心立刻轮询一次，确保后端自动触发的
            // CLIP / 人脸扫描能尽快出现在进度条里——尤其是秒级完成的扫描。
            try {
              useProgressStore().bump();
            } catch (_e) {
              // store 还没初始化时忽略；此时进度中心也尚未挂载。
            }
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

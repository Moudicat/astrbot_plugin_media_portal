import { Icon } from "./components/Icon.js";
import { LoginView } from "./components/LoginView.js";
import { Sidebar } from "./components/Sidebar.js";
import { MediaGrid } from "./components/MediaGrid.js";
import { MediaDrawer } from "./components/MediaDrawer.js";
import { UploadDialog } from "./components/UploadDialog.js";
import { PlayerModal } from "./components/PlayerModal.js";
import { DataBrowser } from "./components/DataBrowser.js";
import { DataFileModal } from "./components/DataFileModal.js";
import { CategoryCreateDialog } from "./components/CategoryCreateDialog.js";
import { Toast } from "./components/Toast.js";
import { AudioDock } from "./components/AudioDock.js";
import { UploadProgress } from "./components/UploadProgress.js";

const { createApp } = Vue;

const THEME_KEY = "media_portal_theme";

function getInitialTheme() {
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

createApp({
  components: {
    Icon,
    LoginView,
    Sidebar,
    MediaGrid,
    MediaDrawer,
    UploadDialog,
    PlayerModal,
    DataBrowser,
    DataFileModal,
    CategoryCreateDialog,
    Toast,
    AudioDock,
    UploadProgress,
  },
  data() {
    return {
      theme: getInitialTheme(),
      token: "",
      readonlyToken: "",
      dataToken: "",
      loginLoading: false,
      loginError: "",
      loadingMedia: false,
      loadingData: false,
      sidebarOpen: false,
      viewMode: "media",
      categories: [],
      mediaItems: [],
      mediaStats: {},
      selectedIds: [],
      selectedMedia: null,
      drawerVisible: false,
      uploadVisible: false,
      uploadMode: "file",
      playerVisible: false,
      playerItem: null,
      playerList: [],
      playerSource: "",
      audioDockItem: null,
      dataItems: [],
      dataPath: "",
      dataParent: "",
      dataPreview: null,
      dataPreviewLoading: false,
      uploadJobs: [],
      uploadPanelOpen: false,
      categoryDialogVisible: false,
      filters: {
        category: "",
        query: "",
        kind: "",
        page: 1,
        page_size: 20,
      },
      pagination: {
        total: 0,
        totalPages: 0,
      },
      toasts: [],
      config: {
        access_urls: [],
        public_base_url: "",
        expose_astrbot_data: true,
        max_file_size_mb: 500,
        max_file_size_bytes: 500 * 1024 * 1024,
      },
    };
  },
  computed: {
    selectedCount() {
      return this.selectedIds.length;
    },
    canDataBrowse() {
      return !!this.config.expose_astrbot_data;
    },
  },
  mounted() {
    this.applyTheme(this.theme);
    if (this.token) {
      this.bootstrap().catch((error) => {
        this.notify(`初始化失败: ${error.message}`, "error");
        this.logout(false);
      });
    }
  },
  methods: {
    applyTheme(theme) {
      document.documentElement.setAttribute("data-theme", theme);
      try {
        localStorage.setItem(THEME_KEY, theme);
      } catch (_e) {
        // ignore
      }
    },
    toggleTheme() {
      this.theme = this.theme === "dark" ? "light" : "dark";
      this.applyTheme(this.theme);
    },
    notify(text, type = "info", title = "") {
      const id = `${Date.now()}_${Math.random()}`;
      const displayTitle =
        title ||
        (type === "success"
          ? "成功"
          : type === "error"
          ? "出错了"
          : type === "warning"
          ? "注意"
          : "提示");
      this.toasts.push({ id, text, type, title: displayTitle });
      setTimeout(() => {
        this.toasts = this.toasts.filter((item) => item.id !== id);
      }, 2800);
    },
    authHeaders(extra = {}) {
      const headers = { ...extra };
      if (this.token) {
        headers.Authorization = `Bearer ${this.token}`;
      }
      return headers;
    },
    async request(url, options = {}) {
      const {
        method = "GET",
        body = null,
        auth = true,
        form = false,
        headers = {},
      } = options;

      const finalHeaders = auth ? this.authHeaders(headers) : { ...headers };
      const requestInit = { method, headers: finalHeaders };

      if (body !== null) {
        if (form) {
          requestInit.body = body;
        } else {
          requestInit.headers["Content-Type"] = "application/json";
          requestInit.body = JSON.stringify(body);
        }
      }

      const response = await fetch(url, requestInit);
      let payload = null;
      const contentType = response.headers.get("content-type") || "";
      if (contentType.includes("application/json")) {
        payload = await response.json();
      } else {
        payload = await response.text();
      }

      if (!response.ok) {
        const detail =
          (payload && payload.detail) ||
          (typeof payload === "string" ? payload : "请求失败");
        throw new Error(detail);
      }
      return payload;
    },
    async bootstrap() {
      await this.fetchConfig();
      await Promise.all([this.fetchCategories(), this.fetchStats(), this.fetchMedia()]);
      if (this.viewMode === "data" && this.canDataBrowse) {
        await this.fetchDataTree("");
      }
    },
    async login(password) {
      this.loginLoading = true;
      this.loginError = "";
      try {
        const result = await this.request("/api/login", {
          method: "POST",
          body: { password },
          auth: false,
        });
        this.token = result.token;
        this.readonlyToken = result.readonly_token || "";
        this.dataToken = result.data_token || "";
        await this.bootstrap();
        this.notify("欢迎回来 Astrbot Media Portal", "success");
      } catch (error) {
        this.loginError = error.message;
      } finally {
        this.loginLoading = false;
      }
    },
    async logout(showToast = true) {
      try {
        if (this.token) {
          await this.request("/api/logout", { method: "POST" });
        }
      } catch (_error) {
        // ignore
      }
      this.token = "";
      this.readonlyToken = "";
      this.dataToken = "";
      this.categories = [];
      this.mediaItems = [];
      this.mediaStats = {};
      this.selectedIds = [];
      this.selectedMedia = null;
      this.drawerVisible = false;
      this.audioDockItem = null;
      this.playerVisible = false;
      if (showToast) {
        this.notify("已安全退出", "info");
      }
    },
    async fetchConfig() {
      const data = await this.request("/api/config");
      const maxMb = Number(data.max_file_size_mb) > 0 ? Number(data.max_file_size_mb) : 500;
      const maxBytes =
        Number(data.max_file_size_bytes) > 0
          ? Number(data.max_file_size_bytes)
          : maxMb * 1024 * 1024;
      this.config = {
        ...this.config,
        ...data,
        max_file_size_mb: maxMb,
        max_file_size_bytes: maxBytes,
      };
      this.readonlyToken = data.readonly_token || "";
      this.dataToken = data.data_token || "";
    },
    async fetchCategories() {
      const data = await this.request("/api/categories");
      this.categories = data.items || [];
    },
    async fetchStats() {
      try {
        this.mediaStats = await this.request("/api/stats");
      } catch (_e) {
        this.mediaStats = {};
      }
    },
    async fetchMedia() {
      this.loadingMedia = true;
      try {
        const query = new URLSearchParams({
          category: this.filters.category,
          kind: this.filters.kind,
          query: this.filters.query,
          page: String(this.filters.page),
          page_size: String(this.filters.page_size),
        });
        const data = await this.request(`/api/media?${query.toString()}`);
        this.mediaItems = data.items || [];
        this.pagination.total = data.total || 0;
        this.pagination.totalPages = data.total_pages || 0;
        const idSet = new Set(this.mediaItems.map((item) => item.id));
        this.selectedIds = this.selectedIds.filter((id) => idSet.has(id));
      } finally {
        this.loadingMedia = false;
      }
    },
    async fetchDataTree(path = "") {
      this.loadingData = true;
      try {
        const query = new URLSearchParams({ path });
        const data = await this.request(`/api/data-tree?${query.toString()}`);
        this.dataItems = data.items || [];
        this.dataPath = data.path || "";
        this.dataParent = data.parent || "";
      } finally {
        this.loadingData = false;
      }
    },
    switchMode(mode) {
      this.viewMode = mode;
      this.sidebarOpen = false;
      if (mode === "data" && this.canDataBrowse) {
        this.fetchDataTree(this.dataPath || "").catch((error) => {
          this.notify(error.message, "error");
        });
      }
      if (mode === "media") {
        this.fetchMedia().catch((error) => this.notify(error.message, "error"));
      }
    },
    selectCategory(category) {
      this.filters.category = category;
      this.filters.page = 1;
      this.fetchMedia().catch((error) => this.notify(error.message, "error"));
      this.sidebarOpen = false;
    },
    onSearch(query) {
      this.filters.query = query || "";
      this.filters.page = 1;
      this.fetchMedia().catch((error) => this.notify(error.message, "error"));
    },
    onKindChange(kind) {
      this.filters.kind = kind || "";
      this.filters.page = 1;
      this.fetchMedia().catch((error) => this.notify(error.message, "error"));
    },
    onPageChange(page) {
      this.filters.page = page;
      this.fetchMedia().catch((error) => this.notify(error.message, "error"));
    },
    toggleSelect(id) {
      if (this.selectedIds.includes(id)) {
        this.selectedIds = this.selectedIds.filter((item) => item !== id);
      } else {
        this.selectedIds.push(id);
      }
    },
    clearSelection() {
      this.selectedIds = [];
    },
    async openDetail(item) {
      try {
        this.selectedMedia = await this.request(`/api/media/${item.id}`);
        this.drawerVisible = true;
      } catch (error) {
        this.notify(error.message, "error");
      }
    },
    previewItem(item) {
      if (item.kind === "audio") {
        this.audioDockItem = item;
        this.playerVisible = false;
        this.playerItem = null;
        return;
      }
      this.playerList = this.mediaItems.filter(
        (entry) => entry && entry.kind !== "audio"
      );
      this.playerSource = "media";
      this.playerItem = item;
      this.playerVisible = true;
    },
    playerIdentity(item) {
      if (!item) return "";
      if (item.id != null) return `id:${item.id}`;
      if (item.path) return `path:${item.path}`;
      if (item.filename) return `file:${item.filename}`;
      return "";
    },
    playerShift(delta) {
      if (!this.playerItem) return;
      const list = Array.isArray(this.playerList) ? this.playerList : [];
      if (!list.length) return;
      const currentKey = this.playerIdentity(this.playerItem);
      let idx = list.findIndex(
        (entry) => this.playerIdentity(entry) === currentKey
      );
      if (idx < 0) idx = 0;
      const nextIdx = (idx + delta + list.length) % list.length;
      const next = list[nextIdx];
      if (!next) return;
      if (this.playerSource === "data") {
        const directUrl = this.dataFileUrl(next.path);
        this.playerItem = { ...next, directUrl, filename: next.name };
      } else {
        this.playerItem = next;
      }
    },
    playerNext() {
      this.playerShift(1);
    },
    playerPrev() {
      this.playerShift(-1);
    },
    async updateMedia(payload) {
      try {
        const updated = await this.request(`/api/media/${payload.id}`, {
          method: "PATCH",
          body: payload,
        });
        this.notify("已更新媒体信息", "success");
        this.selectedMedia = updated;
        await Promise.all([this.fetchCategories(), this.fetchMedia(), this.fetchStats()]);
      } catch (error) {
        this.notify(error.message, "error");
      }
    },
    async deleteMedia(mediaId) {
      if (!window.confirm("确认删除该媒体吗？")) return;
      try {
        await this.request(`/api/media/${mediaId}`, { method: "DELETE" });
        this.notify("媒体已删除", "success");
        this.drawerVisible = false;
        this.selectedMedia = null;
        await Promise.all([this.fetchMedia(), this.fetchCategories(), this.fetchStats()]);
      } catch (error) {
        this.notify(error.message, "error");
      }
    },
    async batchDelete() {
      if (!this.selectedIds.length) return;
      if (!window.confirm(`确认删除选中的 ${this.selectedIds.length} 个媒体吗？`)) return;
      let success = 0;
      for (const id of this.selectedIds) {
        try {
          await this.request(`/api/media/${id}`, { method: "DELETE" });
          success += 1;
        } catch (_error) {
          // ignore each item error
        }
      }
      this.notify(
        `批量删除完成：成功 ${success} / ${this.selectedIds.length}`,
        success === this.selectedIds.length ? "success" : "warning"
      );
      this.selectedIds = [];
      await Promise.all([this.fetchMedia(), this.fetchCategories(), this.fetchStats()]);
    },
    async createCategory(payload) {
      try {
        await this.request("/api/categories", {
          method: "POST",
          body: payload,
        });
        this.notify(`分类 ${payload.category} 已创建`, "success");
        this.categoryDialogVisible = false;
        await this.fetchCategories();
      } catch (error) {
        this.notify(error.message, "error");
      }
    },
    async pruneCategories() {
      if (!window.confirm("将清理所有无媒体、空目录的分类（保留 default），是否继续？")) return;
      try {
        const result = await this.request("/api/categories/prune", { method: "POST" });
        const count = result.removed_count || 0;
        if (count > 0) {
          const names = (result.removed || []).join("、");
          this.notify(`已清理 ${count} 个空分类${names ? "：" + names : ""}`, "success");
          if (this.filters.category && (result.removed || []).includes(this.filters.category)) {
            this.filters.category = "";
          }
        } else {
          this.notify("没有需要清理的空分类", "info");
        }
        await Promise.all([this.fetchCategories(), this.fetchStats(), this.fetchMedia()]);
      } catch (error) {
        this.notify(error.message, "error");
      }
    },
    uploadFiles(payload) {
      const files = Array.from(payload.files || []);
      if (!files.length) return;
      const maxBytes = Number(this.config.max_file_size_bytes) || 0;
      const maxMb = Number(this.config.max_file_size_mb) || 0;
      const accepted = [];
      const rejected = [];
      for (const file of files) {
        if (maxBytes > 0 && file && Number(file.size) > maxBytes) {
          rejected.push(file);
        } else {
          accepted.push(file);
        }
      }
      if (rejected.length) {
        const names = rejected.map((f) => f.name).join("、");
        this.notify(
          `已跳过 ${rejected.length} 个超过 ${maxMb}MB 的文件：${names}`,
          "warning"
        );
      }
      if (!accepted.length) return;
      const category = payload.category || "default";
      const description = payload.description || "";
      this.uploadPanelOpen = true;
      for (const file of accepted) {
        this.enqueueUpload(file, category, description);
      }
    },
    enqueueUpload(file, category, description) {
      const jobId = `${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
      this.uploadJobs.push({
        id: jobId,
        name: file.name,
        size: file.size,
        category,
        description,
        progress: 0,
        loaded: 0,
        status: "uploading",
        message: "",
        xhr: null,
      });
      this.startUpload(jobId, file);
    },
    getUploadJob(jobId) {
      return this.uploadJobs.find((item) => item && item.id === jobId) || null;
    },
    startUpload(jobId, file) {
      const job = this.getUploadJob(jobId);
      if (!job) return;
      const form = new FormData();
      form.append("category", job.category || "default");
      form.append("description", job.description || "");
      form.append("files", file, file.name);

      const xhr = new XMLHttpRequest();
      job.xhr = xhr;
      xhr.open("POST", "/api/media/upload");
      if (this.token) {
        xhr.setRequestHeader("Authorization", `Bearer ${this.token}`);
      }
      xhr.upload.addEventListener("progress", (event) => {
        if (!event.lengthComputable) return;
        const current = this.getUploadJob(jobId);
        if (!current) return;
        current.loaded = event.loaded;
        current.progress = Math.min(
          100,
          Math.round((event.loaded / event.total) * 100)
        );
      });
      xhr.upload.addEventListener("load", () => {
        const current = this.getUploadJob(jobId);
        if (!current) return;
        if (current.status === "uploading") {
          current.loaded = current.size;
          current.progress = Math.max(current.progress || 0, 99);
        }
      });
      xhr.addEventListener("load", () => {
        const current = this.getUploadJob(jobId);
        if (!current) return;
        let payload = null;
        try {
          payload = JSON.parse(xhr.responseText || "null");
        } catch (_e) {
          payload = null;
        }
        if (xhr.status >= 200 && xhr.status < 300 && payload) {
          const savedList = Array.isArray(payload.saved) ? payload.saved : [];
          const errorsList = Array.isArray(payload.errors) ? payload.errors : [];
          if (savedList.length) {
            current.status = "done";
            current.progress = 100;
            current.loaded = current.size;
            current.message = "已保存";
          } else if (errorsList.length) {
            current.status = "error";
            current.message = this.extractErrorText(errorsList[0], file.name);
            this.notify(`${file.name} 上传失败：${current.message}`, "error");
          } else {
            current.status = "error";
            current.message = "未返回结果";
          }
          if (savedList.length || errorsList.length) {
            this.scheduleMediaRefresh();
          }
        } else {
          let detail = "上传失败";
          if (payload && payload.detail) detail = payload.detail;
          else if (xhr.statusText) detail = xhr.statusText;
          current.status = "error";
          current.message = detail;
          this.notify(`${file.name} 上传失败：${detail}`, "error");
        }
        this.scheduleAutoClearFinished();
      });
      xhr.addEventListener("error", () => {
        const current = this.getUploadJob(jobId);
        if (!current) return;
        current.status = "error";
        current.message = "网络错误";
        this.notify(`${file.name} 上传失败：网络错误`, "error");
        this.scheduleAutoClearFinished();
      });
      xhr.addEventListener("abort", () => {
        const current = this.getUploadJob(jobId);
        if (!current) return;
        if (current.status !== "done") {
          current.status = "cancelled";
          current.message = "已取消";
        }
        this.scheduleAutoClearFinished();
      });
      xhr.send(form);
    },
    scheduleAutoClearFinished() {
      if (this._uploadAutoClearTimer) {
        clearTimeout(this._uploadAutoClearTimer);
      }
      this._uploadAutoClearTimer = setTimeout(() => {
        this._uploadAutoClearTimer = null;
        if (this.uploadJobs.some((job) => job && job.status === "uploading")) {
          return;
        }
        const hasError = this.uploadJobs.some(
          (job) => job && (job.status === "error" || job.status === "cancelled")
        );
        if (hasError) return;
        this.uploadJobs = [];
        this.uploadPanelOpen = false;
      }, 2400);
    },
    extractErrorText(raw, fallbackName) {
      const text = String(raw || "").trim();
      if (!text) return "未知错误";
      const prefix = `${fallbackName}: `;
      if (text.startsWith(prefix)) return text.slice(prefix.length);
      const colonIdx = text.indexOf(": ");
      if (colonIdx > 0 && text.slice(0, colonIdx) === fallbackName) {
        return text.slice(colonIdx + 2);
      }
      return text;
    },
    scheduleMediaRefresh() {
      if (this._mediaRefreshTimer) {
        clearTimeout(this._mediaRefreshTimer);
      }
      this._mediaRefreshTimer = setTimeout(() => {
        this._mediaRefreshTimer = null;
        Promise.all([
          this.fetchMedia(),
          this.fetchCategories(),
          this.fetchStats(),
        ]).catch((error) => this.notify(error.message, "error"));
      }, 400);
    },
    cancelUpload(jobId) {
      const job = this.uploadJobs.find((item) => item.id === jobId);
      if (!job) return;
      if (job.xhr && job.status === "uploading") {
        try {
          job.xhr.abort();
        } catch (_e) {
          // ignore
        }
      }
    },
    dismissUpload(jobId) {
      this.uploadJobs = this.uploadJobs.filter((item) => item.id !== jobId);
    },
    clearFinishedUploads() {
      this.uploadJobs = this.uploadJobs.filter(
        (item) => item.status === "uploading"
      );
      if (!this.uploadJobs.length) {
        this.uploadPanelOpen = false;
      }
    },
    toggleUploadPanel() {
      this.uploadPanelOpen = !this.uploadPanelOpen;
    },
    async saveByUrl(payload) {
      try {
        await this.request("/api/media/save-url", {
          method: "POST",
          body: payload,
        });
        this.notify("远程媒体已保存", "success");
        await Promise.all([this.fetchMedia(), this.fetchCategories(), this.fetchStats()]);
      } catch (error) {
        this.notify(error.message, "error");
      }
    },
    absoluteUrl(url) {
      if (!url) return "";
      try {
        return new URL(url, window.location.origin).toString();
      } catch (_e) {
        return url;
      }
    },
    shareAbsoluteUrl(url) {
      if (!url) return "";
      if (/^https?:\/\//i.test(url)) return url;
      const base = String(this.config.public_base_url || "").trim() || window.location.origin;
      try {
        return new URL(url, base).toString();
      } catch (_e) {
        return url;
      }
    },
    async copyText(text) {
      if (!text) throw new Error("内容为空");
      if (
        typeof navigator !== "undefined" &&
        navigator.clipboard &&
        typeof navigator.clipboard.writeText === "function" &&
        window.isSecureContext
      ) {
        try {
          await navigator.clipboard.writeText(text);
          return true;
        } catch (_e) {
          // fall through to legacy fallback
        }
      }
      const textarea = document.createElement("textarea");
      textarea.value = text;
      textarea.setAttribute("readonly", "");
      textarea.style.position = "fixed";
      textarea.style.top = "0";
      textarea.style.left = "0";
      textarea.style.width = "1px";
      textarea.style.height = "1px";
      textarea.style.padding = "0";
      textarea.style.border = "none";
      textarea.style.outline = "none";
      textarea.style.boxShadow = "none";
      textarea.style.background = "transparent";
      textarea.style.opacity = "0";
      document.body.appendChild(textarea);
      textarea.focus({ preventScroll: true });
      textarea.select();
      textarea.setSelectionRange(0, text.length);
      let ok = false;
      try {
        ok = document.execCommand("copy");
      } catch (_e) {
        ok = false;
      }
      document.body.removeChild(textarea);
      if (!ok) {
        throw new Error("当前环境不支持自动复制，请手动复制");
      }
      return true;
    },
    async copyMediaLink(mediaId) {
      try {
        const detail = await this.request(`/api/media/${mediaId}`);
        const raw = detail.public_url || "";
        if (!raw) throw new Error("未返回可复制链接");
        const text = this.shareAbsoluteUrl(raw);
        await this.copyText(text);
        this.notify("链接已复制到剪贴板", "success");
      } catch (error) {
        this.notify(error.message, "error");
      }
    },
    async copyPreviewLink(payload) {
      if (!payload) return;
      if (payload.id != null) {
        return this.copyMediaLink(payload.id);
      }
      if (payload.url) {
        try {
          const text = this.shareAbsoluteUrl(payload.url);
          if (!text) throw new Error("链接为空");
          await this.copyText(text);
          this.notify("链接已复制到剪贴板", "success");
        } catch (error) {
          this.notify(error.message, "error");
        }
      }
    },
    async openDataDir(path) {
      await this.fetchDataTree(path);
    },
    async openDataParent() {
      await this.fetchDataTree(this.dataParent || "");
    },
    dataFileUrl(path, { download = false } = {}) {
      const params = new URLSearchParams();
      params.set("path", path);
      if (this.dataToken) params.set("token", this.dataToken);
      if (download) params.set("download", "1");
      return `/api/data-file?${params.toString()}`;
    },
    openDataFile(item) {
      const directUrl = this.dataFileUrl(item.path);
      if (item.kind === "image" || item.kind === "video" || item.kind === "audio") {
        const previewItem = { ...item, directUrl, filename: item.name };
        if (item.kind === "audio") {
          this.audioDockItem = previewItem;
          this.playerVisible = false;
          this.playerItem = null;
          return;
        }
        this.playerList = (this.dataItems || []).filter(
          (entry) =>
            entry &&
            !entry.is_dir &&
            (entry.kind === "image" || entry.kind === "video")
        );
        this.playerSource = "data";
        this.playerItem = previewItem;
        this.playerVisible = true;
        return;
      }
      this.openDataTextPreview(item);
    },
    async openDataTextPreview(item) {
      this.dataPreviewLoading = true;
      this.dataPreview = {
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
        downloadUrl: this.dataFileUrl(item.path, { download: true }),
      };
      try {
        const query = new URLSearchParams({ path: item.path });
        const data = await this.request(`/api/data-text?${query.toString()}`);
        this.dataPreview = {
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
          downloadUrl: this.dataFileUrl(data.path || item.path, { download: true }),
        };
      } catch (error) {
        this.notify(error.message, "error");
        this.dataPreview = {
          ...this.dataPreview,
          loading: false,
          isText: false,
          content: "",
          message: error.message,
        };
      } finally {
        this.dataPreviewLoading = false;
      }
    },
    closeDataPreview() {
      this.dataPreview = null;
    },
    async copyDataPreviewContent() {
      if (!this.dataPreview || !this.dataPreview.content) return;
      try {
        await this.copyText(this.dataPreview.content);
        this.notify("内容已复制到剪贴板", "success");
      } catch (error) {
        this.notify(error.message, "error");
      }
    },
    downloadDataFile(item) {
      const url = this.dataFileUrl(item.path, { download: true });
      const link = document.createElement("a");
      link.href = url;
      link.download = item.name || "";
      link.rel = "noopener";
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
    },
    refreshAll() {
      const jobs =
        this.viewMode === "media"
          ? [this.fetchCategories(), this.fetchMedia(), this.fetchStats()]
          : [this.fetchDataTree(this.dataPath)];
      Promise.all(jobs)
        .then(() => this.notify("数据已刷新", "success"))
        .catch((error) => this.notify(error.message, "error"));
    },
  },
  template: `
    <div class="app-root">
      <LoginView
        v-if="!token"
        :loading="loginLoading"
        :error="loginError"
        :theme="theme"
        @login="login"
        @toggle-theme="toggleTheme"
      />
      <template v-else>
        <header class="topbar">
          <div class="topbar-left">
            <button
              class="icon mobile-only"
              @click="sidebarOpen = !sidebarOpen"
              title="菜单"
            >
              <Icon name="menu" :size="16" />
            </button>
            <div class="brand">
              <div class="brand-logo brand-logo-img">
                <img src="/static/logo.svg" alt="Astrbot Media Portal" />
              </div>
              <div class="brand-text">
                <strong>Astrbot Media Portal</strong>
                <small>多媒体管理控制台</small>
              </div>
            </div>
            <span v-if="selectedCount" class="topbar-selection">
              <Icon name="check-check" :size="12" />
              {{ selectedCount }}
            </span>
          </div>
          <div class="topbar-actions">
            <button class="icon" @click="toggleTheme" :title="theme === 'dark' ? '切换浅色' : '切换深色'">
              <Icon :name="theme === 'dark' ? 'sun' : 'moon'" :size="16" />
            </button>
            <button class="icon" @click="refreshAll" title="刷新">
              <Icon name="refresh-cw" :size="16" />
            </button>
            <button class="ghost" @click="logout()" title="退出">
              <Icon name="log-out" :size="15" />
              <span class="hide-mobile">退出</span>
            </button>
          </div>
        </header>

        <div
          v-if="sidebarOpen"
          class="sidebar-backdrop mobile-only"
          @click="sidebarOpen = false"
        ></div>

        <main class="layout">
          <div class="sidebar-wrap" :class="{ open: sidebarOpen }">
            <Sidebar
              :categories="categories"
              :active-category="filters.category"
              :view-mode="viewMode"
              :total-count="mediaStats.total_count || 0"
              :can-data-browse="canDataBrowse"
              @switch-mode="switchMode"
              @select-category="selectCategory"
              @request-create-category="categoryDialogVisible = true"
              @prune-categories="pruneCategories"
            />
          </div>

          <section class="content">
            <MediaGrid
              v-if="viewMode === 'media'"
              :items="mediaItems"
              :loading="loadingMedia"
              :query="filters.query"
              :kind="filters.kind"
              :page="filters.page"
              :total-pages="pagination.totalPages"
              :total-count="pagination.total"
              :selected-ids="selectedIds"
              :readonly-token="readonlyToken"
              :stats="mediaStats"
              :active-category="filters.category"
              :categories="categories"
              @search="onSearch"
              @change-kind="onKindChange"
              @select-category="selectCategory"
              @toggle-select="toggleSelect"
              @preview="previewItem"
              @detail="openDetail"
              @open-upload="uploadMode = 'file'; uploadVisible = true"
              @page-change="onPageChange"
              @clear-selection="clearSelection"
              @batch-delete="batchDelete"
              @copy-link="copyMediaLink"
            />

            <DataBrowser
              v-else-if="canDataBrowse"
              :path="dataPath"
              :parent="dataParent"
              :items="dataItems"
              :loading="loadingData"
              @open-dir="openDataDir"
              @open-file="openDataFile"
              @go-parent="openDataParent"
              @navigate="openDataDir"
            />
            <section v-else class="panel empty">
              <div class="illus"><Icon name="shield-off" :size="32" /></div>
              <strong>Data 目录未开放</strong>
              <span>配置中设置 <code class="mono">webui.expose_astrbot_data</code> 为 true 来启用。</span>
            </section>
          </section>

          <MediaDrawer
            :visible="drawerVisible"
            :media="selectedMedia"
            :categories="categories"
            :readonly-token="readonlyToken"
            @close="drawerVisible = false"
            @update="updateMedia"
            @delete="deleteMedia"
            @copy-link="copyMediaLink"
            @preview="previewItem"
          />
        </main>

        <UploadDialog
          :visible="uploadVisible"
          :categories="categories"
          :active-category="filters.category"
          :initial-mode="uploadMode"
          :max-file-size-mb="config.max_file_size_mb"
          @close="uploadVisible = false"
          @upload-files="uploadFiles"
          @save-url="saveByUrl"
        />

        <PlayerModal
          :visible="playerVisible"
          :item="playerItem"
          :readonly-token="readonlyToken"
          :can-navigate="playerList.length > 1"
          @close="playerVisible = false"
          @next="playerNext"
          @prev="playerPrev"
          @copy-link="copyPreviewLink"
        />

        <AudioDock
          :item="audioDockItem"
          :readonly-token="readonlyToken"
          @close="audioDockItem = null"
        />

        <DataFileModal
          :preview="dataPreview"
          @close="closeDataPreview"
          @copy="copyDataPreviewContent"
          @download="downloadDataFile"
        />

        <CategoryCreateDialog
          :visible="categoryDialogVisible"
          :existing="categories"
          @close="categoryDialogVisible = false"
          @submit="createCategory"
        />

        <UploadProgress
          :jobs="uploadJobs"
          :open="uploadPanelOpen"
          @toggle="toggleUploadPanel"
          @cancel="cancelUpload"
          @dismiss="dismissUpload"
          @clear-finished="clearFinishedUploads"
        />

        <Toast :messages="toasts" />
      </template>
    </div>
  `,
}).mount("#app");

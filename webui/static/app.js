import { LoginView } from "./components/LoginView.js";
import { Sidebar } from "./components/Sidebar.js";
import { MediaGrid } from "./components/MediaGrid.js";
import { MediaDrawer } from "./components/MediaDrawer.js";
import { UploadDialog } from "./components/UploadDialog.js";
import { PlayerModal } from "./components/PlayerModal.js";
import { DataBrowser } from "./components/DataBrowser.js";
import { Toast } from "./components/Toast.js";
import { AudioDock } from "./components/AudioDock.js";

const { createApp } = Vue;

createApp({
  components: {
    LoginView,
    Sidebar,
    MediaGrid,
    MediaDrawer,
    UploadDialog,
    PlayerModal,
    DataBrowser,
    Toast,
    AudioDock,
  },
  data() {
    return {
      token: localStorage.getItem("media_portal_token") || "",
      readonlyToken: localStorage.getItem("media_portal_readonly_token") || "",
      loginLoading: false,
      loginError: "",
      loadingMedia: false,
      loadingData: false,
      sidebarOpen: false,
      viewMode: "media",
      categories: [],
      mediaItems: [],
      selectedIds: [],
      selectedMedia: null,
      drawerVisible: false,
      uploadVisible: false,
      uploadMode: "file",
      playerVisible: false,
      playerItem: null,
      audioDockItem: null,
      dataItems: [],
      dataPath: "",
      dataParent: "",
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
    if (this.token) {
      this.bootstrap().catch((error) => {
        this.notify(`初始化失败: ${error.message}`, "error");
        this.logout(false);
      });
    }
  },
  methods: {
    notify(text, type = "info") {
      const id = `${Date.now()}_${Math.random()}`;
      this.toasts.push({ id, text, type });
      setTimeout(() => {
        this.toasts = this.toasts.filter((item) => item.id !== id);
      }, 2600);
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
      const requestInit = {
        method,
        headers: finalHeaders,
      };

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
      await this.fetchCategories();
      await this.fetchMedia();
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
        localStorage.setItem("media_portal_token", this.token);
        localStorage.setItem("media_portal_readonly_token", this.readonlyToken);
        await this.bootstrap();
        this.notify("登录成功", "success");
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
      localStorage.removeItem("media_portal_token");
      localStorage.removeItem("media_portal_readonly_token");
      this.categories = [];
      this.mediaItems = [];
      this.selectedIds = [];
      this.selectedMedia = null;
      this.drawerVisible = false;
      if (showToast) {
        this.notify("已退出登录", "info");
      }
    },
    async fetchConfig() {
      const data = await this.request("/api/config");
      this.config = data;
      if (data.readonly_token) {
        this.readonlyToken = data.readonly_token;
        localStorage.setItem("media_portal_readonly_token", this.readonlyToken);
      }
    },
    async fetchCategories() {
      const data = await this.request("/api/categories");
      this.categories = data.items || [];
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
        this.fetchMedia().catch((error) => {
          this.notify(error.message, "error");
        });
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
      this.playerItem = item;
      this.playerVisible = true;
    },
    playerNext() {
      if (!this.playerItem) return;
      const idx = this.mediaItems.findIndex((item) => item.id === this.playerItem.id);
      if (idx < 0) return;
      const next = this.mediaItems[(idx + 1) % this.mediaItems.length];
      this.playerItem = next;
    },
    playerPrev() {
      if (!this.playerItem) return;
      const idx = this.mediaItems.findIndex((item) => item.id === this.playerItem.id);
      if (idx < 0) return;
      const prev = this.mediaItems[(idx - 1 + this.mediaItems.length) % this.mediaItems.length];
      this.playerItem = prev;
    },
    async updateMedia(payload) {
      try {
        const updated = await this.request(`/api/media/${payload.id}`, {
          method: "PATCH",
          body: payload,
        });
        this.notify("更新成功", "success");
        this.selectedMedia = updated;
        await this.fetchCategories();
        await this.fetchMedia();
      } catch (error) {
        this.notify(error.message, "error");
      }
    },
    async deleteMedia(mediaId) {
      if (!window.confirm("确认删除该媒体吗？")) {
        return;
      }
      try {
        await this.request(`/api/media/${mediaId}`, { method: "DELETE" });
        this.notify("删除成功", "success");
        this.drawerVisible = false;
        this.selectedMedia = null;
        await this.fetchMedia();
        await this.fetchCategories();
      } catch (error) {
        this.notify(error.message, "error");
      }
    },
    async batchDelete() {
      if (!this.selectedIds.length) return;
      if (!window.confirm(`确认删除选中的 ${this.selectedIds.length} 个媒体吗？`)) {
        return;
      }
      let success = 0;
      for (const id of this.selectedIds) {
        try {
          await this.request(`/api/media/${id}`, { method: "DELETE" });
          success += 1;
        } catch (_error) {
          // ignore each item error
        }
      }
      this.notify(`批量删除完成，成功 ${success}/${this.selectedIds.length}`, "info");
      this.selectedIds = [];
      await this.fetchMedia();
      await this.fetchCategories();
    },
    async createCategory(payload) {
      try {
        await this.request("/api/categories", {
          method: "POST",
          body: payload,
        });
        this.notify("分类已创建", "success");
        await this.fetchCategories();
      } catch (error) {
        this.notify(error.message, "error");
      }
    },
    async uploadFiles(payload) {
      try {
        const form = new FormData();
        form.append("category", payload.category || "default");
        form.append("description", payload.description || "");
        for (const file of payload.files || []) {
          form.append("files", file);
        }
        const result = await this.request("/api/media/upload", {
          method: "POST",
          body: form,
          form: true,
        });
        const savedCount = (result.saved || []).length;
        const errorsCount = (result.errors || []).length;
        this.notify(`上传完成：成功 ${savedCount}，失败 ${errorsCount}`, "info");
        await this.fetchMedia();
        await this.fetchCategories();
      } catch (error) {
        this.notify(error.message, "error");
      }
    },
    async saveByUrl(payload) {
      try {
        await this.request("/api/media/save-url", {
          method: "POST",
          body: payload,
        });
        this.notify("URL 保存成功", "success");
        await this.fetchMedia();
        await this.fetchCategories();
      } catch (error) {
        this.notify(error.message, "error");
      }
    },
    async copyMediaLink(mediaId) {
      try {
        const detail = await this.request(`/api/media/${mediaId}`);
        const text = detail.public_url || "";
        if (!text) throw new Error("未返回可复制链接");
        await navigator.clipboard.writeText(text);
        this.notify("链接已复制", "success");
      } catch (error) {
        this.notify(error.message, "error");
      }
    },
    async openDataDir(path) {
      await this.fetchDataTree(path);
    },
    async openDataParent() {
      await this.fetchDataTree(this.dataParent || "");
    },
    openDataFile(item) {
      const directUrl = `/api/data-file?path=${encodeURIComponent(item.path)}&token=${encodeURIComponent(
        this.readonlyToken
      )}`;
      if (item.kind === "image" || item.kind === "video" || item.kind === "audio") {
        const previewItem = {
          ...item,
          directUrl,
          filename: item.name,
        };
        if (item.kind === "audio") {
          this.audioDockItem = previewItem;
          this.playerVisible = false;
          this.playerItem = null;
          return;
        }
        this.playerItem = previewItem;
        this.playerVisible = true;
        return;
      }
      window.open(directUrl, "_blank");
    },
  },
  template: `
    <div class="app-root">
      <LoginView
        v-if="!token"
        :loading="loginLoading"
        :error="loginError"
        @login="login"
      />
      <template v-else>
        <header class="topbar">
          <div class="topbar-left">
            <button class="mobile-only" @click="sidebarOpen = !sidebarOpen">☰</button>
            <h1>Media Portal</h1>
            <span class="muted">已选择 {{ selectedCount }} 项</span>
          </div>
          <div class="topbar-actions">
            <button @click="fetchCategories(); fetchMedia();">刷新</button>
            <button @click="logout()">退出</button>
          </div>
        </header>

        <main class="layout">
          <div class="sidebar-wrap" :class="{ open: sidebarOpen }">
            <Sidebar
              :categories="categories"
              :active-category="filters.category"
              :view-mode="viewMode"
              @switch-mode="switchMode"
              @select-category="selectCategory"
              @create-category="createCategory"
              @refresh="viewMode === 'media' ? fetchCategories() : fetchDataTree(dataPath)"
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
              :selected-ids="selectedIds"
              :readonly-token="readonlyToken"
              @search="onSearch"
              @change-kind="onKindChange"
              @toggle-select="toggleSelect"
              @preview="previewItem"
              @detail="openDetail"
              @open-upload="uploadMode = 'file'; uploadVisible = true"
              @open-save-url="uploadMode = 'url'; uploadVisible = true"
              @page-change="onPageChange"
              @clear-selection="clearSelection"
              @batch-delete="batchDelete"
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
              @refresh="fetchDataTree(dataPath)"
            />
            <section v-else class="empty">当前配置未开放 data 目录浏览。</section>
          </section>

          <MediaDrawer
            :visible="drawerVisible"
            :media="selectedMedia"
            :categories="categories"
            @close="drawerVisible = false"
            @update="updateMedia"
            @delete="deleteMedia"
            @copy-link="copyMediaLink"
          />
        </main>

        <UploadDialog
          :visible="uploadVisible"
          :categories="categories"
          :active-category="filters.category"
          :initial-mode="uploadMode"
          @close="uploadVisible = false"
          @upload-files="uploadFiles"
          @save-url="saveByUrl"
        />

        <PlayerModal
          :visible="playerVisible"
          :item="playerItem"
          :readonly-token="readonlyToken"
          @close="playerVisible = false"
          @next="playerNext"
          @prev="playerPrev"
        />

        <AudioDock
          :item="audioDockItem"
          :readonly-token="readonlyToken"
          @close="audioDockItem = null"
        />

        <Toast :messages="toasts" />
      </template>
    </div>
  `,
}).mount("#app");

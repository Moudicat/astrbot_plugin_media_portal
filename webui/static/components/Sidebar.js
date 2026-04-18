import { Icon } from "./Icon.js";

export const Sidebar = {
  name: "Sidebar",
  components: { Icon },
  props: {
    categories: { type: Array, default: () => [] },
    activeCategory: { type: String, default: "" },
    viewMode: { type: String, default: "media" },
    totalCount: { type: Number, default: 0 },
    canDataBrowse: { type: Boolean, default: true },
  },
  emits: [
    "switch-mode",
    "select-category",
    "request-create-category",
    "close",
  ],
  methods: {
    addCategory() {
      this.$emit("request-create-category");
    },
    categoryIcon(name) {
      const lower = (name || "").toLowerCase();
      if (lower.includes("image") || lower.includes("图")) return "image";
      if (lower.includes("video") || lower.includes("视频") || lower.includes("短视频"))
        return "film";
      if (lower.includes("audio") || lower.includes("音乐") || lower.includes("音频"))
        return "music";
      if (lower.includes("doc") || lower.includes("文档")) return "file-text";
      if (lower.includes("meme") || lower.includes("表情")) return "sticker";
      return "folder";
    },
  },
  template: `
    <aside class="sidebar">
      <div class="sidebar-tabs" role="tablist">
        <button
          class="sidebar-tab"
          :class="{ active: viewMode === 'media' }"
          @click="$emit('switch-mode', 'media')"
        >
          <Icon name="library" :size="15" />
          媒体库
        </button>
        <button
          class="sidebar-tab"
          :class="{ active: viewMode === 'data' }"
          @click="$emit('switch-mode', 'data')"
          :disabled="!canDataBrowse"
          :title="canDataBrowse ? '浏览 AstrBot data 目录' : '该功能未在配置中开启'"
        >
          <Icon name="folder-tree" :size="15" />
          Data 浏览
        </button>
      </div>

      <div v-if="viewMode === 'media'" class="sidebar-section">
        <div class="sidebar-header">
          <h3>分类 · {{ categories.length }}</h3>
          <div class="sidebar-tools">
            <button class="icon sm" @click="addCategory" title="新增分类">
              <Icon name="folder-plus" :size="14" />
            </button>
          </div>
        </div>
        <ul class="category-list">
          <li
            class="category-item"
            :class="{ active: activeCategory === '' }"
            @click="$emit('select-category', '')"
          >
            <span class="icon-wrap"><Icon name="layers" :size="14" /></span>
            <span class="label">全部媒体</span>
            <span class="count">{{ totalCount }}</span>
          </li>
          <li
            v-for="item in categories"
            :key="item.category"
            class="category-item"
            :class="{ active: activeCategory === item.category }"
            @click="$emit('select-category', item.category)"
            :title="item.description || item.category"
          >
            <span class="icon-wrap"><Icon :name="categoryIcon(item.category)" :size="14" /></span>
            <span class="label">{{ item.category }}</span>
            <span class="count">{{ item.count }}</span>
          </li>
        </ul>
      </div>

      <div v-else class="sidebar-section">
        <div class="sidebar-header">
          <h3>AstrBot Data</h3>
        </div>
        <p class="muted" style="padding: 0 4px">
          只读浏览 <code class="mono">/astrbot/data</code> 目录下的文件。
        </p>
      </div>

    </aside>
  `,
};

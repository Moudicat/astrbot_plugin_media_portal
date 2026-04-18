import { Icon } from "./Icon.js";
import { MediaCard } from "./MediaCard.js";

export const MediaGrid = {
  name: "MediaGrid",
  components: { Icon, MediaCard },
  props: {
    items: { type: Array, default: () => [] },
    loading: { type: Boolean, default: false },
    selectedIds: { type: Array, default: () => [] },
    query: { type: String, default: "" },
    kind: { type: String, default: "" },
    page: { type: Number, default: 1 },
    totalPages: { type: Number, default: 0 },
    totalCount: { type: Number, default: 0 },
    readonlyToken: { type: String, default: "" },
    stats: { type: Object, default: () => ({}) },
    activeCategory: { type: String, default: "" },
    categories: { type: Array, default: () => [] },
  },
  emits: [
    "search",
    "change-kind",
    "toggle-select",
    "preview",
    "detail",
    "open-upload",
    "page-change",
    "clear-selection",
    "batch-delete",
    "batch-change-category",
    "copy-link",
    "select-category",
  ],
  data() {
    return {
      localQuery: this.query,
    };
  },
  watch: {
    query(value) {
      this.localQuery = value;
    },
  },
  computed: {
    statCards() {
      const categories = this.stats?.categories || [];
      const totalSize = this.stats?.total_size_human || this.stats?.total_size || "-";
      const kindCount = (target) =>
        (this.stats?.by_kind && this.stats.by_kind[target]) || 0;
      return [
        {
          key: "total",
          label: "媒体总数",
          value: this.stats?.total_count ?? this.totalCount ?? 0,
          icon: "library",
          tone: "primary",
        },
        {
          key: "image",
          label: "图片",
          value: kindCount("image"),
          icon: "image",
          tone: "violet",
        },
        {
          key: "video",
          label: "视频",
          value: kindCount("video"),
          icon: "film",
          tone: "info",
        },
        {
          key: "audio",
          label: "音频",
          value: kindCount("audio"),
          icon: "music",
          tone: "accent",
        },
        {
          key: "cat",
          label: "分类",
          value: categories.length,
          icon: "folder",
          tone: "warning",
        },
        {
          key: "size",
          label: "占用空间",
          value: totalSize,
          icon: "database",
          tone: "primary",
        },
      ];
    },
    kindTabs() {
      return [
        { id: "", label: "全部", icon: "layers" },
        { id: "image", label: "图片", icon: "image" },
        { id: "video", label: "视频", icon: "film" },
        { id: "audio", label: "音频", icon: "music" },
      ];
    },
  },
  methods: {
    submitSearch() {
      this.$emit("search", this.localQuery);
      // 触屏设备上提交后主动失焦以收起虚拟键盘
      if (this.$refs.searchInput && typeof this.$refs.searchInput.blur === "function") {
        this.$refs.searchInput.blur();
      }
    },
    clearSearch() {
      this.localQuery = "";
      this.$emit("search", "");
      if (this.$refs.searchInput && typeof this.$refs.searchInput.focus === "function") {
        this.$refs.searchInput.focus();
      }
    },
    pickKind(kind) {
      this.$emit("change-kind", kind);
    },
  },
  template: `
    <section style="display: flex; flex-direction: column; gap: 14px">
      <div class="panel stat-grid">
        <div
          class="stat-card"
          v-for="card in statCards"
          :key="card.key"
          :data-tone="card.tone"
        >
          <div class="avatar"><Icon :name="card.icon" :size="18" /></div>
          <div class="meta">
            <small>{{ card.label }}</small>
            <strong>{{ card.value }}</strong>
          </div>
        </div>
      </div>

      <div class="panel" style="display: flex; flex-direction: column; gap: 10px">
        <div class="toolbar">
          <div class="toolbar-search">
            <div class="input-wrap">
              <span class="icon-slot"><Icon name="search" :size="16" /></span>
              <input
                ref="searchInput"
                v-model="localQuery"
                @keyup.enter="submitSearch"
                type="search"
                inputmode="search"
                enterkeyhint="search"
                autocomplete="off"
                placeholder="搜索文件名 / 描述 / 标签"
              />
              <button
                v-if="localQuery"
                class="icon sm input-clear"
                type="button"
                @click="clearSearch"
                title="清除搜索"
                aria-label="清除搜索"
              >
                <Icon name="x" :size="14" />
              </button>
            </div>
            <button
              class="primary search-submit"
              type="button"
              @click="submitSearch"
              title="搜索"
              aria-label="搜索"
            >
              <Icon name="search" :size="15" />
              <span class="hide-mobile">搜索</span>
            </button>
          </div>
          <div class="toolbar-actions">
            <button class="accent" @click="$emit('open-upload')" title="上传文件 / URL 保存">
              <Icon name="upload" :size="15" />
              <span class="hide-mobile">上传</span>
            </button>
          </div>
        </div>

        <div class="kind-tabs">
          <button
            v-for="tab in kindTabs"
            :key="tab.id"
            class="chip"
            :class="{ active: kind === tab.id }"
            @click="pickKind(tab.id)"
          >
            <Icon :name="tab.icon" :size="13" />
            {{ tab.label }}
          </button>
          <span v-if="activeCategory" class="chip active hide-mobile" style="margin-left: auto">
            <Icon name="folder" :size="13" />
            {{ activeCategory }}
          </span>
        </div>

        <div v-if="categories.length" class="category-tabs mobile-only">
          <button
            class="chip"
            :class="{ active: activeCategory === '' }"
            @click="$emit('select-category', '')"
          >
            <Icon name="layers" :size="13" />
            全部
          </button>
          <button
            v-for="cat in categories"
            :key="cat.category"
            class="chip"
            :class="{ active: activeCategory === cat.category }"
            @click="$emit('select-category', cat.category)"
            :title="cat.description || cat.category"
          >
            <Icon name="folder" :size="13" />
            {{ cat.category }}
            <span class="chip-count">{{ cat.count }}</span>
          </button>
        </div>

        <div v-if="selectedIds.length" class="selection-bar">
          <span>
            <Icon name="check-check" :size="14" style="vertical-align: -2px" />
            已选择 <strong>{{ selectedIds.length }}</strong> 个媒体
          </span>
          <div class="actions">
            <button class="sm" @click="$emit('clear-selection')">
              <Icon name="x" :size="14" /> 取消选择
            </button>
            <button class="sm" @click="$emit('batch-change-category')" title="批量移动到分类">
              <Icon name="folder-input" :size="14" /> 批量分类
            </button>
            <button class="danger sm" @click="$emit('batch-delete')">
              <Icon name="trash-2" :size="14" /> 批量删除
            </button>
          </div>
        </div>
      </div>

      <div v-if="loading" class="skeleton-grid">
        <div v-for="n in 8" :key="n" class="skeleton-card">
          <div class="sk-media"></div>
          <div class="sk-line"></div>
          <div class="sk-line short"></div>
        </div>
      </div>

      <div v-else-if="!items.length" class="empty panel">
        <div class="illus"><Icon name="package-open" :size="36" /></div>
        <strong>这里还没有媒体</strong>
        <span>试试上传一个文件，或在上传弹窗中切换 URL 保存一个远程媒体。</span>
        <div style="display: flex; gap: 8px; margin-top: 6px">
          <button class="primary" @click="$emit('open-upload')">
            <Icon name="upload" :size="15" /> 上传 / URL 保存
          </button>
        </div>
      </div>

      <div v-else class="media-grid">
        <MediaCard
          v-for="item in items"
          :key="item.id"
          :item="item"
          :selected="selectedIds.includes(item.id)"
          :readonly-token="readonlyToken"
          @toggle-select="$emit('toggle-select', $event)"
          @preview="$emit('preview', $event)"
          @detail="$emit('detail', $event)"
          @copy-link="$emit('copy-link', $event)"
        />
      </div>

      <footer class="pager" v-if="totalPages > 0">
        <button class="icon sm" :disabled="page <= 1" @click="$emit('page-change', page - 1)">
          <Icon name="chevron-left" :size="15" />
        </button>
        <span>第 <strong>{{ page }}</strong> / {{ totalPages }} 页 · 共 {{ totalCount }} 条</span>
        <button class="icon sm" :disabled="page >= totalPages" @click="$emit('page-change', page + 1)">
          <Icon name="chevron-right" :size="15" />
        </button>
      </footer>
    </section>
  `,
};

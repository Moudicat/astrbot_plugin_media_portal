import { MediaCard } from "./MediaCard.js";

export const MediaGrid = {
  name: "MediaGrid",
  components: { MediaCard },
  props: {
    items: { type: Array, default: () => [] },
    loading: { type: Boolean, default: false },
    selectedIds: { type: Array, default: () => [] },
    query: { type: String, default: "" },
    kind: { type: String, default: "" },
    page: { type: Number, default: 1 },
    totalPages: { type: Number, default: 0 },
    readonlyToken: { type: String, default: "" },
  },
  emits: [
    "search",
    "change-kind",
    "toggle-select",
    "preview",
    "detail",
    "open-upload",
    "open-save-url",
    "page-change",
    "clear-selection",
    "batch-delete",
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
  methods: {
    submitSearch() {
      this.$emit("search", this.localQuery);
    },
    pickKind(kind) {
      this.$emit("change-kind", kind);
    },
  },
  template: `
    <section class="media-grid-wrap">
      <header class="toolbar">
        <div class="toolbar-search">
          <input
            v-model="localQuery"
            @keyup.enter="submitSearch"
            placeholder="搜索文件名/描述"
          />
          <button @click="submitSearch">搜索</button>
        </div>
        <div class="toolbar-actions">
          <button @click="$emit('open-upload')">上传文件</button>
          <button @click="$emit('open-save-url')">保存 URL</button>
          <button @click="$emit('clear-selection')" :disabled="!selectedIds.length">清空选择</button>
          <button @click="$emit('batch-delete')" :disabled="!selectedIds.length">批量删除</button>
        </div>
      </header>

      <div class="kind-tabs">
        <button :class="{ active: kind === '' }" @click="pickKind('')">全部</button>
        <button :class="{ active: kind === 'image' }" @click="pickKind('image')">图片</button>
        <button :class="{ active: kind === 'video' }" @click="pickKind('video')">视频</button>
        <button :class="{ active: kind === 'audio' }" @click="pickKind('audio')">音频</button>
      </div>

      <div v-if="loading" class="loading">加载中...</div>
      <div v-else-if="!items.length" class="empty">暂无媒体，试试上传或切换分类。</div>
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
        />
      </div>

      <footer class="pager" v-if="totalPages > 0">
        <button :disabled="page <= 1" @click="$emit('page-change', page - 1)">上一页</button>
        <span>第 {{ page }} / {{ totalPages }} 页</span>
        <button :disabled="page >= totalPages" @click="$emit('page-change', page + 1)">下一页</button>
      </footer>
    </section>
  `,
};

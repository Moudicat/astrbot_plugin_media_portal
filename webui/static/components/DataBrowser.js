import { Icon } from "./Icon.js";

export const DataBrowser = {
  name: "DataBrowser",
  components: { Icon },
  props: {
    path: { type: String, default: "" },
    parent: { type: String, default: "" },
    items: { type: Array, default: () => [] },
    loading: { type: Boolean, default: false },
  },
  emits: ["open-dir", "open-file", "go-parent", "navigate"],
  computed: {
    breadcrumb() {
      const parts = (this.path || "").split("/").filter(Boolean);
      const result = [{ label: "data", path: "" }];
      let current = "";
      parts.forEach((seg) => {
        current = current ? `${current}/${seg}` : seg;
        result.push({ label: seg, path: current });
      });
      return result;
    },
    sortedItems() {
      return [...this.items].sort((a, b) => {
        if (a.is_dir !== b.is_dir) return a.is_dir ? -1 : 1;
        return a.name.localeCompare(b.name);
      });
    },
  },
  methods: {
    iconFor(item) {
      if (item.is_dir) return "folder";
      if (item.kind === "image") return "image";
      if (item.kind === "video") return "film";
      if (item.kind === "audio") return "music";
      return "file";
    },
    kindClass(item) {
      if (item.is_dir) return "dir";
      return item.kind || "";
    },
    sizeLabel(item) {
      if (item.is_dir) return "目录";
      const bytes = item.size || 0;
      if (bytes < 1024) return bytes + " B";
      if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + " KB";
      if (bytes < 1024 * 1024 * 1024) return (bytes / 1048576).toFixed(1) + " MB";
      return (bytes / 1073741824).toFixed(2) + " GB";
    },
    handleClick(item) {
      if (item.is_dir) this.$emit("open-dir", item.path);
      else this.$emit("open-file", item);
    },
  },
  template: `
    <section class="panel" style="display: flex; flex-direction: column; gap: 12px">
      <div class="toolbar">
        <div class="toolbar-actions">
          <button @click="$emit('go-parent')" :disabled="!path" title="上级目录">
            <Icon name="corner-up-left" :size="15" /> 上级
          </button>
        </div>
        <div class="data-breadcrumb">
          <Icon name="home" :size="12" />
          <template v-for="(seg, idx) in breadcrumb" :key="idx">
            <span v-if="idx > 0">/</span>
            <span
              class="part"
              style="cursor: pointer"
              @click="$emit('navigate', seg.path)"
            >{{ seg.label }}</span>
          </template>
        </div>
      </div>

      <div v-if="loading" class="skeleton-grid">
        <div v-for="n in 6" :key="n" class="skeleton-card">
          <div class="sk-line"></div>
          <div class="sk-line short"></div>
        </div>
      </div>
      <div v-else-if="!sortedItems.length" class="empty">
        <div class="illus"><Icon name="folder-open" :size="34" /></div>
        <strong>当前目录为空</strong>
        <span>返回上级或切换路径查看更多文件。</span>
      </div>

      <div v-else class="data-grid">
        <div
          v-for="item in sortedItems"
          :key="item.path"
          class="data-item"
          :class="kindClass(item)"
          @click="handleClick(item)"
        >
          <div class="icon-wrap">
            <Icon :name="iconFor(item)" :size="16" />
          </div>
          <div class="meta">
            <strong :title="item.name">{{ item.name }}</strong>
            <small>{{ sizeLabel(item) }}</small>
          </div>
        </div>
      </div>
    </section>
  `,
};

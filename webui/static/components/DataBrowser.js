export const DataBrowser = {
  name: "DataBrowser",
  props: {
    path: { type: String, default: "" },
    parent: { type: String, default: "" },
    items: { type: Array, default: () => [] },
    loading: { type: Boolean, default: false },
  },
  emits: ["open-dir", "open-file", "go-parent", "refresh"],
  template: `
    <section class="data-browser">
      <header class="toolbar">
        <div class="toolbar-actions">
          <button @click="$emit('go-parent')" :disabled="!path">上级目录</button>
          <button @click="$emit('refresh')">刷新</button>
        </div>
        <div class="path-label">/data/{{ path || '' }}</div>
      </header>
      <div v-if="loading" class="loading">加载中...</div>
      <div v-else-if="!items.length" class="empty">当前目录为空。</div>
      <ul v-else class="data-list">
        <li v-for="item in items" :key="item.path" class="data-item">
          <button v-if="item.is_dir" class="data-link" @click="$emit('open-dir', item.path)">
            📁 {{ item.name }}
          </button>
          <button v-else class="data-link" @click="$emit('open-file', item)">
            📄 {{ item.name }}
          </button>
        </li>
      </ul>
    </section>
  `,
};

export const Sidebar = {
  name: "Sidebar",
  props: {
    categories: { type: Array, default: () => [] },
    activeCategory: { type: String, default: "" },
    viewMode: { type: String, default: "media" },
  },
  emits: ["switch-mode", "select-category", "create-category", "refresh"],
  methods: {
    addCategory() {
      const category = window.prompt("请输入新分类名称");
      if (!category || !category.trim()) {
        return;
      }
      const description = window.prompt("请输入分类描述（可选）", "") || "";
      this.$emit("create-category", { category: category.trim(), description: description.trim() });
    },
  },
  template: `
    <aside class="sidebar">
      <div class="sidebar-actions">
        <button :class="{ active: viewMode === 'media' }" @click="$emit('switch-mode', 'media')">媒体库</button>
        <button :class="{ active: viewMode === 'data' }" @click="$emit('switch-mode', 'data')">Data 浏览</button>
      </div>

      <div v-if="viewMode === 'media'" class="sidebar-section">
        <div class="sidebar-header">
          <h3>分类</h3>
          <div class="sidebar-tools">
            <button @click="$emit('refresh')">刷新</button>
            <button @click="addCategory">新增</button>
          </div>
        </div>
        <ul class="category-list">
          <li
            class="category-item"
            :class="{ active: activeCategory === '' }"
            @click="$emit('select-category', '')"
          >
            <span>全部</span>
          </li>
          <li
            v-for="item in categories"
            :key="item.category"
            class="category-item"
            :class="{ active: activeCategory === item.category }"
            @click="$emit('select-category', item.category)"
          >
            <span>{{ item.category }}</span>
            <small>{{ item.count }}</small>
          </li>
        </ul>
      </div>

      <div v-else class="sidebar-section">
        <div class="sidebar-header">
          <h3>AstrBot Data</h3>
          <button @click="$emit('refresh')">刷新</button>
        </div>
        <p class="muted">只读浏览 /astrbot/data 目录。</p>
      </div>
    </aside>
  `,
};

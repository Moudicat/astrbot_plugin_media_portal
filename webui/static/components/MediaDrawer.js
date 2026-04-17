export const MediaDrawer = {
  name: "MediaDrawer",
  props: {
    visible: { type: Boolean, default: false },
    media: { type: Object, default: null },
    categories: { type: Array, default: () => [] },
  },
  emits: ["close", "update", "delete", "copy-link"],
  data() {
    return {
      description: "",
      category: "",
      tags: "",
    };
  },
  watch: {
    media: {
      immediate: true,
      handler(value) {
        if (!value) {
          this.description = "";
          this.category = "";
          this.tags = "";
          return;
        }
        this.description = value.description || "";
        this.category = value.category || "";
        this.tags = Array.isArray(value.tags) ? value.tags.join(", ") : "";
      },
    },
  },
  methods: {
    save() {
      if (!this.media) return;
      this.$emit("update", {
        id: this.media.id,
        description: this.description,
        category: this.category,
        tags: this.tags
          .split(",")
          .map((item) => item.trim())
          .filter(Boolean),
      });
    },
  },
  template: `
    <aside class="drawer" :class="{ show: visible }">
      <header>
        <h3>媒体详情</h3>
        <button @click="$emit('close')">关闭</button>
      </header>
      <div v-if="!media" class="empty">请选择媒体查看详情。</div>
      <div v-else class="drawer-content">
        <p><strong>ID：</strong>{{ media.id }}</p>
        <p><strong>文件：</strong>{{ media.filename }}</p>
        <p><strong>类型：</strong>{{ media.kind }}</p>
        <p><strong>大小：</strong>{{ media.size_human || (media.size + 'B') }}</p>
        <label>分类</label>
        <select v-model="category">
          <option v-for="item in categories" :key="item.category" :value="item.category">
            {{ item.category }}
          </option>
        </select>
        <label>描述</label>
        <textarea v-model="description" rows="4" placeholder="可填写描述信息"></textarea>
        <label>标签（逗号分隔）</label>
        <input v-model="tags" placeholder="例如：猫, 表情, 测试" />
        <div class="drawer-actions">
          <button @click="save">保存</button>
          <button @click="$emit('copy-link', media.id)">复制链接</button>
          <button class="danger" @click="$emit('delete', media.id)">删除</button>
        </div>
      </div>
    </aside>
  `,
};

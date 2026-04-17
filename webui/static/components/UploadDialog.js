export const UploadDialog = {
  name: "UploadDialog",
  props: {
    visible: { type: Boolean, default: false },
    categories: { type: Array, default: () => [] },
    activeCategory: { type: String, default: "" },
    initialMode: { type: String, default: "file" },
  },
  emits: ["close", "upload-files", "save-url"],
  data() {
    return {
      mode: "file",
      category: this.activeCategory || "default",
      description: "",
      files: [],
      url: "",
      filename: "",
    };
  },
  watch: {
    visible(value) {
      if (value) {
        this.category = this.activeCategory || "default";
        this.mode = this.initialMode || "file";
      }
    },
  },
  methods: {
    onFiles(event) {
      this.files = Array.from(event.target.files || []);
    },
    submit() {
      if (this.mode === "file") {
        if (!this.files.length) {
          return;
        }
        this.$emit("upload-files", {
          category: this.category || "default",
          description: this.description,
          files: this.files,
        });
      } else {
        if (!this.url.trim()) {
          return;
        }
        this.$emit("save-url", {
          category: this.category || "default",
          description: this.description,
          url: this.url.trim(),
          filename: this.filename.trim(),
        });
      }
      this.files = [];
      this.url = "";
      this.filename = "";
      this.description = "";
      this.$emit("close");
    },
  },
  template: `
    <div class="dialog-mask" v-if="visible" @click.self="$emit('close')">
      <div class="dialog">
        <header>
          <h3>保存媒体</h3>
          <button @click="$emit('close')">关闭</button>
        </header>
        <div class="dialog-tabs">
          <button :class="{ active: mode === 'file' }" @click="mode = 'file'">上传文件</button>
          <button :class="{ active: mode === 'url' }" @click="mode = 'url'">保存 URL</button>
        </div>

        <label>分类</label>
        <select v-model="category">
          <option value="default">default</option>
          <option v-for="item in categories" :key="item.category" :value="item.category">
            {{ item.category }}
          </option>
        </select>

        <label>描述</label>
        <input v-model="description" placeholder="可选描述" />

        <template v-if="mode === 'file'">
          <label>选择文件</label>
          <input type="file" multiple @change="onFiles" />
          <small class="muted">支持图片、视频、音频。</small>
        </template>
        <template v-else>
          <label>媒体 URL</label>
          <input v-model="url" placeholder="https://..." />
          <label>自定义文件名（可选）</label>
          <input v-model="filename" placeholder="例如 cat.mp4" />
        </template>

        <footer>
          <button @click="submit">确认</button>
        </footer>
      </div>
    </div>
  `,
};

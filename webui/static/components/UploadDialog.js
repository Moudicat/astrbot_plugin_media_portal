import { Icon } from "./Icon.js";

export const UploadDialog = {
  name: "UploadDialog",
  components: { Icon },
  props: {
    visible: { type: Boolean, default: false },
    categories: { type: Array, default: () => [] },
    activeCategory: { type: String, default: "" },
    initialMode: { type: String, default: "file" },
    maxFileSizeMb: { type: Number, default: 500 },
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
      dragover: false,
    };
  },
  watch: {
    visible(value) {
      if (value) {
        this.category = this.activeCategory || "default";
        this.mode = this.initialMode || "file";
        this.files = [];
        this.url = "";
        this.filename = "";
        this.description = "";
      }
    },
  },
  computed: {
    hasDefault() {
      return (this.categories || []).some(
        (item) => item && item.category === "default"
      );
    },
    totalSize() {
      const bytes = this.files.reduce((sum, f) => sum + (f.size || 0), 0);
      if (!bytes) return "";
      if (bytes < 1024) return bytes + " B";
      if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + " KB";
      if (bytes < 1024 * 1024 * 1024) return (bytes / 1048576).toFixed(1) + " MB";
      return (bytes / 1073741824).toFixed(2) + " GB";
    },
    maxBytes() {
      const mb = Number(this.maxFileSizeMb) || 0;
      return mb > 0 ? mb * 1024 * 1024 : 0;
    },
    oversizedFiles() {
      if (!this.maxBytes) return [];
      return this.files.filter((f) => Number(f.size) > this.maxBytes);
    },
    acceptedFiles() {
      if (!this.maxBytes) return this.files;
      return this.files.filter((f) => Number(f.size) <= this.maxBytes);
    },
    dropzoneHint() {
      const mb = Number(this.maxFileSizeMb) || 0;
      if (mb > 0) {
        return `支持图片 / 视频 / 音频，多选上传 · 单文件上限 ${mb}MB`;
      }
      return "支持图片 / 视频 / 音频，多选上传";
    },
  },
  methods: {
    onFiles(event) {
      this.files = Array.from(event.target.files || []);
    },
    onDrop(event) {
      this.dragover = false;
      const dropped = Array.from(event.dataTransfer?.files || []);
      if (dropped.length) {
        this.files = dropped;
        this.mode = "file";
      }
    },
    formatSize(bytes) {
      if (bytes < 1024) return bytes + " B";
      if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + " KB";
      if (bytes < 1024 * 1024 * 1024) return (bytes / 1048576).toFixed(1) + " MB";
      return (bytes / 1073741824).toFixed(2) + " GB";
    },
    openFileDialog() {
      this.$refs.fileInput?.click();
    },
    removeFile(index) {
      this.files = this.files.filter((_, i) => i !== index);
    },
    isOversized(file) {
      return this.maxBytes > 0 && Number(file?.size) > this.maxBytes;
    },
    submit() {
      if (this.mode === "file") {
        if (!this.acceptedFiles.length) return;
        this.$emit("upload-files", {
          category: this.category || "default",
          description: this.description,
          files: this.acceptedFiles,
        });
      } else {
        if (!this.url.trim()) return;
        this.$emit("save-url", {
          category: this.category || "default",
          description: this.description,
          url: this.url.trim(),
          filename: this.filename.trim(),
        });
      }
      this.$emit("close");
    },
  },
  template: `
    <transition name="modal">
      <div class="modal-mask" v-if="visible" @click.self="$emit('close')">
        <div class="modal">
          <header>
            <h3>
              <Icon name="upload-cloud" :size="17" style="vertical-align: -3px" />
              保存媒体
            </h3>
            <button class="icon" @click="$emit('close')" title="关闭">
              <Icon name="x" :size="16" />
            </button>
          </header>

          <div class="modal-body">
            <div class="dialog-tabs">
              <button :class="{ active: mode === 'file' }" @click="mode = 'file'">
                <Icon name="upload" :size="14" /> 上传文件
              </button>
              <button :class="{ active: mode === 'url' }" @click="mode = 'url'">
                <Icon name="link" :size="14" /> URL 保存
              </button>
            </div>

            <div class="field">
              <label>分类</label>
              <select v-model="category">
                <option v-if="!hasDefault" value="default">default</option>
                <option v-for="item in categories" :key="item.category" :value="item.category">
                  {{ item.category }}
                </option>
              </select>
            </div>

            <div class="field">
              <label>描述（可选）</label>
              <input v-model="description" placeholder="添加一些描述，帮助后续检索" />
            </div>

            <template v-if="mode === 'file'">
              <div
                class="dropzone"
                :class="{ dragover }"
                @dragover.prevent="dragover = true"
                @dragleave.prevent="dragover = false"
                @drop.prevent="onDrop"
                @click="openFileDialog"
              >
                <Icon name="upload-cloud" :size="30" />
                <strong>拖拽文件到这里，或点击选择</strong>
                <span class="muted">{{ dropzoneHint }}</span>
                <input
                  ref="fileInput"
                  type="file"
                  multiple
                  style="display: none"
                  @change="onFiles"
                />
                <div v-if="files.length" class="file-list">
                  <div
                    v-for="(f, idx) in files"
                    :key="idx"
                    class="file"
                    :class="{ 'file-oversized': isOversized(f) }"
                  >
                    <span style="overflow: hidden; text-overflow: ellipsis; white-space: nowrap">
                      {{ f.name }}
                    </span>
                    <span class="muted mono">{{ formatSize(f.size) }}</span>
                    <span v-if="isOversized(f)" class="file-badge" title="超过体积上限，保存时将被跳过">
                      <Icon name="triangle-alert" :size="12" /> 超出上限
                    </span>
                  </div>
                </div>
              </div>
              <small class="muted" v-if="files.length">
                共 {{ files.length }} 个文件 · 总计 {{ totalSize }}
                <template v-if="oversizedFiles.length">
                  · <span class="text-warning">{{ oversizedFiles.length }} 个超出 {{ maxFileSizeMb }}MB 上限，将被跳过</span>
                </template>
              </small>
            </template>

            <template v-else>
              <div class="field">
                <label>媒体 URL</label>
                <div class="input-wrap">
                  <span class="icon-slot"><Icon name="globe" :size="15" /></span>
                  <input v-model="url" placeholder="https://..." />
                </div>
              </div>
              <div class="field">
                <label>自定义文件名（可选）</label>
                <input v-model="filename" placeholder="例如 cat.mp4" />
              </div>
            </template>
          </div>

          <div class="modal-footer">
            <button @click="$emit('close')">取消</button>
            <button
              class="primary"
              @click="submit"
              :disabled="mode === 'file' ? !acceptedFiles.length : !url.trim()"
            >
              <Icon name="check" :size="15" />
              确认保存
            </button>
          </div>
        </div>
      </div>
    </transition>
  `,
};

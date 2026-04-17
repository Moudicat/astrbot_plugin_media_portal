import { Icon } from "./Icon.js";

function formatSize(bytes) {
  const size = Number(bytes) || 0;
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
  if (size < 1024 * 1024 * 1024) return `${(size / 1048576).toFixed(1)} MB`;
  return `${(size / 1073741824).toFixed(2)} GB`;
}

const LANG_MAP = {
  ".json": "json",
  ".json5": "json",
  ".jsonl": "json",
  ".ndjson": "json",
  ".md": "markdown",
  ".markdown": "markdown",
  ".yaml": "yaml",
  ".yml": "yaml",
  ".toml": "toml",
  ".ini": "ini",
  ".py": "python",
  ".js": "javascript",
  ".ts": "typescript",
  ".tsx": "tsx",
  ".jsx": "jsx",
  ".vue": "vue",
  ".css": "css",
  ".html": "html",
  ".htm": "html",
  ".xml": "xml",
  ".sh": "shell",
  ".sql": "sql",
  ".go": "go",
  ".rs": "rust",
  ".java": "java",
  ".c": "c",
  ".cpp": "cpp",
  ".h": "c",
};

export const DataFileModal = {
  name: "DataFileModal",
  components: { Icon },
  props: {
    preview: { type: Object, default: null },
  },
  emits: ["close", "copy", "download"],
  computed: {
    visible() {
      return !!this.preview;
    },
    sizeLabel() {
      return formatSize(this.preview?.size || 0);
    },
    language() {
      const suffix = (this.preview?.suffix || "").toLowerCase();
      return LANG_MAP[suffix] || "";
    },
    contentLines() {
      const content = this.preview?.content || "";
      if (!content) return 0;
      return content.split("\n").length;
    },
    displayContent() {
      return this.preview?.content || "";
    },
  },
  watch: {
    visible(value) {
      if (value) {
        window.addEventListener("keydown", this.onKey);
      } else {
        window.removeEventListener("keydown", this.onKey);
      }
    },
  },
  beforeUnmount() {
    window.removeEventListener("keydown", this.onKey);
  },
  methods: {
    onKey(event) {
      if (!this.visible) return;
      if (event.key === "Escape") this.$emit("close");
    },
    handleDownload() {
      if (!this.preview) return;
      this.$emit("download", {
        path: this.preview.path,
        name: this.preview.name,
      });
    },
  },
  template: `
    <transition name="modal">
      <div v-if="visible" class="modal-mask data-preview-mask" @click.self="$emit('close')">
        <div class="modal data-preview-modal">
          <header>
            <h3>
              <Icon :name="preview.isText ? 'file-text' : 'file-question'" :size="17" style="vertical-align: -3px" />
              <span class="data-preview-title" :title="preview.name">{{ preview.name }}</span>
            </h3>
            <button class="icon" @click="$emit('close')" title="关闭">
              <Icon name="x" :size="16" />
            </button>
          </header>

          <div class="data-preview-meta">
            <span class="badge" :class="preview.isText ? 'info' : 'warning'">
              <Icon :name="preview.isText ? 'align-left' : 'help-circle'" :size="12" />
              {{ preview.isText ? '文本预览' : '不支持的文件类型' }}
            </span>
            <span class="mono muted">{{ sizeLabel }}</span>
            <span v-if="preview.mime" class="muted">{{ preview.mime }}</span>
            <span v-if="preview.encoding" class="muted">编码: {{ preview.encoding }}</span>
            <span v-if="preview.truncated" class="badge warning">
              <Icon name="scissors" :size="11" />
              已截断
            </span>
          </div>

          <div class="modal-body data-preview-body">
            <div v-if="preview.loading" class="empty" style="padding: 30px 12px">
              <Icon name="loader" :size="28" />
              <strong>加载中…</strong>
            </div>
            <template v-else-if="preview.isText">
              <div class="data-preview-toolbar">
                <small class="muted">
                  <Icon name="list" :size="12" style="vertical-align: -2px" />
                  {{ contentLines }} 行
                </small>
                <div class="data-preview-actions">
                  <button class="sm" @click="$emit('copy')">
                    <Icon name="clipboard-copy" :size="13" />
                    复制内容
                  </button>
                  <button class="sm" @click="handleDownload">
                    <Icon name="download" :size="13" />
                    下载原文件
                  </button>
                </div>
              </div>
              <pre class="data-preview-pre" :data-lang="language"><code>{{ displayContent }}</code></pre>
              <small v-if="preview.truncated" class="muted">文件较大，仅预览前部分内容。请下载以查看完整文件。</small>
            </template>
            <div v-else class="data-preview-unsupported">
              <div class="illus"><Icon name="file-warning" :size="38" /></div>
              <strong>此类型不支持文本预览</strong>
              <span class="muted">
                该文件看起来是二进制或未识别的格式，无法在浏览器内直接展示。你可以下载后在本地打开。
              </span>
              <div class="data-preview-actions" style="justify-content: center; margin-top: 4px">
                <button class="primary" @click="handleDownload">
                  <Icon name="download" :size="14" />
                  点击下载
                </button>
              </div>
            </div>
          </div>

          <div class="modal-footer">
            <button @click="$emit('close')">关闭</button>
          </div>
        </div>
      </div>
    </transition>
  `,
};

import { Icon } from "./Icon.js";

export const MediaDrawer = {
  name: "MediaDrawer",
  components: { Icon },
  props: {
    visible: { type: Boolean, default: false },
    media: { type: Object, default: null },
    categories: { type: Array, default: () => [] },
    readonlyToken: { type: String, default: "" },
  },
  emits: ["close", "update", "delete", "copy-link", "preview"],
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
  computed: {
    fileUrl() {
      if (!this.media) return "";
      if (this.media.public_url) return this.media.public_url;
      const token = this.readonlyToken
        ? `?token=${encodeURIComponent(this.readonlyToken)}`
        : "";
      return `/files/${encodeURIComponent(this.media.category)}/${encodeURIComponent(
        this.media.filename
      )}${token}`;
    },
    sizeLabel() {
      if (!this.media) return "-";
      return this.media.size_human || `${this.media.size || 0} B`;
    },
    hasDefaultCategory() {
      return (this.categories || []).some(
        (item) => item && item.category === "default"
      );
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
    <transition name="drawer">
      <div v-if="visible" class="drawer-mask" @click.self="$emit('close')">
        <aside class="drawer">
          <header>
            <h3>
              <Icon name="info" :size="16" style="vertical-align: -3px" />
              媒体详情
            </h3>
            <button class="icon" @click="$emit('close')" title="关闭">
              <Icon name="x" :size="16" />
            </button>
          </header>
          <div v-if="!media" class="empty">
            <div class="illus"><Icon name="file-question" :size="30" /></div>
            <strong>未选中媒体</strong>
            <span>请在列表中点击项目查看详情。</span>
          </div>
          <div v-else class="drawer-content">
            <div class="drawer-preview" @click="$emit('preview', media)">
              <img v-if="media.kind === 'image'" :src="fileUrl" :alt="media.filename" />
              <video v-else-if="media.kind === 'video'" :src="fileUrl" muted preload="metadata"></video>
              <div v-else class="audio-placeholder">
                <div class="disc"><Icon :name="media.kind === 'audio' ? 'music' : 'file'" :size="24" /></div>
                <small>{{ media.kind }}</small>
              </div>
            </div>

            <dl class="drawer-meta">
              <dt>ID</dt><dd>{{ media.id }}</dd>
              <dt>文件</dt><dd>{{ media.filename }}</dd>
              <dt>类型</dt><dd><span class="badge primary">{{ media.kind }}</span></dd>
              <dt>大小</dt><dd>{{ sizeLabel }}</dd>
              <dt v-if="media.created_at">创建</dt>
              <dd v-if="media.created_at">{{ media.created_at }}</dd>
            </dl>

            <div class="field">
              <label>分类</label>
              <select v-model="category">
                <option v-if="!hasDefaultCategory" value="default">default</option>
                <option
                  v-for="item in categories"
                  :key="item.category"
                  :value="item.category"
                >
                  {{ item.category }}
                </option>
              </select>
            </div>

            <div class="field">
              <label>描述</label>
              <textarea v-model="description" rows="3" placeholder="可填写描述信息..."></textarea>
            </div>

            <div class="field">
              <label>标签（逗号分隔）</label>
              <input v-model="tags" placeholder="例如：猫, 表情, 测试" />
            </div>

            <div class="drawer-actions">
              <button class="primary drawer-action-primary" @click="save">
                <Icon name="save" :size="15" /> 保存
              </button>
              <div class="drawer-action-row">
                <button class="drawer-action-sub" @click="$emit('copy-link', media.id)">
                  <Icon name="link-2" :size="15" />
                  <span>复制链接</span>
                </button>
                <a
                  :href="fileUrl"
                  target="_blank"
                  rel="noopener"
                  class="btn drawer-action-sub"
                  style="text-decoration: none"
                >
                  <Icon name="external-link" :size="15" />
                  <span>打开</span>
                </a>
                <button class="danger drawer-action-sub" @click="$emit('delete', media.id)">
                  <Icon name="trash-2" :size="15" />
                  <span>删除</span>
                </button>
              </div>
            </div>
          </div>
        </aside>
      </div>
    </transition>
  `,
};

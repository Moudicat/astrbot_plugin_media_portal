import { Icon } from "./Icon.js";

export const PlayerModal = {
  name: "PlayerModal",
  components: { Icon },
  props: {
    visible: { type: Boolean, default: false },
    item: { type: Object, default: null },
    readonlyToken: { type: String, default: "" },
    canNavigate: { type: Boolean, default: true },
  },
  emits: ["close", "next", "prev", "copy-link"],
  computed: {
    sourceUrl() {
      if (!this.item) return "";
      if (this.item.directUrl) return this.item.directUrl;
      if (!this.item.category || !this.item.filename) return "";
      const token = this.readonlyToken
        ? `?token=${encodeURIComponent(this.readonlyToken)}`
        : "";
      return `/files/${encodeURIComponent(this.item.category)}/${encodeURIComponent(
        this.item.filename
      )}${token}`;
    },
    displayName() {
      return this.item?.filename || this.item?.name || "预览";
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
      else if (event.key === "ArrowLeft") this.$emit("prev");
      else if (event.key === "ArrowRight") this.$emit("next");
    },
    openInNewTab() {
      if (!this.sourceUrl) return;
      let target = this.sourceUrl;
      try {
        target = new URL(this.sourceUrl, window.location.origin).toString();
      } catch (_e) {
        // keep as-is
      }
      window.open(target, "_blank", "noopener");
    },
    copyLink() {
      if (!this.item) return;
      if (this.item.id != null) {
        this.$emit("copy-link", { id: this.item.id });
        return;
      }
      if (this.sourceUrl) {
        this.$emit("copy-link", { url: this.sourceUrl });
      }
    },
  },
  template: `
    <transition name="modal">
      <div v-if="visible" class="player-mask" @click.self="$emit('close')">
        <div class="player-topbar">
          <div style="min-width: 0; display: flex; flex-direction: column">
            <strong style="white-space: nowrap; overflow: hidden; text-overflow: ellipsis">
              {{ displayName }}
            </strong>
            <span class="meta">
              <span v-if="item?.category">{{ item.category }}</span>
              <span v-if="item?.kind"> · {{ item.kind }}</span>
              <span v-if="item?.size_human"> · {{ item.size_human }}</span>
            </span>
          </div>
          <div class="actions">
            <button class="icon" @click="copyLink" title="复制链接">
              <Icon name="link-2" :size="16" />
            </button>
            <button
              class="icon"
              :disabled="!sourceUrl"
              title="新窗口打开"
              @click="openInNewTab"
            >
              <Icon name="external-link" :size="16" />
            </button>
            <button class="icon" @click="$emit('close')" title="关闭 (Esc)">
              <Icon name="x" :size="16" />
            </button>
          </div>
        </div>

        <div class="player-body" v-if="item">
          <button
            v-if="canNavigate"
            class="player-nav prev"
            @click.stop="$emit('prev')"
            title="上一项 (←)"
          >
            <Icon name="chevron-left" :size="20" />
          </button>
          <img v-if="item.kind === 'image'" :src="sourceUrl" :alt="displayName" />
          <video
            v-else-if="item.kind === 'video'"
            :src="sourceUrl"
            controls
            playsinline
            autoplay
            preload="metadata"
          ></video>
          <audio
            v-else-if="item.kind === 'audio'"
            :src="sourceUrl"
            controls
            autoplay
            preload="metadata"
          ></audio>
          <div v-else class="empty">
            <div class="illus"><Icon name="file-question" :size="28" /></div>
            <strong>此类型不支持内置预览</strong>
            <span>请下载文件后在本地打开。</span>
          </div>
          <button
            v-if="canNavigate"
            class="player-nav next"
            @click.stop="$emit('next')"
            title="下一项 (→)"
          >
            <Icon name="chevron-right" :size="20" />
          </button>
        </div>
      </div>
    </transition>
  `,
};

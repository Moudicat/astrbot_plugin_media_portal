import { Icon } from "./Icon.js";

export const AudioDock = {
  name: "AudioDock",
  components: { Icon },
  props: {
    item: { type: Object, default: null },
    readonlyToken: { type: String, default: "" },
  },
  emits: ["close"],
  data() {
    return {
      minimized: false,
    };
  },
  computed: {
    sourceUrl() {
      if (!this.item) return "";
      if (this.item.directUrl) return this.item.directUrl;
      const token = this.readonlyToken
        ? `?token=${encodeURIComponent(this.readonlyToken)}`
        : "";
      return `/files/${encodeURIComponent(this.item.category)}/${encodeURIComponent(
        this.item.filename
      )}${token}`;
    },
    title() {
      if (!this.item) return "";
      return this.item.filename || this.item.name || "";
    },
  },
  watch: {
    item: {
      immediate: true,
      handler(value) {
        if (value) this.minimized = false;
        if (typeof document !== "undefined") {
          document.body.classList.toggle("audio-dock-active", !!value);
        }
      },
    },
    minimized(value) {
      if (typeof document !== "undefined") {
        document.body.classList.toggle("audio-dock-mini", !!value);
      }
    },
  },
  beforeUnmount() {
    if (typeof document !== "undefined") {
      document.body.classList.remove("audio-dock-active");
      document.body.classList.remove("audio-dock-mini");
    }
  },
  methods: {
    toggleMinimized() {
      this.minimized = !this.minimized;
    },
  },
  template: `
    <transition name="audio-dock">
      <div
        v-if="item"
        class="audio-dock"
        :class="{ 'is-mini': minimized }"
        role="region"
        aria-label="音频播放器"
      >
        <div class="avatar" @click="minimized && toggleMinimized()">
          <Icon name="music" :size="18" />
        </div>
        <div class="audio-dock-meta">
          <strong :title="title">{{ title }}</strong>
          <small>{{ item.category || 'data' }}</small>
        </div>
        <div class="audio-dock-controls">
          <button
            class="icon"
            @click="toggleMinimized"
            :title="minimized ? '展开播放器' : '最小化'"
          >
            <Icon :name="minimized ? 'chevron-up' : 'chevron-down'" :size="16" />
          </button>
          <button class="icon" @click="$emit('close')" title="关闭">
            <Icon name="x" :size="16" />
          </button>
        </div>
        <audio v-show="!minimized" :src="sourceUrl" controls autoplay preload="metadata"></audio>
      </div>
    </transition>
  `,
};

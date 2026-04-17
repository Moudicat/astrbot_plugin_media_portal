import { Icon } from "./Icon.js";

export const AudioDock = {
  name: "AudioDock",
  components: { Icon },
  props: {
    item: { type: Object, default: null },
    readonlyToken: { type: String, default: "" },
  },
  emits: ["close"],
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
  },
  template: `
    <transition name="audio-dock">
      <div v-if="item" class="audio-dock" role="region" aria-label="音频播放器">
        <div class="avatar"><Icon name="music" :size="18" /></div>
        <div class="audio-dock-meta">
          <strong :title="item.filename || item.name">{{ item.filename || item.name }}</strong>
          <small>{{ item.category || 'data' }}</small>
        </div>
        <button class="icon" @click="$emit('close')" title="关闭">
          <Icon name="x" :size="16" />
        </button>
        <audio :src="sourceUrl" controls autoplay preload="metadata"></audio>
      </div>
    </transition>
  `,
};

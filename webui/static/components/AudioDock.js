export const AudioDock = {
  name: "AudioDock",
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
    <div v-if="item" class="audio-dock">
      <div class="audio-dock-meta">
        <strong>{{ item.filename || item.name }}</strong>
        <small>{{ item.category || 'data' }}</small>
      </div>
      <audio :src="sourceUrl" controls autoplay preload="metadata"></audio>
      <button @click="$emit('close')">关闭</button>
    </div>
  `,
};

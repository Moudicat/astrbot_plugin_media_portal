export const MediaCard = {
  name: "MediaCard",
  props: {
    item: { type: Object, required: true },
    selected: { type: Boolean, default: false },
    readonlyToken: { type: String, default: "" },
  },
  emits: ["toggle-select", "preview", "detail"],
  computed: {
    fileUrl() {
      const token = this.readonlyToken ? `?token=${encodeURIComponent(this.readonlyToken)}` : "";
      return `/files/${encodeURIComponent(this.item.category)}/${encodeURIComponent(this.item.filename)}${token}`;
    },
  },
  template: `
    <article class="media-card" :class="{ selected }">
      <div class="card-toolbar">
        <input
          type="checkbox"
          :checked="selected"
          @change="$emit('toggle-select', item.id)"
        />
        <button @click="$emit('detail', item)">详情</button>
      </div>
      <div class="media-preview" @click="$emit('preview', item)">
        <img v-if="item.kind === 'image'" :src="fileUrl" :alt="item.filename" loading="lazy" />
        <video v-else-if="item.kind === 'video'" :src="fileUrl" muted preload="metadata"></video>
        <div v-else-if="item.kind === 'audio'" class="audio-placeholder">
          <span>🎵</span>
          <small>音频</small>
        </div>
        <div v-else class="file-placeholder">
          <span>📄</span>
          <small>{{ item.kind || 'file' }}</small>
        </div>
      </div>
      <footer class="media-meta">
        <strong :title="item.filename">{{ item.filename }}</strong>
        <small>{{ item.category }} · {{ item.size_human || item.size + 'B' }}</small>
      </footer>
    </article>
  `,
};

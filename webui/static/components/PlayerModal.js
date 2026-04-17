export const PlayerModal = {
  name: "PlayerModal",
  props: {
    visible: { type: Boolean, default: false },
    item: { type: Object, default: null },
    readonlyToken: { type: String, default: "" },
  },
  emits: ["close", "next", "prev"],
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
  },
  template: `
    <div v-if="visible" class="player-mask" @click.self="$emit('close')">
      <div class="player-modal">
        <header>
          <strong>{{ item?.filename || item?.name || '预览' }}</strong>
          <div class="player-actions">
            <button @click="$emit('prev')">上一项</button>
            <button @click="$emit('next')">下一项</button>
            <button @click="$emit('close')">关闭</button>
          </div>
        </header>

        <div class="player-body" v-if="item">
          <img v-if="item.kind === 'image'" :src="sourceUrl" :alt="item.filename || item.name" />
          <video
            v-else-if="item.kind === 'video'"
            :src="sourceUrl"
            controls
            playsinline
            preload="metadata"
          ></video>
          <audio
            v-else-if="item.kind === 'audio'"
            :src="sourceUrl"
            controls
            preload="metadata"
          ></audio>
          <div v-else class="empty">该类型不支持内置预览，请下载后查看。</div>
        </div>
      </div>
    </div>
  `,
};

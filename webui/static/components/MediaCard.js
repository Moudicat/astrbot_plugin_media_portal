import { Icon } from "./Icon.js";

const KIND_META = {
  image: { icon: "image", label: "图片" },
  video: { icon: "film", label: "视频" },
  audio: { icon: "music", label: "音频" },
  file: { icon: "file", label: "文件" },
};

export const MediaCard = {
  name: "MediaCard",
  components: { Icon },
  props: {
    item: { type: Object, required: true },
    selected: { type: Boolean, default: false },
    readonlyToken: { type: String, default: "" },
  },
  emits: ["toggle-select", "preview", "detail", "copy-link"],
  data() {
    return {
      imageLoaded: false,
      imageError: false,
    };
  },
  watch: {
    "item.id"() {
      this.imageLoaded = false;
      this.imageError = false;
    },
  },
  computed: {
    tokenSuffix() {
      return this.readonlyToken
        ? `?token=${encodeURIComponent(this.readonlyToken)}`
        : "";
    },
    fileUrl() {
      return `/files/${encodeURIComponent(this.item.category)}/${encodeURIComponent(
        this.item.filename
      )}${this.tokenSuffix}`;
    },
    thumbUrl() {
      const sep = this.tokenSuffix ? "&" : "?";
      return `/thumb/${encodeURIComponent(this.item.category)}/${encodeURIComponent(
        this.item.filename
      )}${this.tokenSuffix}${sep}size=480`;
    },
    previewSrc() {
      if (this.item.kind === "image") {
        return this.imageError ? this.fileUrl : this.thumbUrl;
      }
      return this.fileUrl;
    },
    kindMeta() {
      return KIND_META[this.item.kind] || KIND_META.file;
    },
    sizeLabel() {
      return this.item.size_human || `${this.item.size || 0} B`;
    },
  },
  methods: {
    handleImgError() {
      if (!this.imageError) {
        this.imageError = true;
      }
    },
    handleImgLoad() {
      this.imageLoaded = true;
    },
  },
  template: `
    <article class="media-card" :class="{ selected }">
      <div class="media-preview" @click="$emit('preview', item)">
        <img
          v-if="item.kind === 'image'"
          :src="previewSrc"
          :alt="item.filename"
          loading="lazy"
          decoding="async"
          :class="{ loaded: imageLoaded }"
          @load="handleImgLoad"
          @error="handleImgError"
        />
        <video
          v-else-if="item.kind === 'video'"
          :src="fileUrl"
          muted
          preload="metadata"
          playsinline
        ></video>
        <div v-else-if="item.kind === 'audio'" class="audio-placeholder">
          <div class="disc"><Icon name="music" :size="24" /></div>
          <small>{{ item.filename }}</small>
        </div>
        <div v-else class="file-placeholder">
          <Icon name="file" :size="28" />
          <small>{{ item.kind || 'file' }}</small>
        </div>

        <div class="preview-overlay">
          <span class="preview-kind">
            <Icon :name="kindMeta.icon" :size="12" />
            {{ kindMeta.label }}
          </span>
          <div class="preview-actions" @click.stop>
            <button class="icon sm" @click="$emit('preview', item)" title="预览">
              <Icon name="play" :size="14" />
            </button>
            <button class="icon sm" @click="$emit('copy-link', item.id)" title="复制链接">
              <Icon name="link-2" :size="14" />
            </button>
            <button class="icon sm" @click="$emit('detail', item)" title="详情">
              <Icon name="settings-2" :size="14" />
            </button>
          </div>
        </div>
      </div>

      <div class="media-card-body">
        <label class="card-check" @click.stop>
          <input
            type="checkbox"
            :checked="selected"
            @change="$emit('toggle-select', item.id)"
          />
        </label>
        <div class="card-meta">
          <strong :title="item.filename">{{ item.filename }}</strong>
          <div class="sub">
            <span>{{ item.category }}</span>
            <span class="dot"></span>
            <span class="mono">{{ sizeLabel }}</span>
          </div>
        </div>
      </div>
    </article>
  `,
};

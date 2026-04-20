import { Icon } from "./Icon.js";

const STAT_CARD_OPTIONS = [
  { key: "total", label: "媒体总数", icon: "library", desc: "顶部首要指标" },
  { key: "image", label: "图片数量", icon: "image", desc: "按类型统计" },
  { key: "video", label: "视频数量", icon: "film", desc: "按类型统计" },
  { key: "audio", label: "音频数量", icon: "music", desc: "按类型统计" },
  { key: "cat", label: "分类总数", icon: "folder", desc: "当前分类数" },
  { key: "size", label: "占用空间", icon: "database", desc: "总体大小" },
];

export const SettingsDialog = {
  name: "SettingsDialog",
  components: { Icon },
  props: {
    visible: { type: Boolean, default: false },
    statVisibility: {
      type: Object,
      default: () => ({
        total: true,
        image: true,
        video: true,
        audio: true,
        cat: true,
        size: true,
      }),
    },
  },
  emits: ["close", "prune-categories", "update-stat-visibility"],
  data() {
    return {
      pruneBusy: false,
      statOptions: STAT_CARD_OPTIONS,
    };
  },
  computed: {
    allOn() {
      return STAT_CARD_OPTIONS.every(
        (opt) => (this.statVisibility || {})[opt.key] !== false,
      );
    },
    allOff() {
      return STAT_CARD_OPTIONS.every(
        (opt) => (this.statVisibility || {})[opt.key] === false,
      );
    },
  },
  watch: {
    visible(value) {
      if (value) {
        this.pruneBusy = false;
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
      if (event.key === "Escape") {
        this.$emit("close");
      }
    },
    onPrune() {
      this.pruneBusy = true;
      this.$emit("prune-categories");
      setTimeout(() => {
        this.pruneBusy = false;
      }, 1200);
    },
    isOn(key) {
      return (this.statVisibility || {})[key] !== false;
    },
    toggleStat(key) {
      this.$emit("update-stat-visibility", { [key]: !this.isOn(key) });
    },
    setAll(value) {
      const payload = {};
      for (const opt of STAT_CARD_OPTIONS) {
        payload[opt.key] = value;
      }
      this.$emit("update-stat-visibility", payload);
    },
  },
  template: `
    <transition name="modal">
      <div v-if="visible" class="modal-mask" @click.self="$emit('close')">
        <div class="modal settings-modal">
          <header>
            <h3>
              <Icon name="settings" :size="17" style="vertical-align: -3px" />
              设置
            </h3>
            <button class="icon" @click="$emit('close')" title="关闭 (Esc)">
              <Icon name="x" :size="16" />
            </button>
          </header>

          <div class="modal-body settings-body">
            <section class="settings-section">
              <div class="settings-section-head">
                <div>
                  <strong>首页统计卡片</strong>
                  <small class="muted">控制媒体库首页顶部统计卡片的显示项</small>
                </div>
                <div class="settings-toolbar">
                  <button
                    class="ghost sm"
                    :disabled="allOn"
                    @click="setAll(true)"
                    title="全部显示"
                  >
                    <Icon name="eye" :size="13" />
                    <span>全部显示</span>
                  </button>
                  <button
                    class="ghost sm"
                    :disabled="allOff"
                    @click="setAll(false)"
                    title="全部隐藏"
                  >
                    <Icon name="eye-off" :size="13" />
                    <span>全部隐藏</span>
                  </button>
                </div>
              </div>
              <ul class="settings-toggle-list">
                <li
                  v-for="opt in statOptions"
                  :key="opt.key"
                  class="settings-toggle"
                  :class="{ disabled: !isOn(opt.key) }"
                  @click="toggleStat(opt.key)"
                >
                  <div class="settings-toggle-icon">
                    <Icon :name="opt.icon" :size="14" />
                  </div>
                  <div class="settings-toggle-body">
                    <span class="settings-toggle-title">{{ opt.label }}</span>
                    <span class="settings-toggle-desc">{{ opt.desc }}</span>
                  </div>
                  <span
                    class="switch"
                    :class="{ on: isOn(opt.key) }"
                    role="switch"
                    :aria-checked="isOn(opt.key) ? 'true' : 'false'"
                  ></span>
                </li>
              </ul>
            </section>

            <section class="settings-section">
              <div class="settings-section-head">
                <div>
                  <strong>清理空分类</strong>
                  <small class="muted">一键清除没有媒体且目录为空的分类（保留 default）</small>
                </div>
                <button
                  class="ghost"
                  :disabled="pruneBusy"
                  @click="onPrune"
                >
                  <Icon name="eraser" :size="14" />
                  <span>{{ pruneBusy ? "清理中..." : "立即清理" }}</span>
                </button>
              </div>
            </section>
          </div>

          <div class="modal-footer">
            <button class="primary" @click="$emit('close')">完成</button>
          </div>
        </div>
      </div>
    </transition>
  `,
};

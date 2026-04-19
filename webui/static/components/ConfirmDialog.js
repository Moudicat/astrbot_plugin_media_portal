import { Icon } from "./Icon.js";

const TONE_ICON = {
  danger: "alert-triangle",
  warning: "alert-triangle",
  primary: "help-circle",
  info: "info",
  success: "check-circle",
};

const TONE_BUTTON = {
  danger: "danger",
  warning: "accent",
  primary: "primary",
  info: "primary",
  success: "accent",
};

export const ConfirmDialog = {
  name: "ConfirmDialog",
  components: { Icon },
  props: {
    visible: { type: Boolean, default: false },
    title: { type: String, default: "请确认" },
    message: { type: String, default: "" },
    detail: { type: String, default: "" },
    confirmText: { type: String, default: "确认" },
    cancelText: { type: String, default: "取消" },
    tone: { type: String, default: "primary" },
    icon: { type: String, default: "" },
    loading: { type: Boolean, default: false },
  },
  emits: ["confirm", "cancel"],
  computed: {
    toneKey() {
      return TONE_ICON[this.tone] ? this.tone : "primary";
    },
    headIcon() {
      if (this.icon) return this.icon;
      return TONE_ICON[this.toneKey] || "help-circle";
    },
    confirmBtnClass() {
      return TONE_BUTTON[this.toneKey] || "primary";
    },
  },
  watch: {
    visible(value) {
      if (value) {
        window.addEventListener("keydown", this.onKey);
        this.$nextTick(() => {
          if (this.$refs.confirmBtn && typeof this.$refs.confirmBtn.focus === "function") {
            this.$refs.confirmBtn.focus();
          }
        });
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
        event.preventDefault();
        this.onCancel();
      } else if (event.key === "Enter") {
        event.preventDefault();
        this.onConfirm();
      }
    },
    onCancel() {
      if (this.loading) return;
      this.$emit("cancel");
    },
    onConfirm() {
      if (this.loading) return;
      this.$emit("confirm");
    },
  },
  template: `
    <transition name="modal">
      <div v-if="visible" class="modal-mask confirm-mask" @click.self="onCancel">
        <div class="modal confirm-modal" :data-tone="toneKey">
          <header class="confirm-header">
            <div class="confirm-head-main">
              <span class="confirm-head-icon" :data-tone="toneKey">
                <Icon :name="headIcon" :size="18" />
              </span>
              <h3>{{ title }}</h3>
            </div>
            <button class="icon sm plain-ish" type="button" @click="onCancel" title="关闭 (Esc)">
              <Icon name="x" :size="15" />
            </button>
          </header>
          <div class="modal-body confirm-body">
            <p v-if="message" class="confirm-message">{{ message }}</p>
            <p v-if="detail" class="confirm-detail">{{ detail }}</p>
          </div>
          <div class="modal-footer confirm-footer">
            <button type="button" :disabled="loading" @click="onCancel">
              {{ cancelText }}
            </button>
            <button
              ref="confirmBtn"
              type="button"
              :class="confirmBtnClass"
              :disabled="loading"
              @click="onConfirm"
            >
              <Icon v-if="loading" name="loader-2" :size="14" class="spin" />
              <span>{{ confirmText }}</span>
            </button>
          </div>
        </div>
      </div>
    </transition>
  `,
};

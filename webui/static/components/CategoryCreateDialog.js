import { Icon } from "./Icon.js";

const CATEGORY_NAME_RE = /^[A-Za-z0-9_\u4e00-\u9fa5][A-Za-z0-9_\-\u4e00-\u9fa5]{0,31}$/;

export const CategoryCreateDialog = {
  name: "CategoryCreateDialog",
  components: { Icon },
  props: {
    visible: { type: Boolean, default: false },
    existing: { type: Array, default: () => [] },
  },
  emits: ["close", "submit"],
  data() {
    return {
      category: "",
      description: "",
      touched: false,
    };
  },
  computed: {
    trimmedName() {
      return (this.category || "").trim();
    },
    duplicated() {
      if (!this.trimmedName) return false;
      const lower = this.trimmedName.toLowerCase();
      return (this.existing || []).some(
        (item) =>
          item && (item.category || "").toString().toLowerCase() === lower
      );
    },
    invalidFormat() {
      if (!this.trimmedName) return false;
      return !CATEGORY_NAME_RE.test(this.trimmedName);
    },
    errorMessage() {
      if (!this.touched) return "";
      if (!this.trimmedName) return "分类名称不能为空";
      if (this.invalidFormat)
        return "只能包含中英文、数字、下划线与连字符，长度 1-32";
      if (this.duplicated) return "该分类已存在";
      return "";
    },
    canSubmit() {
      return !!this.trimmedName && !this.invalidFormat && !this.duplicated;
    },
  },
  watch: {
    visible(value) {
      if (value) {
        this.category = "";
        this.description = "";
        this.touched = false;
        this.$nextTick(() => {
          this.$refs.nameInput?.focus();
        });
        window.addEventListener("keydown", this.onKey);
      } else {
        this.touched = false;
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
      else if (event.key === "Enter" && (event.metaKey || event.ctrlKey)) {
        this.handleSubmit();
      }
    },
    handleSubmit() {
      this.touched = true;
      if (!this.canSubmit) return;
      this.$emit("submit", {
        category: this.trimmedName,
        description: (this.description || "").trim(),
      });
    },
  },
  template: `
    <transition name="modal">
      <div v-if="visible" class="modal-mask" @click.self="$emit('close')">
        <div class="modal category-create-modal">
          <header>
            <h3>
              <Icon name="folder-plus" :size="17" style="vertical-align: -3px" />
              新建分类
            </h3>
            <button class="icon" @click="$emit('close')" title="关闭 (Esc)">
              <Icon name="x" :size="16" />
            </button>
          </header>

          <div class="modal-body">
            <div class="field">
              <label>分类名称</label>
              <div class="input-wrap">
                <span class="icon-slot"><Icon name="folder" :size="15" /></span>
                <input
                  ref="nameInput"
                  v-model="category"
                  placeholder="例如 memes / short-video / 猫片"
                  maxlength="32"
                />
              </div>
              <small class="muted">仅支持中英文、数字、下划线、连字符</small>
            </div>

            <div class="field">
              <label>描述（可选）</label>
              <textarea
                v-model="description"
                rows="2"
                placeholder="为这个分类写点说明，例如存放什么内容、用于什么场景"
              ></textarea>
            </div>

            <transition name="fade">
              <div v-if="errorMessage" class="category-create-error">
                <Icon name="alert-circle" :size="13" />
                {{ errorMessage }}
              </div>
            </transition>
          </div>

          <div class="modal-footer">
            <button @click="$emit('close')">取消</button>
            <button
              class="primary"
              :disabled="!canSubmit"
              @click="handleSubmit"
            >
              <Icon name="check" :size="15" />
              创建
            </button>
          </div>
        </div>
      </div>
    </transition>
  `,
};

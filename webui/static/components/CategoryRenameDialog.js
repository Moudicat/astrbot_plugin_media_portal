import { Icon } from "./Icon.js";

const CATEGORY_NAME_RE = /^[A-Za-z0-9_\u4e00-\u9fa5][A-Za-z0-9_\-\u4e00-\u9fa5]{0,31}$/;

export const CategoryRenameDialog = {
  name: "CategoryRenameDialog",
  components: { Icon },
  props: {
    visible: { type: Boolean, default: false },
    category: { type: Object, default: null },
    existing: { type: Array, default: () => [] },
  },
  emits: ["close", "submit"],
  data() {
    return {
      name: "",
      description: "",
      touched: false,
    };
  },
  computed: {
    oldName() {
      return (this.category && this.category.category) || "";
    },
    trimmedName() {
      return (this.name || "").trim();
    },
    duplicated() {
      if (!this.trimmedName) return false;
      if (this.trimmedName === this.oldName) return false;
      const lower = this.trimmedName.toLowerCase();
      return (this.existing || []).some(
        (item) =>
          item && (item.category || "").toString().toLowerCase() === lower,
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
    dirty() {
      return (
        this.trimmedName !== this.oldName ||
        (this.description || "").trim() !==
          ((this.category && this.category.description) || "")
      );
    },
    canSubmit() {
      return (
        !!this.trimmedName &&
        !this.invalidFormat &&
        !this.duplicated &&
        this.dirty
      );
    },
  },
  watch: {
    visible: {
      immediate: true,
      handler(value) {
        if (value) {
          this.reset();
          window.addEventListener("keydown", this.onKey);
          this.$nextTick(() => {
            const input = this.$refs.nameInput;
            if (input && typeof input.focus === "function") {
              input.focus();
              input.select?.();
            }
          });
        } else {
          window.removeEventListener("keydown", this.onKey);
        }
      },
    },
    category() {
      if (this.visible) this.reset();
    },
  },
  beforeUnmount() {
    window.removeEventListener("keydown", this.onKey);
  },
  methods: {
    reset() {
      this.name = this.oldName;
      this.description = (this.category && this.category.description) || "";
      this.touched = false;
    },
    onKey(event) {
      if (!this.visible) return;
      if (event.key === "Escape") {
        event.preventDefault();
        this.$emit("close");
      } else if (
        event.key === "Enter" &&
        (event.metaKey || event.ctrlKey)
      ) {
        event.preventDefault();
        this.handleSubmit();
      }
    },
    handleSubmit() {
      this.touched = true;
      if (!this.canSubmit) return;
      this.$emit("submit", {
        oldName: this.oldName,
        newName: this.trimmedName,
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
              <Icon name="pencil" :size="17" style="vertical-align: -3px" />
              重命名分类
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
                  v-model="name"
                  :placeholder="oldName"
                  maxlength="32"
                  @keydown.enter.prevent="handleSubmit"
                />
              </div>
              <small class="muted">仅支持中英文、数字、下划线、连字符</small>
            </div>

            <div class="field">
              <label>描述（可选）</label>
              <textarea
                v-model="description"
                rows="2"
                placeholder="补充这个分类的用途，便于自己或 AI 识别"
                maxlength="120"
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
              保存
            </button>
          </div>
        </div>
      </div>
    </transition>
  `,
};

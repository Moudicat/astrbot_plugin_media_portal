import { Icon } from "./Icon.js";

const CATEGORY_NAME_RE = /^[A-Za-z0-9_\u4e00-\u9fa5][A-Za-z0-9_\-\u4e00-\u9fa5]{0,31}$/;

export const BatchCategoryDialog = {
  name: "BatchCategoryDialog",
  components: { Icon },
  props: {
    visible: { type: Boolean, default: false },
    count: { type: Number, default: 0 },
    categories: { type: Array, default: () => [] },
    activeCategory: { type: String, default: "" },
  },
  emits: ["close", "submit"],
  data() {
    return {
      mode: "existing",
      selected: "",
      customName: "",
      touched: false,
      submitting: false,
    };
  },
  watch: {
    visible(value) {
      if (value) {
        this.mode = this.categories.length ? "existing" : "new";
        const active = this.activeCategory || "";
        const firstOther =
          (this.categories.find((c) => c && c.category !== active) || {})
            .category || "";
        this.selected =
          this.categories.length
            ? firstOther || (this.categories[0] && this.categories[0].category) || ""
            : "";
        this.customName = "";
        this.touched = false;
        this.submitting = false;
        window.addEventListener("keydown", this.onKey);
        this.$nextTick(() => {
          if (this.mode === "new") {
            this.$refs.customInput?.focus();
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
  computed: {
    trimmedCustom() {
      return (this.customName || "").trim();
    },
    customInvalid() {
      if (this.mode !== "new") return "";
      if (!this.trimmedCustom) return "请输入新分类名";
      if (!CATEGORY_NAME_RE.test(this.trimmedCustom))
        return "只能包含中英文、数字、下划线与连字符，长度 1-32";
      const lower = this.trimmedCustom.toLowerCase();
      const duplicated = (this.categories || []).some(
        (item) => item && (item.category || "").toString().toLowerCase() === lower,
      );
      if (duplicated) return "该分类已存在，请直接在上一页选择";
      return "";
    },
    errorMessage() {
      if (!this.touched) return "";
      if (this.mode === "existing" && !this.selected) return "请先选择目标分类";
      if (this.mode === "new") return this.customInvalid;
      return "";
    },
    canSubmit() {
      if (this.submitting) return false;
      if (this.mode === "existing") return !!this.selected;
      return !this.customInvalid;
    },
    targetLabel() {
      if (this.mode === "existing") return this.selected || "未选择";
      return this.trimmedCustom || "未填写";
    },
  },
  methods: {
    onKey(event) {
      if (!this.visible) return;
      if (event.key === "Escape") this.$emit("close");
      else if (event.key === "Enter" && (event.metaKey || event.ctrlKey)) {
        this.submit();
      }
    },
    selectMode(mode) {
      this.mode = mode;
      this.touched = false;
      this.$nextTick(() => {
        if (mode === "new") this.$refs.customInput?.focus();
      });
    },
    submit() {
      this.touched = true;
      if (!this.canSubmit) return;
      const category =
        this.mode === "existing" ? this.selected : this.trimmedCustom;
      if (!category) return;
      this.submitting = true;
      this.$emit("submit", { category });
    },
  },
  template: `
    <transition name="modal">
      <div v-if="visible" class="modal-mask" @click.self="$emit('close')">
        <div class="modal batch-category-modal">
          <header>
            <h3>
              <Icon name="folder-input" :size="17" style="vertical-align: -3px" />
              批量移动到分类
            </h3>
            <button class="icon" @click="$emit('close')" title="关闭 (Esc)">
              <Icon name="x" :size="16" />
            </button>
          </header>

          <div class="modal-body">
            <div class="batch-summary">
              <Icon name="check-check" :size="14" />
              <span>将对 <strong>{{ count }}</strong> 个选中媒体生效</span>
            </div>

            <div class="dialog-tabs">
              <button
                :class="{ active: mode === 'existing' }"
                :disabled="!categories.length"
                @click="selectMode('existing')"
              >
                选择已有分类
              </button>
              <button
                :class="{ active: mode === 'new' }"
                @click="selectMode('new')"
              >
                新建分类
              </button>
            </div>

            <div v-if="mode === 'existing'" class="field">
              <label>目标分类</label>
              <select v-model="selected">
                <option value="" disabled>请选择分类</option>
                <option
                  v-for="item in categories"
                  :key="item.category"
                  :value="item.category"
                >
                  {{ item.category }} · {{ item.count || 0 }}
                </option>
              </select>
            </div>

            <div v-else class="field">
              <label>新分类名称</label>
              <div class="input-wrap">
                <span class="icon-slot"><Icon name="folder-plus" :size="14" /></span>
                <input
                  ref="customInput"
                  v-model="customName"
                  maxlength="32"
                  placeholder="例如 memes / 随手拍"
                  @keydown.enter.prevent="submit"
                />
              </div>
              <small class="muted">不存在时会自动创建，仅支持中英文、数字、下划线、连字符</small>
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
              @click="submit"
            >
              <Icon name="check" :size="15" />
              移动到 {{ targetLabel }}
            </button>
          </div>
        </div>
      </div>
    </transition>
  `,
};

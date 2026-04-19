import { Icon } from "./Icon.js";

const CATEGORY_NAME_RE = /^[A-Za-z0-9_\u4e00-\u9fa5][A-Za-z0-9_\-\u4e00-\u9fa5]{0,31}$/;

function deriveState(categories) {
  return {
    editing: "",
    editingName: "",
    editingDescription: "",
    editingError: "",
    pruneBusy: false,
    deleting: "",
    snapshotKey: (categories || []).map((c) => c && c.category).join("|"),
  };
}

export const SettingsDialog = {
  name: "SettingsDialog",
  components: { Icon },
  props: {
    visible: { type: Boolean, default: false },
    categories: { type: Array, default: () => [] },
  },
  inject: {
    appConfirm: { from: "confirm", default: null },
  },
  emits: ["close", "rename-category", "delete-category", "prune-categories"],
  data() {
    return deriveState(this.categories);
  },
  watch: {
    visible(value) {
      if (value) {
        Object.assign(this, deriveState(this.categories));
        window.addEventListener("keydown", this.onKey);
      } else {
        window.removeEventListener("keydown", this.onKey);
      }
    },
    categories: {
      handler(value) {
        // 分类列表变化时如果不在编辑中则重置快照
        const key = (value || []).map((c) => c && c.category).join("|");
        if (!this.editing && key !== this.snapshotKey) {
          this.snapshotKey = key;
        }
      },
      deep: true,
    },
  },
  beforeUnmount() {
    window.removeEventListener("keydown", this.onKey);
  },
  methods: {
    onKey(event) {
      if (!this.visible) return;
      if (event.key === "Escape") {
        if (this.editing) {
          this.cancelEdit();
        } else {
          this.$emit("close");
        }
      }
    },
    startEdit(item) {
      if (!item || item.category === "default") return;
      this.editing = item.category;
      this.editingName = item.category;
      this.editingDescription = item.description || "";
      this.editingError = "";
      this.$nextTick(() => {
        const el = this.$refs[`name_${item.category}`];
        const input = Array.isArray(el) ? el[0] : el;
        if (input && typeof input.focus === "function") {
          input.focus();
          input.select?.();
        }
      });
    },
    cancelEdit() {
      this.editing = "";
      this.editingName = "";
      this.editingDescription = "";
      this.editingError = "";
    },
    validate(newName) {
      const trimmed = (newName || "").trim();
      if (!trimmed) return "分类名称不能为空";
      if (!CATEGORY_NAME_RE.test(trimmed))
        return "只能包含中英文、数字、下划线与连字符，长度 1-32";
      if (trimmed === this.editing) return "";
      const lower = trimmed.toLowerCase();
      const duplicated = (this.categories || []).some(
        (item) => item && (item.category || "").toString().toLowerCase() === lower,
      );
      if (duplicated) return "该分类已存在";
      return "";
    },
    async submitEdit() {
      const err = this.validate(this.editingName);
      if (err) {
        this.editingError = err;
        return;
      }
      const payload = {
        oldName: this.editing,
        newName: (this.editingName || "").trim(),
        description: (this.editingDescription || "").trim(),
      };
      this.$emit("rename-category", payload);
      this.cancelEdit();
    },
    async confirmDelete(item) {
      if (!item || item.category === "default") return;
      const count = Number(item.count || 0);
      const message =
        count > 0
          ? `分类「${item.category}」下还有 ${count} 个媒体，删除将一并清理。`
          : `确认删除分类「${item.category}」？`;
      const detail =
        count > 0
          ? "所有归属该分类的媒体记录与文件会被移除，无法撤销。"
          : "";
      const ok = this.appConfirm
        ? await this.appConfirm({
            title: "删除分类",
            message,
            detail,
            confirmText: "删除分类",
            tone: "danger",
            icon: "trash-2",
          })
        : window.confirm(message);
      if (!ok) return;
      this.deleting = item.category;
      this.$emit("delete-category", {
        category: item.category,
        removeFiles: true,
      });
    },
    onPrune() {
      this.pruneBusy = true;
      this.$emit("prune-categories");
      // 由父级负责实际调用；这里仅短暂锁定按钮避免重复点击
      setTimeout(() => {
        this.pruneBusy = false;
      }, 1200);
    },
    formattedSize(item) {
      return item?.size_human || "";
    },
    isProtected(item) {
      return item && item.category === "default";
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
                  <strong>分类管理</strong>
                  <small class="muted">重命名、调整描述或删除非默认分类</small>
                </div>
                <span class="chip mono">共 {{ categories.length }}</span>
              </div>

              <div v-if="!categories.length" class="settings-empty">
                <Icon name="folder-x" :size="18" />
                <span>暂无分类数据</span>
              </div>

              <ul v-else class="settings-category-list">
                <li
                  v-for="item in categories"
                  :key="item.category"
                  class="settings-category-row"
                  :class="{ editing: editing === item.category, protected: isProtected(item) }"
                >
                  <template v-if="editing === item.category">
                    <div class="settings-edit-form">
                      <div class="field">
                        <label>分类名</label>
                        <div class="input-wrap">
                          <span class="icon-slot"><Icon name="folder" :size="14" /></span>
                          <input
                            :ref="'name_' + item.category"
                            v-model="editingName"
                            maxlength="32"
                            @keydown.enter.prevent="submitEdit"
                            @keydown.esc.prevent="cancelEdit"
                          />
                        </div>
                      </div>
                      <div class="field">
                        <label>描述</label>
                        <input
                          v-model="editingDescription"
                          placeholder="简短描述，帮助自己或 AI 分辨用途"
                          maxlength="120"
                        />
                      </div>
                      <div v-if="editingError" class="settings-edit-error">
                        <Icon name="alert-circle" :size="13" /> {{ editingError }}
                      </div>
                      <div class="settings-edit-actions">
                        <button @click="cancelEdit">取消</button>
                        <button class="primary" @click="submitEdit">
                          <Icon name="check" :size="14" /> 保存
                        </button>
                      </div>
                    </div>
                  </template>
                  <template v-else>
                    <div class="settings-category-main">
                      <div class="settings-category-icon"><Icon name="folder" :size="16" /></div>
                      <div class="settings-category-info">
                        <div class="settings-category-name">
                          {{ item.category }}
                          <span v-if="isProtected(item)" class="chip tiny">默认</span>
                        </div>
                        <small class="muted">
                          {{ item.count || 0 }} 个
                          <span v-if="formattedSize(item)"> · {{ formattedSize(item) }}</span>
                          <span v-if="item.description"> · {{ item.description }}</span>
                        </small>
                      </div>
                    </div>
                    <div class="settings-category-actions">
                      <button
                        class="icon sm"
                        :disabled="isProtected(item)"
                        :title="isProtected(item) ? '默认分类不可重命名' : '重命名 / 改描述'"
                        @click="startEdit(item)"
                      >
                        <Icon name="pencil" :size="14" />
                      </button>
                      <button
                        class="icon sm danger"
                        :disabled="isProtected(item) || deleting === item.category"
                        :title="isProtected(item) ? '默认分类不可删除' : '删除分类'"
                        @click="confirmDelete(item)"
                      >
                        <Icon name="trash-2" :size="14" />
                      </button>
                    </div>
                  </template>
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

<template>
  <transition name="modal">
    <div v-if="visible" class="modal-mask" @click.self="$emit('close')">
      <div class="modal category-create-modal">
        <header>
          <h3>
            <Icon name="pencil" :size="17" style="vertical-align: -3px" />
            {{ $t("categoryRename.title") }}
          </h3>
          <button class="icon" :title="$t('common.closeEsc')" @click="$emit('close')">
            <Icon name="x" :size="16" />
          </button>
        </header>

        <div class="modal-body">
          <div class="field">
            <label>{{ $t("categoryRename.nameLabel") }}</label>
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
            <small class="muted">{{ $t("categoryRename.nameHint") }}</small>
          </div>

          <div class="field">
            <label>{{ $t("categoryRename.descLabel") }}</label>
            <textarea
              v-model="description"
              rows="2"
              :placeholder="$t('categoryRename.descPlaceholder')"
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
          <button @click="$emit('close')">{{ $t("common.cancel") }}</button>
          <button class="primary" :disabled="!canSubmit" @click="handleSubmit">
            <Icon name="check" :size="15" />
            {{ $t("common.save") }}
          </button>
        </div>
      </div>
    </div>
  </transition>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import Icon from "@/components/common/Icon.vue";
import type { CategoryItem } from "@/api/types";

const CATEGORY_NAME_RE = /^[A-Za-z0-9_\u4e00-\u9fa5][A-Za-z0-9_\-\u4e00-\u9fa5]{0,31}$/;

interface Props {
  visible?: boolean;
  category?: CategoryItem | null;
  existing?: CategoryItem[];
}

const props = withDefaults(defineProps<Props>(), {
  visible: false,
  category: null,
  existing: () => [],
});

const emit = defineEmits<{
  (e: "close"): void;
  (e: "submit", payload: { oldName: string; newName: string; description: string }): void;
}>();

const { t } = useI18n();

const name = ref("");
const description = ref("");
const touched = ref(false);
const nameInput = ref<HTMLInputElement | null>(null);

const oldName = computed(() => (props.category && props.category.category) || "");
const trimmedName = computed(() => (name.value || "").trim());

const duplicated = computed(() => {
  if (!trimmedName.value) return false;
  if (trimmedName.value === oldName.value) return false;
  const lower = trimmedName.value.toLowerCase();
  return (props.existing || []).some(
    (item) => item && (item.category || "").toString().toLowerCase() === lower,
  );
});

const invalidFormat = computed(() => {
  if (!trimmedName.value) return false;
  return !CATEGORY_NAME_RE.test(trimmedName.value);
});

const errorMessage = computed(() => {
  if (!touched.value) return "";
  if (!trimmedName.value) return t("categoryRename.errEmpty");
  if (invalidFormat.value) return t("categoryRename.errInvalid");
  if (duplicated.value) return t("categoryRename.errDuplicate");
  return "";
});

const dirty = computed(
  () =>
    trimmedName.value !== oldName.value ||
    (description.value || "").trim() !== ((props.category && props.category.description) || ""),
);

const canSubmit = computed(
  () => !!trimmedName.value && !invalidFormat.value && !duplicated.value && dirty.value,
);

function reset() {
  name.value = oldName.value;
  description.value = (props.category && props.category.description) || "";
  touched.value = false;
}

function onKey(event: KeyboardEvent) {
  if (!props.visible) return;
  if (event.key === "Escape") {
    event.preventDefault();
    emit("close");
  } else if (event.key === "Enter" && (event.metaKey || event.ctrlKey)) {
    event.preventDefault();
    handleSubmit();
  }
}

watch(
  () => props.visible,
  (value) => {
    if (value) {
      reset();
      window.addEventListener("keydown", onKey);
      nextTick(() => {
        const input = nameInput.value;
        if (input && typeof input.focus === "function") {
          input.focus();
          (input as any).select?.();
        }
      });
    } else {
      window.removeEventListener("keydown", onKey);
    }
  },
  { immediate: true },
);

watch(
  () => props.category,
  () => {
    if (props.visible) reset();
  },
);

onBeforeUnmount(() => {
  window.removeEventListener("keydown", onKey);
});

function handleSubmit() {
  touched.value = true;
  if (!canSubmit.value) return;
  emit("submit", {
    oldName: oldName.value,
    newName: trimmedName.value,
    description: (description.value || "").trim(),
  });
}
</script>

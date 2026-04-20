<template>
  <transition name="modal">
    <div v-if="visible" class="modal-mask" @click.self="$emit('close')">
      <div class="modal category-create-modal">
        <header>
          <h3>
            <Icon name="folder-plus" :size="17" style="vertical-align: -3px" />
            {{ $t("categoryCreate.title") }}
          </h3>
          <button class="icon" :title="$t('common.closeEsc')" @click="$emit('close')">
            <Icon name="x" :size="16" />
          </button>
        </header>

        <div class="modal-body">
          <div class="field">
            <label>{{ $t("categoryCreate.nameLabel") }}</label>
            <div class="input-wrap">
              <span class="icon-slot"><Icon name="folder" :size="15" /></span>
              <input
                ref="nameInput"
                v-model="category"
                :placeholder="$t('categoryCreate.namePlaceholder')"
                maxlength="32"
              />
            </div>
            <small class="muted">{{ $t("categoryCreate.nameHint") }}</small>
          </div>

          <div class="field">
            <label>{{ $t("categoryCreate.descLabel") }}</label>
            <textarea
              v-model="description"
              rows="2"
              :placeholder="$t('categoryCreate.descPlaceholder')"
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
            {{ $t("categoryCreate.submit") }}
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
  existing?: CategoryItem[];
}

const props = withDefaults(defineProps<Props>(), {
  visible: false,
  existing: () => [],
});

const emit = defineEmits<{
  (e: "close"): void;
  (e: "submit", payload: { category: string; description: string }): void;
}>();

const { t } = useI18n();

const category = ref("");
const description = ref("");
const touched = ref(false);
const nameInput = ref<HTMLInputElement | null>(null);

const trimmedName = computed(() => (category.value || "").trim());

const duplicated = computed(() => {
  if (!trimmedName.value) return false;
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
  if (!trimmedName.value) return t("categoryCreate.errEmpty");
  if (invalidFormat.value) return t("categoryCreate.errInvalid");
  if (duplicated.value) return t("categoryCreate.errDuplicate");
  return "";
});

const canSubmit = computed(
  () => !!trimmedName.value && !invalidFormat.value && !duplicated.value,
);

function onKey(event: KeyboardEvent) {
  if (!props.visible) return;
  if (event.key === "Escape") emit("close");
  else if (event.key === "Enter" && (event.metaKey || event.ctrlKey)) handleSubmit();
}

watch(
  () => props.visible,
  (value) => {
    if (value) {
      category.value = "";
      description.value = "";
      touched.value = false;
      nextTick(() => nameInput.value?.focus());
      window.addEventListener("keydown", onKey);
    } else {
      touched.value = false;
      window.removeEventListener("keydown", onKey);
    }
  },
);

onBeforeUnmount(() => {
  window.removeEventListener("keydown", onKey);
});

function handleSubmit() {
  touched.value = true;
  if (!canSubmit.value) return;
  emit("submit", {
    category: trimmedName.value,
    description: (description.value || "").trim(),
  });
}
</script>

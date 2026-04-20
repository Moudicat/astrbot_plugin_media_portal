<template>
  <transition name="modal">
    <div v-if="visible" class="modal-mask" @click.self="$emit('close')">
      <div class="modal batch-category-modal">
        <header>
          <h3>
            <Icon name="folder-input" :size="17" style="vertical-align: -3px" />
            {{ $t("batchCategory.title") }}
          </h3>
          <button class="icon" :title="$t('common.closeEsc')" @click="$emit('close')">
            <Icon name="x" :size="16" />
          </button>
        </header>

        <div class="modal-body">
          <div class="batch-summary">
            <Icon name="check-check" :size="14" />
            <i18n-t keypath="batchCategory.summary" tag="span">
              <template #count>
                <strong>{{ count }}</strong>
              </template>
            </i18n-t>
          </div>

          <div class="dialog-tabs">
            <button
              :class="{ active: mode === 'existing' }"
              :disabled="!categories.length"
              @click="selectMode('existing')"
            >
              {{ $t("batchCategory.tabExisting") }}
            </button>
            <button :class="{ active: mode === 'new' }" @click="selectMode('new')">
              {{ $t("batchCategory.tabNew") }}
            </button>
          </div>

          <div v-if="mode === 'existing'" class="field">
            <label>{{ $t("batchCategory.targetLabel") }}</label>
            <select v-model="selected">
              <option value="" disabled>{{ $t("batchCategory.selectHint") }}</option>
              <option v-for="item in categories" :key="item.category" :value="item.category">
                {{ item.category }} · {{ item.count || 0 }}
              </option>
            </select>
          </div>

          <div v-else class="field">
            <label>{{ $t("batchCategory.newLabel") }}</label>
            <div class="input-wrap">
              <span class="icon-slot"><Icon name="folder-plus" :size="14" /></span>
              <input
                ref="customInput"
                v-model="customName"
                maxlength="32"
                :placeholder="$t('batchCategory.newPlaceholder')"
                @keydown.enter.prevent="submit"
              />
            </div>
            <small class="muted">{{ $t("batchCategory.newHint") }}</small>
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
          <button class="primary" :disabled="!canSubmit" @click="submit">
            <Icon name="check" :size="15" />
            {{ $t("batchCategory.submit", { target: targetLabel }) }}
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
  count?: number;
  categories?: CategoryItem[];
  activeCategory?: string;
}

const props = withDefaults(defineProps<Props>(), {
  visible: false,
  count: 0,
  categories: () => [],
  activeCategory: "",
});

const emit = defineEmits<{
  (e: "close"): void;
  (e: "submit", payload: { category: string }): void;
}>();

const { t } = useI18n();

const mode = ref<"existing" | "new">("existing");
const selected = ref("");
const customName = ref("");
const touched = ref(false);
const submitting = ref(false);
const customInput = ref<HTMLInputElement | null>(null);

const trimmedCustom = computed(() => (customName.value || "").trim());

const customInvalid = computed(() => {
  if (mode.value !== "new") return "";
  if (!trimmedCustom.value) return t("batchCategory.errEmpty");
  if (!CATEGORY_NAME_RE.test(trimmedCustom.value)) return t("batchCategory.errInvalid");
  const lower = trimmedCustom.value.toLowerCase();
  const duplicated = (props.categories || []).some(
    (item) => item && (item.category || "").toString().toLowerCase() === lower,
  );
  if (duplicated) return t("batchCategory.errDuplicate");
  return "";
});

const errorMessage = computed(() => {
  if (!touched.value) return "";
  if (mode.value === "existing" && !selected.value) return t("batchCategory.errSelect");
  if (mode.value === "new") return customInvalid.value;
  return "";
});

const canSubmit = computed(() => {
  if (submitting.value) return false;
  if (mode.value === "existing") return !!selected.value;
  return !customInvalid.value;
});

const targetLabel = computed(() => {
  if (mode.value === "existing") return selected.value || t("batchCategory.unselected");
  return trimmedCustom.value || t("batchCategory.unfilled");
});

function onKey(event: KeyboardEvent) {
  if (!props.visible) return;
  if (event.key === "Escape") emit("close");
  else if (event.key === "Enter" && (event.metaKey || event.ctrlKey)) submit();
}

watch(
  () => props.visible,
  (value) => {
    if (value) {
      mode.value = props.categories.length ? "existing" : "new";
      const active = props.activeCategory || "";
      const firstOther =
        (props.categories.find((c) => c && c.category !== active) || ({} as CategoryItem))
          .category || "";
      selected.value = props.categories.length
        ? firstOther ||
          (props.categories[0] && props.categories[0].category) ||
          ""
        : "";
      customName.value = "";
      touched.value = false;
      submitting.value = false;
      window.addEventListener("keydown", onKey);
      nextTick(() => {
        if (mode.value === "new") customInput.value?.focus();
      });
    } else {
      window.removeEventListener("keydown", onKey);
    }
  },
);

onBeforeUnmount(() => {
  window.removeEventListener("keydown", onKey);
});

function selectMode(next: "existing" | "new") {
  mode.value = next;
  touched.value = false;
  nextTick(() => {
    if (next === "new") customInput.value?.focus();
  });
}

function submit() {
  touched.value = true;
  if (!canSubmit.value) return;
  const category = mode.value === "existing" ? selected.value : trimmedCustom.value;
  if (!category) return;
  submitting.value = true;
  emit("submit", { category });
}
</script>

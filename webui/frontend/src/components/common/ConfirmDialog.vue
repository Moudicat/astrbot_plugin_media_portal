<template>
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
          <button class="icon sm plain-ish" type="button" :title="$t('common.close') + ' (Esc)'" @click="onCancel">
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
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, watch } from "vue";
import Icon from "./Icon.vue";

interface Props {
  visible?: boolean;
  title?: string;
  message?: string;
  detail?: string;
  confirmText?: string;
  cancelText?: string;
  tone?: string;
  icon?: string;
  loading?: boolean;
}

const props = withDefaults(defineProps<Props>(), {
  visible: false,
  title: "请确认",
  message: "",
  detail: "",
  confirmText: "确认",
  cancelText: "取消",
  tone: "primary",
  icon: "",
  loading: false,
});

const emit = defineEmits<{
  (e: "confirm"): void;
  (e: "cancel"): void;
}>();

const TONE_ICON: Record<string, string> = {
  danger: "alert-triangle",
  warning: "alert-triangle",
  primary: "help-circle",
  info: "info",
  success: "check-circle",
};
const TONE_BUTTON: Record<string, string> = {
  danger: "danger",
  warning: "accent",
  primary: "primary",
  info: "primary",
  success: "accent",
};

const confirmBtn = ref<HTMLButtonElement | null>(null);
const toneKey = computed(() => (TONE_ICON[props.tone] ? props.tone : "primary"));
const headIcon = computed(() => props.icon || TONE_ICON[toneKey.value] || "help-circle");
const confirmBtnClass = computed(() => TONE_BUTTON[toneKey.value] || "primary");

function onKey(event: KeyboardEvent) {
  if (!props.visible) return;
  if (event.key === "Escape") {
    event.preventDefault();
    onCancel();
  } else if (event.key === "Enter") {
    event.preventDefault();
    onConfirm();
  }
}

watch(
  () => props.visible,
  (value) => {
    if (value) {
      window.addEventListener("keydown", onKey);
      nextTick(() => confirmBtn.value?.focus());
    } else {
      window.removeEventListener("keydown", onKey);
    }
  },
);
onBeforeUnmount(() => window.removeEventListener("keydown", onKey));

function onCancel() {
  if (props.loading) return;
  emit("cancel");
}
function onConfirm() {
  if (props.loading) return;
  emit("confirm");
}
</script>

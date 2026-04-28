<template>
  <transition name="modal">
    <div v-if="visible" class="modal-mask" @click.self="$emit('close')">
      <div class="modal intelligence-modal">
        <header>
          <h3>
            <Icon
              name="brain-circuit"
              :size="17"
              style="vertical-align: -3px"
            />
            {{ $t("settings.intelligence.title") }}
          </h3>
          <button
            class="icon"
            :title="$t('common.closeEsc')"
            @click="$emit('close')"
          >
            <Icon name="x" :size="16" />
          </button>
        </header>

        <p class="intelligence-modal-hint muted small">
          {{ $t("settings.intelligence.dialogSubtitle") }}
        </p>

        <div class="modal-body">
          <IntelligenceSection />
        </div>

        <div class="modal-footer">
          <button class="primary" @click="$emit('close')">
            <Icon name="check" :size="14" />
            <span>{{ $t("common.done") }}</span>
          </button>
        </div>
      </div>
    </div>
  </transition>
</template>

<script setup lang="ts">
import { onBeforeUnmount, watch } from "vue";
import Icon from "@/components/common/Icon.vue";
import IntelligenceSection from "@/components/settings/IntelligenceSection.vue";

interface Props {
  visible?: boolean;
}

const props = withDefaults(defineProps<Props>(), { visible: false });
const emit = defineEmits<{
  (e: "close"): void;
}>();

function onKey(event: KeyboardEvent) {
  if (!props.visible) return;
  if (event.key === "Escape") emit("close");
}

watch(
  () => props.visible,
  (value) => {
    if (value) {
      window.addEventListener("keydown", onKey);
    } else {
      window.removeEventListener("keydown", onKey);
    }
  },
);

onBeforeUnmount(() => {
  window.removeEventListener("keydown", onKey);
});
</script>

<style scoped>
.intelligence-modal {
  width: min(760px, 96vw);
  max-height: 92vh;
}

.intelligence-modal-hint {
  margin: -4px 0 0;
  line-height: 1.55;
}
</style>

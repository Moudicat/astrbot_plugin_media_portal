<template>
  <teleport to="body">
    <transition name="context-menu">
      <div
        v-if="visible"
        class="context-menu-mask"
        @mousedown.self="$emit('close')"
        @contextmenu.prevent="$emit('close')"
      >
        <ul
          ref="menu"
          class="context-menu"
          :class="{ ready }"
          :style="{ left: pos.left + 'px', top: pos.top + 'px' }"
          role="menu"
        >
          <template v-for="(item, idx) in items" :key="item.key || 'd_' + idx">
            <li v-if="item.divider" class="context-menu-divider" role="separator"></li>
            <li
              v-else
              class="context-menu-item"
              :class="['tone-' + (item.tone || 'default'), { disabled: item.disabled }]"
              role="menuitem"
              @click="pick(item)"
            >
              <span class="context-menu-icon">
                <Icon v-if="item.icon" :name="item.icon" :size="14" />
              </span>
              <span class="context-menu-label">{{ item.label }}</span>
              <span v-if="item.shortcut" class="context-menu-shortcut">{{ item.shortcut }}</span>
            </li>
          </template>
        </ul>
      </div>
    </transition>
  </teleport>
</template>

<script setup lang="ts">
import { nextTick, onBeforeUnmount, ref, watch } from "vue";
import Icon from "./Icon.vue";
import type { ContextMenuEntry } from "@/api/types";

interface Props {
  visible: boolean;
  x?: number;
  y?: number;
  items: ContextMenuEntry[];
}

const props = withDefaults(defineProps<Props>(), { x: 0, y: 0 });
const emit = defineEmits<{
  (e: "close"): void;
  (e: "select", key: string): void;
}>();

const menu = ref<HTMLUListElement | null>(null);
const pos = ref({ left: props.x, top: props.y });
const ready = ref(false);

function onKey(event: KeyboardEvent) {
  if (!props.visible) return;
  if (event.key === "Escape") {
    event.preventDefault();
    emit("close");
  }
}
function onWinChange() {
  emit("close");
}

function adjust() {
  const el = menu.value;
  if (!el) return;
  const margin = 8;
  const rect = el.getBoundingClientRect();
  const vw = window.innerWidth || document.documentElement.clientWidth;
  const vh = window.innerHeight || document.documentElement.clientHeight;
  let left = props.x;
  let top = props.y;
  if (left + rect.width + margin > vw) {
    left = Math.max(margin, vw - rect.width - margin);
  }
  if (top + rect.height + margin > vh) {
    top = Math.max(margin, vh - rect.height - margin);
  }
  if (left < margin) left = margin;
  if (top < margin) top = margin;
  pos.value = { left, top };
  ready.value = true;
}

watch(
  () => props.visible,
  (value) => {
    if (value) {
      ready.value = false;
      pos.value = { left: props.x, top: props.y };
      nextTick(adjust);
      window.addEventListener("keydown", onKey);
      window.addEventListener("resize", onWinChange);
      window.addEventListener("scroll", onWinChange, true);
    } else {
      window.removeEventListener("keydown", onKey);
      window.removeEventListener("resize", onWinChange);
      window.removeEventListener("scroll", onWinChange, true);
    }
  },
  { immediate: true },
);
watch([() => props.x, () => props.y], () => {
  if (props.visible) {
    ready.value = false;
    pos.value = { left: props.x, top: props.y };
    nextTick(adjust);
  }
});
onBeforeUnmount(() => {
  window.removeEventListener("keydown", onKey);
  window.removeEventListener("resize", onWinChange);
  window.removeEventListener("scroll", onWinChange, true);
});

function pick(item: ContextMenuEntry) {
  if (!item || item.disabled || item.divider) return;
  emit("select", item.key || "");
  emit("close");
}
</script>

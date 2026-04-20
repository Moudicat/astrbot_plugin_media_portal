<template>
  <transition name="audio-dock">
    <div
      v-if="item"
      class="audio-dock"
      :class="{ 'is-mini': minimized }"
      role="region"
      :aria-label="$t('audioDock.aria')"
    >
      <div class="avatar" @click="minimized && toggleMinimized()">
        <Icon name="music" :size="18" />
      </div>
      <div class="audio-dock-meta">
        <strong :title="title">{{ title }}</strong>
        <small>{{ item.category || "data" }}</small>
      </div>
      <div class="audio-dock-controls">
        <button
          class="icon"
          :title="minimized ? $t('audioDock.expand') : $t('audioDock.minimize')"
          @click="toggleMinimized"
        >
          <Icon :name="minimized ? 'chevron-up' : 'chevron-down'" :size="16" />
        </button>
        <button class="icon" :title="$t('audioDock.close')" @click="$emit('close')">
          <Icon name="x" :size="16" />
        </button>
      </div>
      <audio v-show="!minimized" :src="sourceUrl" controls autoplay preload="metadata"></audio>
    </div>
  </transition>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from "vue";
import Icon from "@/components/common/Icon.vue";
import type { MediaItem } from "@/api/types";

interface AudioItem extends Partial<MediaItem> {
  directUrl?: string;
  name?: string;
}

interface Props {
  item?: AudioItem | null;
  readonlyToken?: string;
}

const props = withDefaults(defineProps<Props>(), {
  item: null,
  readonlyToken: "",
});

defineEmits<{
  (e: "close"): void;
}>();

const minimized = ref(false);

watch(
  () => props.item,
  (value) => {
    if (value) minimized.value = false;
    if (typeof document !== "undefined") {
      document.body.classList.toggle("audio-dock-active", !!value);
    }
  },
  { immediate: true },
);

watch(minimized, (value) => {
  if (typeof document !== "undefined") {
    document.body.classList.toggle("audio-dock-mini", !!value);
  }
});

onBeforeUnmount(() => {
  if (typeof document !== "undefined") {
    document.body.classList.remove("audio-dock-active");
    document.body.classList.remove("audio-dock-mini");
  }
});

const sourceUrl = computed(() => {
  const it = props.item;
  if (!it) return "";
  if (it.directUrl) return it.directUrl;
  if (!it.category || !it.filename) return "";
  const token = props.readonlyToken ? `?token=${encodeURIComponent(props.readonlyToken)}` : "";
  return `/files/${encodeURIComponent(it.category)}/${encodeURIComponent(it.filename)}${token}`;
});

const title = computed(() => {
  if (!props.item) return "";
  return props.item.filename || props.item.name || "";
});

function toggleMinimized() {
  minimized.value = !minimized.value;
}
</script>

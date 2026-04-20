<template>
  <transition name="modal">
    <div v-if="visible" class="player-mask" @click.self="$emit('close')">
      <div class="player-topbar">
        <div style="min-width: 0; display: flex; flex-direction: column">
          <strong style="white-space: nowrap; overflow: hidden; text-overflow: ellipsis">
            {{ displayName }}
          </strong>
          <span class="meta">
            <span v-if="item?.category">{{ item.category }}</span>
            <span v-if="item?.kind"> · {{ item.kind }}</span>
            <span v-if="item?.size_human"> · {{ item.size_human }}</span>
          </span>
        </div>
        <div class="actions">
          <button class="icon" :title="$t('player.copyLink')" @click="copyLink">
            <Icon name="link-2" :size="16" />
          </button>
          <button
            class="icon"
            :disabled="!sourceUrl"
            :title="$t('player.openNewTab')"
            @click="openInNewTab"
          >
            <Icon name="external-link" :size="16" />
          </button>
          <button class="icon" :title="$t('player.close')" @click="$emit('close')">
            <Icon name="x" :size="16" />
          </button>
        </div>
      </div>

      <div v-if="item" class="player-body" @click.self="$emit('close')">
        <button
          v-if="canNavigate"
          class="player-nav prev"
          :title="$t('player.prev')"
          @click.stop="$emit('prev')"
        >
          <Icon name="chevron-left" :size="20" />
        </button>
        <img v-if="item.kind === 'image'" :src="sourceUrl" :alt="displayName" />
        <video
          v-else-if="item.kind === 'video'"
          :src="sourceUrl"
          controls
          playsinline
          autoplay
          preload="metadata"
        ></video>
        <audio
          v-else-if="item.kind === 'audio'"
          :src="sourceUrl"
          controls
          autoplay
          preload="metadata"
        ></audio>
        <div v-else class="empty">
          <div class="illus"><Icon name="file-question" :size="28" /></div>
          <strong>{{ $t("player.unsupportedTitle") }}</strong>
          <span>{{ $t("player.unsupportedHint") }}</span>
        </div>
        <button
          v-if="canNavigate"
          class="player-nav next"
          :title="$t('player.next')"
          @click.stop="$emit('next')"
        >
          <Icon name="chevron-right" :size="20" />
        </button>
      </div>
    </div>
  </transition>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, watch } from "vue";
import { useI18n } from "vue-i18n";
import Icon from "@/components/common/Icon.vue";
import type { MediaItem } from "@/api/types";

interface PlayerItem extends Partial<MediaItem> {
  directUrl?: string;
  name?: string;
}

interface Props {
  visible?: boolean;
  item?: PlayerItem | null;
  readonlyToken?: string;
  canNavigate?: boolean;
}

const props = withDefaults(defineProps<Props>(), {
  visible: false,
  item: null,
  readonlyToken: "",
  canNavigate: true,
});

const emit = defineEmits<{
  (e: "close"): void;
  (e: "next"): void;
  (e: "prev"): void;
  (e: "copy-link", payload: { id?: string | number; url?: string }): void;
}>();

const { t } = useI18n();

const sourceUrl = computed(() => {
  const it = props.item;
  if (!it) return "";
  if (it.directUrl) return it.directUrl;
  if (!it.category || !it.filename) return "";
  const token = props.readonlyToken ? `?token=${encodeURIComponent(props.readonlyToken)}` : "";
  return `/files/${encodeURIComponent(it.category)}/${encodeURIComponent(it.filename)}${token}`;
});

const displayName = computed(() => props.item?.filename || props.item?.name || t("player.fallbackName"));

function onKey(event: KeyboardEvent) {
  if (!props.visible) return;
  if (event.key === "Escape") emit("close");
  else if (event.key === "ArrowLeft") emit("prev");
  else if (event.key === "ArrowRight") emit("next");
}

watch(
  () => props.visible,
  (value) => {
    if (value) window.addEventListener("keydown", onKey);
    else window.removeEventListener("keydown", onKey);
  },
  { immediate: true },
);

onBeforeUnmount(() => {
  window.removeEventListener("keydown", onKey);
});

function openInNewTab() {
  if (!sourceUrl.value) return;
  let target = sourceUrl.value;
  try {
    target = new URL(sourceUrl.value, window.location.origin).toString();
  } catch (_e) {
    // keep as-is
  }
  window.open(target, "_blank", "noopener");
}

function copyLink() {
  if (!props.item) return;
  if (props.item.id != null) {
    emit("copy-link", { id: props.item.id });
    return;
  }
  if (sourceUrl.value) emit("copy-link", { url: sourceUrl.value });
}
</script>

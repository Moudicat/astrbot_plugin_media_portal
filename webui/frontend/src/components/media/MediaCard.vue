<template>
  <article class="media-card" :class="{ selected }" @contextmenu.prevent="onContext">
    <div class="media-preview" @click="$emit('preview', item)">
      <img
        v-if="item.kind === 'image'"
        :src="previewSrc"
        :alt="item.filename"
        loading="lazy"
        decoding="async"
        :class="{ loaded: imageLoaded }"
        @load="handleImgLoad"
        @error="handleImgError"
      />
      <video
        v-else-if="item.kind === 'video'"
        :src="fileUrl"
        muted
        preload="metadata"
        playsinline
      ></video>
      <div v-else-if="item.kind === 'audio'" class="audio-placeholder">
        <div class="disc"><Icon name="music" :size="24" /></div>
        <small>{{ item.filename }}</small>
      </div>
      <div v-else class="file-placeholder">
        <Icon name="file" :size="28" />
        <small>{{ item.kind || "file" }}</small>
      </div>

      <div class="preview-overlay">
        <span class="preview-kind">
          <Icon :name="kindMeta.icon" :size="12" />
          {{ kindMeta.label }}
        </span>
        <span v-if="durationLabel" class="preview-duration">
          <Icon name="clock" :size="11" />
          {{ durationLabel }}
        </span>
        <div class="preview-actions" @click.stop>
          <button class="icon sm" :title="$t('card.copyLink')" @click="$emit('copy-link', item.id)">
            <Icon name="link-2" :size="14" />
          </button>
          <button class="icon sm" :title="$t('card.detail')" @click="$emit('detail', item)">
            <Icon name="settings-2" :size="14" />
          </button>
        </div>
      </div>
    </div>

    <div class="media-card-body">
      <label class="card-check" @click.stop>
        <input
          type="checkbox"
          :checked="selected"
          @change="$emit('toggle-select', item.id)"
        />
      </label>
      <div class="card-meta">
        <strong
          :title="item.filename"
          :class="{ 'meta-name-clickable': ui.gridMode === 'list' }"
          @click="onNameClick"
        >{{ item.filename }}</strong>
        <div class="sub">
          <span>{{ item.category }}</span>
          <span class="dot"></span>
          <span class="mono">{{ sizeLabel }}</span>
          <template v-if="dateLabel">
            <span class="dot"></span>
            <span class="mono">{{ dateLabel }}</span>
          </template>
        </div>
      </div>
      <div v-if="ui.gridMode === 'list'" class="list-actions" @click.stop>
        <button
          type="button"
          class="icon sm"
          :title="$t('card.copyLink')"
          :aria-label="$t('card.copyLink')"
          @click="$emit('copy-link', item.id)"
        >
          <Icon name="link-2" :size="14" />
        </button>
        <button
          type="button"
          class="icon sm"
          :title="$t('card.detail')"
          :aria-label="$t('card.detail')"
          @click="$emit('detail', item)"
        >
          <Icon name="settings-2" :size="14" />
        </button>
      </div>
    </div>
  </article>
</template>

<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import Icon from "@/components/common/Icon.vue";
import { buildMediaDirectUrl, buildThumbUrl } from "@/utils/url";
import { formatDateShort, formatDuration } from "@/utils/format";
import { useUiStore } from "@/stores/ui";
import type { MediaItem } from "@/api/types";

const ui = useUiStore();

interface Props {
  item: MediaItem;
  selected?: boolean;
  readonlyToken?: string;
}

const props = withDefaults(defineProps<Props>(), {
  selected: false,
  readonlyToken: "",
});

const emit = defineEmits<{
  (e: "toggle-select", id: string | number): void;
  (e: "preview", item: MediaItem): void;
  (e: "detail", item: MediaItem): void;
  (e: "copy-link", id: string | number): void;
  (e: "context-media", payload: { event: MouseEvent; item: MediaItem }): void;
}>();

const { t } = useI18n();

const imageLoaded = ref(false);
const imageError = ref(false);

watch(
  () => props.item.id,
  () => {
    imageLoaded.value = false;
    imageError.value = false;
  },
);

const fileUrl = computed(() =>
  buildMediaDirectUrl(props.item.category, props.item.filename, props.readonlyToken),
);
const thumbUrl = computed(() =>
  buildThumbUrl(props.item.category, props.item.filename, props.readonlyToken, 480),
);
const previewSrc = computed(() =>
  props.item.kind === "image" ? (imageError.value ? fileUrl.value : thumbUrl.value) : fileUrl.value,
);

const KIND_META: Record<string, { icon: string; label: string }> = {
  image: { icon: "image", label: "" },
  video: { icon: "film", label: "" },
  audio: { icon: "music", label: "" },
  file: { icon: "file", label: "" },
};

const kindMeta = computed(() => {
  const base = KIND_META[props.item.kind as string] || KIND_META.file;
  const label = t(`media.kind.${props.item.kind || "file"}`);
  return { ...base, label };
});

const sizeLabel = computed(() => props.item.size_human || `${props.item.size || 0} B`);
const dateLabel = computed(() => formatDateShort(props.item.created_at));
const durationLabel = computed(() => {
  if (props.item.kind !== "audio" && props.item.kind !== "video") return "";
  return formatDuration(props.item.duration);
});

function handleImgError() {
  if (!imageError.value) imageError.value = true;
}
function handleImgLoad() {
  imageLoaded.value = true;
}
function onContext(event: MouseEvent) {
  emit("context-media", { event, item: props.item });
}
function onNameClick() {
  if (ui.gridMode === "list") emit("preview", props.item);
}
</script>

<style scoped>
.meta-name-clickable {
  cursor: pointer;
}
.meta-name-clickable:hover {
  color: var(--primary);
}
</style>

<template>
  <transition name="drawer">
    <div v-if="visible" class="drawer-mask" @click.self="$emit('close')">
      <aside class="drawer">
        <header>
          <h3>
            <Icon name="info" :size="16" style="vertical-align: -3px" />
            {{ $t("drawer.title") }}
          </h3>
          <button class="icon" :title="$t('drawer.close')" @click="$emit('close')">
            <Icon name="x" :size="16" />
          </button>
        </header>
        <div v-if="!media" class="empty">
          <div class="illus"><Icon name="file-question" :size="30" /></div>
          <strong>{{ $t("drawer.emptyTitle") }}</strong>
          <span>{{ $t("drawer.emptyHint") }}</span>
        </div>
        <template v-else>
          <div class="drawer-content">
            <div class="drawer-preview-wrap">
              <div class="drawer-preview" @click="$emit('preview', media)">
                <img
                  v-if="media.kind === 'image'"
                  :src="previewSrc"
                  :alt="media.filename"
                  @error="handlePreviewError"
                />
                <video v-else-if="media.kind === 'video'" :src="previewSrc" muted preload="metadata"></video>
                <div v-else class="audio-placeholder">
                  <div class="disc">
                    <Icon :name="media.kind === 'audio' ? 'music' : 'file'" :size="24" />
                  </div>
                  <small>{{ media.kind }}</small>
                </div>
              </div>
            </div>

            <section class="meta-block">
              <h4 class="meta-title">{{ $t("drawer.metadataTitle") }}</h4>
              <dl class="meta-grid">
                <div class="meta-item">
                  <dt>{{ $t("drawer.id") }}</dt>
                  <dd class="meta-mono">{{ media.id }}</dd>
                </div>
                <div class="meta-item">
                  <dt>{{ $t("drawer.kind") }}</dt>
                  <dd>
                    <span class="meta-kind">
                      <Icon :name="kindIcon" :size="14" />
                      <span>{{ kindLabel }}</span>
                    </span>
                  </dd>
                </div>
                <div class="meta-item">
                  <dt>{{ $t("drawer.size") }}</dt>
                  <dd>{{ sizeLabel }}</dd>
                </div>
                <div v-if="mimeLabel" class="meta-item">
                  <dt>{{ $t("drawer.mime") }}</dt>
                  <dd class="meta-mono ellipsis" :title="mimeLabel">{{ mimeLabel }}</dd>
                </div>
                <div v-if="durationLabel" class="meta-item">
                  <dt>{{ $t("drawer.duration") }}</dt>
                  <dd class="meta-mono">{{ durationLabel }}</dd>
                </div>
                <div v-if="categoryLabel" class="meta-item">
                  <dt>{{ $t("drawer.category") }}</dt>
                  <dd class="ellipsis" :title="categoryLabel">{{ categoryLabel }}</dd>
                </div>
                <div v-if="createdAtLabel" class="meta-item">
                  <dt>{{ $t("drawer.created") }}</dt>
                  <dd>{{ createdAtLabel }}</dd>
                </div>
                <div v-if="updatedAtLabel" class="meta-item">
                  <dt>{{ $t("drawer.updated") }}</dt>
                  <dd>{{ updatedAtLabel }}</dd>
                </div>
              </dl>
            </section>

            <div class="field">
              <label>{{ $t("drawer.fieldFilename") }}</label>
              <input v-model="filename" :placeholder="originalFilename || $t('drawer.fieldFilenamePlaceholder')" />
              <small v-if="filenameDirty" class="field-hint-warn">
                <Icon name="alert-triangle" :size="12" style="vertical-align: -2px" />
                {{ $t("drawer.fieldFilenameWarn") }}
              </small>
            </div>

            <div class="field">
              <label>{{ $t("drawer.fieldCategory") }}</label>
              <select v-model="category">
                <option v-if="!hasDefaultCategory" value="default">default</option>
                <option v-for="item in categories" :key="item.category" :value="item.category">
                  {{ item.category }}
                </option>
              </select>
            </div>

            <div class="field">
              <label>{{ $t("drawer.fieldDescription") }}</label>
              <textarea v-model="description" rows="3" :placeholder="$t('drawer.fieldDescriptionPlaceholder')"></textarea>
            </div>

            <div class="field">
              <label>{{ $t("drawer.fieldTags") }}</label>
              <input v-model="tags" :placeholder="$t('drawer.fieldTagsPlaceholder')" />
            </div>
          </div>

          <div class="drawer-actions">
            <button class="primary drawer-action-primary" @click="save">
              <Icon name="save" :size="15" /> {{ $t("drawer.save") }}
            </button>
            <div class="drawer-action-row">
              <button class="drawer-action-sub" @click="$emit('copy-link', media.id)">
                <Icon name="link-2" :size="15" />
                <span>{{ $t("drawer.copy") }}</span>
              </button>
              <a
                :href="fileUrl"
                target="_blank"
                rel="noopener"
                class="btn drawer-action-sub"
                style="text-decoration: none"
              >
                <Icon name="external-link" :size="15" />
                <span>{{ $t("drawer.open") }}</span>
              </a>
              <button class="danger drawer-action-sub" @click="$emit('delete', media.id)">
                <Icon name="trash-2" :size="15" />
                <span>{{ $t("drawer.delete") }}</span>
              </button>
            </div>
          </div>
        </template>
      </aside>
    </div>
  </transition>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import Icon from "@/components/common/Icon.vue";
import { buildMediaDirectUrl, buildThumbUrl } from "@/utils/url";
import { formatDuration, formatTimestamp } from "@/utils/format";
import type { CategoryItem, MediaItem } from "@/api/types";

const { t } = useI18n();

interface Props {
  visible?: boolean;
  media?: MediaItem | null;
  categories: CategoryItem[];
  readonlyToken?: string;
}

const props = withDefaults(defineProps<Props>(), {
  visible: false,
  media: null,
  readonlyToken: "",
});

const emit = defineEmits<{
  (e: "close"): void;
  (e: "update", payload: Record<string, any>): void;
  (e: "delete", id: string | number): void;
  (e: "copy-link", id: string | number): void;
  (e: "preview", media: MediaItem): void;
}>();

const description = ref("");
const category = ref("");
const tags = ref("");
const filename = ref("");
const originalFilename = ref("");
const previewError = ref(false);

watch(
  () => props.media,
  (value) => {
    previewError.value = false;
    if (!value) {
      description.value = "";
      category.value = "";
      tags.value = "";
      filename.value = "";
      originalFilename.value = "";
      return;
    }
    description.value = value.description || "";
    category.value = value.category || "";
    tags.value = Array.isArray(value.tags) ? value.tags.join(", ") : "";
    filename.value = value.filename || "";
    originalFilename.value = value.filename || "";
  },
  { immediate: true },
);

watch(
  () => props.visible,
  (flag) => {
    if (typeof document === "undefined") return;
    document.body.classList.toggle("drawer-open", !!flag);
  },
  { immediate: true },
);

onBeforeUnmount(() => {
  if (typeof document !== "undefined") {
    document.body.classList.remove("drawer-open");
  }
});

const fileUrl = computed(() => {
  if (!props.media) return "";
  if (props.media.public_url) return props.media.public_url;
  return buildMediaDirectUrl(props.media.category, props.media.filename, props.readonlyToken);
});
const directUrl = computed(() => {
  if (!props.media) return "";
  return buildMediaDirectUrl(props.media.category, props.media.filename, props.readonlyToken);
});
const thumbSrc = computed(() => {
  if (!props.media) return "";
  return buildThumbUrl(props.media.category, props.media.filename, props.readonlyToken, 480);
});
const previewSrc = computed(() => {
  if (!props.media) return "";
  if (props.media.kind === "image") {
    return previewError.value ? directUrl.value : thumbSrc.value;
  }
  return directUrl.value;
});
const sizeLabel = computed(() => {
  if (!props.media) return "-";
  return props.media.size_human || `${props.media.size || 0} B`;
});
const hasDefaultCategory = computed(() =>
  (props.categories || []).some((item) => item && item.category === "default"),
);
const filenameDirty = computed(() => {
  const cleaned = (filename.value || "").trim();
  return !!cleaned && cleaned !== originalFilename.value;
});
const createdAtLabel = computed(() =>
  props.media ? formatTimestamp(props.media.created_at) : "",
);
const updatedAtLabel = computed(() =>
  props.media ? formatTimestamp(props.media.updated_at) : "",
);
const mimeLabel = computed(() => (props.media?.mime || "").trim());
const durationLabel = computed(() =>
  props.media ? formatDuration(props.media.duration) : "",
);
const categoryLabel = computed(() => (props.media?.category || "").trim());
const kindLabel = computed(() => {
  const k = props.media?.kind || "";
  const map: Record<string, string> = {
    image: t("media.kind.image"),
    video: t("media.kind.video"),
    audio: t("media.kind.audio"),
  };
  return map[k] || k || "-";
});
const kindIcon = computed(() => {
  const k = props.media?.kind || "";
  if (k === "image") return "image";
  if (k === "video") return "film";
  if (k === "audio") return "music";
  return "file";
});

function handlePreviewError() {
  if (!previewError.value) previewError.value = true;
}

function save() {
  if (!props.media) return;
  const payload: Record<string, any> = {
    id: props.media.id,
    description: description.value,
    category: category.value,
    tags: tags.value
      .split(",")
      .map((t) => t.trim())
      .filter(Boolean),
  };
  const cleaned = (filename.value || "").trim();
  if (cleaned && cleaned !== originalFilename.value) {
    payload.filename = cleaned;
  }
  emit("update", payload);
}
</script>

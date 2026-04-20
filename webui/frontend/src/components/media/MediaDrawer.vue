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
            <div class="drawer-preview" @click="$emit('preview', media)">
              <img v-if="media.kind === 'image'" :src="fileUrl" :alt="media.filename" />
              <video v-else-if="media.kind === 'video'" :src="fileUrl" muted preload="metadata"></video>
              <div v-else class="audio-placeholder">
                <div class="disc">
                  <Icon :name="media.kind === 'audio' ? 'music' : 'file'" :size="24" />
                </div>
                <small>{{ media.kind }}</small>
              </div>
            </div>

            <dl class="drawer-meta">
              <dt>{{ $t("drawer.id") }}</dt>
              <dd>{{ media.id }}</dd>
              <dt>{{ $t("drawer.kind") }}</dt>
              <dd><span class="badge primary">{{ media.kind }}</span></dd>
              <dt>{{ $t("drawer.size") }}</dt>
              <dd>{{ sizeLabel }}</dd>
              <dt v-if="createdAtLabel">{{ $t("drawer.created") }}</dt>
              <dd v-if="createdAtLabel">{{ createdAtLabel }}</dd>
            </dl>

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
import Icon from "@/components/common/Icon.vue";
import { buildMediaDirectUrl } from "@/utils/url";
import { formatTimestamp } from "@/utils/format";
import type { CategoryItem, MediaItem } from "@/api/types";

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

watch(
  () => props.media,
  (value) => {
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

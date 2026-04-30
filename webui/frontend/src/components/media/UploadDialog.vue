<template>
  <transition name="modal">
    <div v-if="visible" class="modal-mask" @click.self="$emit('close')">
      <div class="modal">
        <header>
          <h3>
            <Icon name="upload-cloud" :size="17" style="vertical-align: -3px" />
            {{ $t("upload.title") }}
          </h3>
          <button class="icon" :title="$t('upload.close')" @click="$emit('close')">
            <Icon name="x" :size="16" />
          </button>
        </header>

        <div class="modal-body">
          <div class="dialog-tabs">
            <button :class="{ active: mode === 'file' }" @click="mode = 'file'">
              <Icon name="upload" :size="14" /> {{ $t("upload.tabFile") }}
            </button>
            <button :class="{ active: mode === 'url' }" @click="mode = 'url'">
              <Icon name="link" :size="14" /> {{ $t("upload.tabUrl") }}
            </button>
          </div>

          <div class="field">
            <label>{{ $t("upload.category") }}</label>
            <select v-model="category">
              <option v-if="!hasDefault" value="default">default</option>
              <option v-for="item in categories" :key="item.category" :value="item.category">
                {{ item.category }}
              </option>
            </select>
          </div>

          <div class="field">
            <label>{{ $t("upload.descriptionLabel") }}</label>
            <input v-model="description" :placeholder="$t('upload.descriptionPlaceholder')" />
          </div>

          <template v-if="mode === 'file'">
            <div v-if="isPcHover" class="upload-tip" role="note">
              <Icon name="info" :size="14" />
              <span>{{ $t("upload.dropTipPc") }}</span>
            </div>
            <div
              class="dropzone"
              :class="{ dragover }"
              @dragover.prevent="dragover = true"
              @dragleave.prevent="dragover = false"
              @drop.prevent="onDrop"
              @click="openFileDialog"
            >
              <Icon name="upload-cloud" :size="30" />
              <strong>{{ $t("upload.dropHint") }}</strong>
              <span class="muted">{{ dropzoneHint }}</span>
              <input
                ref="fileInput"
                type="file"
                multiple
                style="display: none"
                @change="onFiles"
              />
              <div v-if="files.length" class="file-list">
                <div
                  v-for="(f, idx) in files"
                  :key="idx"
                  class="file"
                  :class="{ 'file-oversized': isOversized(f) }"
                >
                  <span style="overflow: hidden; text-overflow: ellipsis; white-space: nowrap">
                    {{ f.name }}
                  </span>
                  <span class="muted mono">{{ formatBytes(f.size) }}</span>
                  <span
                    v-if="isOversized(f)"
                    class="file-badge"
                    :title="$t('upload.oversizedTitle')"
                  >
                    <Icon name="triangle-alert" :size="12" /> {{ $t("upload.oversizedBadge") }}
                  </span>
                </div>
              </div>
            </div>
            <small v-if="files.length" class="muted">
              {{ $t("upload.summary", { count: files.length, size: totalSize }) }}
              <template v-if="oversizedFiles.length">
                ·
                <span class="text-warning">
                  {{ $t("upload.oversizedHint", { count: oversizedFiles.length, mb: maxFileSizeMb }) }}
                </span>
              </template>
            </small>
          </template>

          <template v-else>
            <div class="field">
              <label>{{ $t("upload.urlLabel") }}</label>
              <div class="input-wrap">
                <span class="icon-slot"><Icon name="globe" :size="15" /></span>
                <input v-model="url" placeholder="https://..." />
              </div>
            </div>
            <div class="field">
              <label>{{ $t("upload.filenameLabel") }}</label>
              <input v-model="filename" :placeholder="$t('upload.filenamePlaceholder')" />
            </div>
          </template>
        </div>

        <div class="modal-footer">
          <button @click="$emit('close')">{{ $t("common.cancel") }}</button>
          <button
            class="primary"
            :disabled="mode === 'file' ? !acceptedFiles.length : !url.trim()"
            @click="submit"
          >
            <Icon name="check" :size="15" />
            {{ $t("upload.submit") }}
          </button>
        </div>
      </div>
    </div>
  </transition>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import Icon from "@/components/common/Icon.vue";
import { formatSize } from "@/utils/format";
import type { CategoryItem } from "@/api/types";

interface Props {
  visible?: boolean;
  categories?: CategoryItem[];
  activeCategory?: string;
  initialMode?: "file" | "url";
  maxFileSizeMb?: number;
}

const props = withDefaults(defineProps<Props>(), {
  visible: false,
  categories: () => [],
  activeCategory: "",
  initialMode: "file",
  maxFileSizeMb: 500,
});

const emit = defineEmits<{
  (e: "close"): void;
  (e: "upload-files", payload: { category: string; description: string; files: File[] }): void;
  (e: "save-url", payload: { category: string; description: string; url: string; filename: string }): void;
}>();

const { t } = useI18n();

const mode = ref<"file" | "url">(props.initialMode);
const category = ref(props.activeCategory || "default");
const description = ref("");
const files = ref<File[]>([]);
const url = ref("");
const filename = ref("");
const dragover = ref(false);
const fileInput = ref<HTMLInputElement | null>(null);

const PC_HOVER_QUERY = "(hover: hover) and (pointer: fine)";
const isPcHover = ref(
  typeof window !== "undefined" && typeof window.matchMedia === "function"
    ? window.matchMedia(PC_HOVER_QUERY).matches
    : true,
);
let pcHoverMql: MediaQueryList | null = null;
const onPcHoverChange = (event: MediaQueryListEvent) => {
  isPcHover.value = event.matches;
};

onMounted(() => {
  if (typeof window === "undefined" || typeof window.matchMedia !== "function") return;
  pcHoverMql = window.matchMedia(PC_HOVER_QUERY);
  isPcHover.value = pcHoverMql.matches;
  if (typeof pcHoverMql.addEventListener === "function") {
    pcHoverMql.addEventListener("change", onPcHoverChange);
  } else if (typeof (pcHoverMql as any).addListener === "function") {
    (pcHoverMql as any).addListener(onPcHoverChange);
  }
});

onBeforeUnmount(() => {
  if (!pcHoverMql) return;
  if (typeof pcHoverMql.removeEventListener === "function") {
    pcHoverMql.removeEventListener("change", onPcHoverChange);
  } else if (typeof (pcHoverMql as any).removeListener === "function") {
    (pcHoverMql as any).removeListener(onPcHoverChange);
  }
  pcHoverMql = null;
});

watch(
  () => props.visible,
  (value) => {
    if (value) {
      category.value = props.activeCategory || "default";
      mode.value = props.initialMode || "file";
      files.value = [];
      url.value = "";
      filename.value = "";
      description.value = "";
    }
  },
);

const hasDefault = computed(() =>
  (props.categories || []).some((item) => item && item.category === "default"),
);

const maxBytes = computed(() => {
  const mb = Number(props.maxFileSizeMb) || 0;
  return mb > 0 ? mb * 1024 * 1024 : 0;
});

const oversizedFiles = computed(() => {
  if (!maxBytes.value) return [] as File[];
  return files.value.filter((f) => Number(f.size) > maxBytes.value);
});

const acceptedFiles = computed(() => {
  if (!maxBytes.value) return files.value;
  return files.value.filter((f) => Number(f.size) <= maxBytes.value);
});

const totalSize = computed(() => {
  const bytes = files.value.reduce((sum, f) => sum + (f.size || 0), 0);
  return bytes ? formatSize(bytes) : "";
});

const dropzoneHint = computed(() => {
  const mb = Number(props.maxFileSizeMb) || 0;
  if (mb > 0) return t("upload.dropzoneHintWithLimit", { mb });
  return t("upload.dropzoneHint");
});

function onFiles(event: Event) {
  const input = event.target as HTMLInputElement;
  files.value = Array.from(input.files || []);
}

function onDrop(event: DragEvent) {
  dragover.value = false;
  const dropped = Array.from(event.dataTransfer?.files || []);
  if (dropped.length) {
    files.value = dropped;
    mode.value = "file";
  }
}

function openFileDialog() {
  fileInput.value?.click();
}

function isOversized(file: File) {
  return maxBytes.value > 0 && Number(file?.size) > maxBytes.value;
}

function formatBytes(bytes: number) {
  return formatSize(bytes);
}

function submit() {
  if (mode.value === "file") {
    if (!acceptedFiles.value.length) return;
    emit("upload-files", {
      category: category.value || "default",
      description: description.value,
      files: acceptedFiles.value,
    });
  } else {
    if (!url.value.trim()) return;
    emit("save-url", {
      category: category.value || "default",
      description: description.value,
      url: url.value.trim(),
      filename: filename.value.trim(),
    });
  }
  emit("close");
}
</script>

<style scoped>
.upload-tip {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 8px 12px;
  border-radius: var(--radius-sm);
  background: var(--info-soft);
  color: var(--info);
  border: 1px solid color-mix(in srgb, var(--info) 28%, transparent);
  font-size: 12.5px;
  line-height: 1.55;
}

.upload-tip :deep(.icon) {
  margin-top: 2px;
  flex: none;
}
</style>

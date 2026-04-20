<template>
  <transition name="modal">
    <div v-if="visible" class="modal-mask data-preview-mask" @click.self="$emit('close')">
      <div class="modal data-preview-modal">
        <header>
          <h3>
            <Icon
              :name="preview?.isText ? 'file-text' : 'file-question'"
              :size="17"
              style="vertical-align: -3px"
            />
            <span class="data-preview-title" :title="preview?.name">{{ preview?.name }}</span>
          </h3>
          <button class="icon" :title="$t('dataFile.close')" @click="$emit('close')">
            <Icon name="x" :size="16" />
          </button>
        </header>

        <div v-if="preview" class="data-preview-meta">
          <span class="badge" :class="preview.isText ? 'info' : 'warning'">
            <Icon :name="preview.isText ? 'align-left' : 'help-circle'" :size="12" />
            {{ preview.isText ? $t("dataFile.textPreview") : $t("dataFile.unsupported") }}
          </span>
          <span class="mono muted">{{ sizeLabel }}</span>
          <span v-if="preview.mime" class="muted">{{ preview.mime }}</span>
          <span v-if="preview.encoding" class="muted">
            {{ $t("dataFile.encoding") }}: {{ preview.encoding }}
          </span>
          <span v-if="preview.truncated" class="badge warning">
            <Icon name="scissors" :size="11" />
            {{ $t("dataFile.truncated") }}
          </span>
        </div>

        <div class="modal-body data-preview-body">
          <div v-if="preview?.loading" class="empty" style="padding: 30px 12px">
            <Icon name="loader" :size="28" />
            <strong>{{ $t("dataFile.loading") }}</strong>
          </div>
          <template v-else-if="preview?.isText">
            <div class="data-preview-toolbar">
              <small class="muted">
                <Icon name="list" :size="12" style="vertical-align: -2px" />
                {{ $t("dataFile.lines", { count: contentLines }) }}
              </small>
              <div class="data-preview-actions">
                <button class="sm" @click="$emit('copy')">
                  <Icon name="clipboard-copy" :size="13" />
                  {{ $t("dataFile.copy") }}
                </button>
                <button class="sm" @click="handleDownload">
                  <Icon name="download" :size="13" />
                  {{ $t("dataFile.download") }}
                </button>
              </div>
            </div>
            <pre class="data-preview-pre" :data-lang="language"><code>{{ displayContent }}</code></pre>
            <small v-if="preview.truncated" class="muted">{{ $t("dataFile.truncatedHint") }}</small>
          </template>
          <div v-else-if="preview" class="data-preview-unsupported">
            <div class="illus"><Icon name="file-warning" :size="38" /></div>
            <strong>{{ $t("dataFile.unsupportedTitle") }}</strong>
            <span class="muted">{{ $t("dataFile.unsupportedHint") }}</span>
            <div class="data-preview-actions" style="justify-content: center; margin-top: 4px">
              <button class="primary" @click="handleDownload">
                <Icon name="download" :size="14" />
                {{ $t("dataFile.downloadNow") }}
              </button>
            </div>
          </div>
        </div>

        <div class="modal-footer">
          <button @click="$emit('close')">{{ $t("common.close") }}</button>
        </div>
      </div>
    </div>
  </transition>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, watch } from "vue";
import Icon from "@/components/common/Icon.vue";
import { formatSize } from "@/utils/format";

interface PreviewData {
  loading?: boolean;
  name?: string;
  path?: string;
  size?: number;
  mime?: string;
  kind?: string;
  suffix?: string;
  isText?: boolean;
  content?: string;
  truncated?: boolean;
  encoding?: string;
}

interface Props {
  preview?: PreviewData | null;
}

const props = withDefaults(defineProps<Props>(), {
  preview: null,
});

const emit = defineEmits<{
  (e: "close"): void;
  (e: "copy"): void;
  (e: "download", payload: { path: string; name: string }): void;
}>();

const LANG_MAP: Record<string, string> = {
  ".json": "json",
  ".json5": "json",
  ".jsonl": "json",
  ".ndjson": "json",
  ".md": "markdown",
  ".markdown": "markdown",
  ".yaml": "yaml",
  ".yml": "yaml",
  ".toml": "toml",
  ".ini": "ini",
  ".py": "python",
  ".js": "javascript",
  ".ts": "typescript",
  ".tsx": "tsx",
  ".jsx": "jsx",
  ".vue": "vue",
  ".css": "css",
  ".html": "html",
  ".htm": "html",
  ".xml": "xml",
  ".sh": "shell",
  ".sql": "sql",
  ".go": "go",
  ".rs": "rust",
  ".java": "java",
  ".c": "c",
  ".cpp": "cpp",
  ".h": "c",
};

const visible = computed(() => !!props.preview);

const sizeLabel = computed(() => formatSize(props.preview?.size || 0));

const language = computed(() => {
  const suffix = (props.preview?.suffix || "").toLowerCase();
  return LANG_MAP[suffix] || "";
});

const contentLines = computed(() => {
  const content = props.preview?.content || "";
  if (!content) return 0;
  return content.split("\n").length;
});

const displayContent = computed(() => props.preview?.content || "");

function onKey(event: KeyboardEvent) {
  if (!visible.value) return;
  if (event.key === "Escape") emit("close");
}

watch(visible, (value) => {
  if (value) window.addEventListener("keydown", onKey);
  else window.removeEventListener("keydown", onKey);
});

onBeforeUnmount(() => {
  window.removeEventListener("keydown", onKey);
});

function handleDownload() {
  if (!props.preview) return;
  emit("download", {
    path: props.preview.path || "",
    name: props.preview.name || "",
  });
}
</script>

<template>
  <section class="panel" style="display: flex; flex-direction: column; gap: 12px">
    <div class="toolbar">
      <div class="toolbar-actions">
        <button :disabled="!path" :title="$t('dataBrowser.parentTitle')" @click="$emit('go-parent')">
          <Icon name="corner-up-left" :size="15" /> {{ $t("dataBrowser.parent") }}
        </button>
      </div>
      <div class="data-breadcrumb">
        <Icon name="home" :size="12" />
        <template v-for="(seg, idx) in breadcrumb" :key="idx">
          <span v-if="idx > 0">/</span>
          <span
            class="part"
            style="cursor: pointer"
            @click="$emit('navigate', seg.path)"
            >{{ seg.label }}</span
          >
        </template>
      </div>
    </div>

    <div v-if="loading" class="skeleton-grid">
      <div v-for="n in 6" :key="n" class="skeleton-card">
        <div class="sk-line"></div>
        <div class="sk-line short"></div>
      </div>
    </div>
    <div v-else-if="!sortedItems.length" class="empty">
      <div class="illus"><Icon name="folder-open" :size="34" /></div>
      <strong>{{ $t("dataBrowser.emptyTitle") }}</strong>
      <span>{{ $t("dataBrowser.emptyHint") }}</span>
    </div>

    <div v-else class="data-grid">
      <div
        v-for="item in sortedItems"
        :key="item.path"
        class="data-item"
        :class="kindClass(item)"
        @click="handleClick(item)"
      >
        <div class="icon-wrap">
          <Icon :name="iconFor(item)" :size="16" />
        </div>
        <div class="meta">
          <strong :title="item.name">{{ item.name }}</strong>
          <small>{{ sizeLabel(item) }}</small>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed } from "vue";
import { useI18n } from "vue-i18n";
import Icon from "@/components/common/Icon.vue";
import { formatSize } from "@/utils/format";
import type { DataTreeItem as DataBrowserItem } from "@/api/types";

interface Props {
  path?: string;
  parent?: string;
  items?: DataBrowserItem[];
  loading?: boolean;
}

const props = withDefaults(defineProps<Props>(), {
  path: "",
  parent: "",
  items: () => [],
  loading: false,
});

const emit = defineEmits<{
  (e: "open-dir", path: string): void;
  (e: "open-file", item: DataBrowserItem): void;
  (e: "go-parent"): void;
  (e: "navigate", path: string): void;
}>();

const { t } = useI18n();

const breadcrumb = computed(() => {
  const parts = (props.path || "").split("/").filter(Boolean);
  const result = [{ label: "data", path: "" }];
  let current = "";
  parts.forEach((seg) => {
    current = current ? `${current}/${seg}` : seg;
    result.push({ label: seg, path: current });
  });
  return result;
});

const sortedItems = computed(() =>
  [...props.items].sort((a, b) => {
    if (a.is_dir !== b.is_dir) return a.is_dir ? -1 : 1;
    return a.name.localeCompare(b.name);
  }),
);

function iconFor(item: DataBrowserItem) {
  if (item.is_dir) return "folder";
  if (item.kind === "image") return "image";
  if (item.kind === "video") return "film";
  if (item.kind === "audio") return "music";
  return "file";
}

function kindClass(item: DataBrowserItem) {
  if (item.is_dir) return "dir";
  return item.kind || "";
}

function sizeLabel(item: DataBrowserItem) {
  if (item.is_dir) return t("dataBrowser.dirLabel");
  return formatSize(item.size || 0);
}

function handleClick(item: DataBrowserItem) {
  if (item.is_dir) emit("open-dir", item.path);
  else emit("open-file", item);
}
</script>

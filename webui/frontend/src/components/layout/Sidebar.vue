<template>
  <aside class="sidebar">
    <div class="sidebar-tabs" role="tablist">
      <button
        class="sidebar-tab"
        :class="{ active: viewMode === 'media' }"
        @click="$emit('switch-mode', 'media')"
      >
        <Icon name="library" :size="15" />
        {{ $t("nav.media") }}
      </button>
      <button
        class="sidebar-tab"
        :class="{ active: viewMode === 'data' }"
        :disabled="!canDataBrowse"
        :title="canDataBrowse ? $t('sidebar.dataDesc') : $t('dataBrowser.notEnabledHint')"
        @click="$emit('switch-mode', 'data')"
      >
        <Icon name="folder-tree" :size="15" />
        {{ $t("nav.data") }}
      </button>
    </div>

    <div v-if="viewMode === 'media'" class="sidebar-section">
      <div class="sidebar-header">
        <h3>{{ $t("sidebar.categoryTotal", { count: categories.length }) }}</h3>
        <div class="sidebar-tools">
          <button class="icon sm" :title="$t('sidebar.addCategoryTitle')" @click="$emit('request-create-category')">
            <Icon name="folder-plus" :size="14" />
          </button>
        </div>
      </div>
      <ul class="category-list">
        <li
          class="category-item"
          :class="{ active: activeCategory === '' }"
          @click="$emit('select-category', '')"
          @contextmenu.prevent="onContext($event, { category: '', isAll: true, count: totalCount })"
        >
          <span class="icon-wrap"><Icon name="layers" :size="14" /></span>
          <span class="label">{{ $t("sidebar.allMedia") }}</span>
          <span class="count">{{ totalCount }}</span>
        </li>
        <li
          v-for="item in categories"
          :key="item.category"
          class="category-item"
          :class="{ active: activeCategory === item.category }"
          :title="item.description || item.category"
          @click="$emit('select-category', item.category)"
          @contextmenu.prevent="onContext($event, item)"
        >
          <span class="icon-wrap"><Icon :name="categoryIcon(item.category)" :size="14" /></span>
          <span class="label">{{ item.category }}</span>
          <span class="count">{{ item.count }}</span>
        </li>
      </ul>
    </div>

    <div v-else class="sidebar-section">
      <div class="sidebar-header">
        <h3>{{ $t("sidebar.dataTitle") }}</h3>
      </div>
      <p class="muted" style="padding: 0 4px">
        {{ $t("sidebar.dataDesc") }}
      </p>
    </div>
  </aside>
</template>

<script setup lang="ts">
import Icon from "@/components/common/Icon.vue";
import type { CategoryItem } from "@/api/types";

interface Props {
  categories: CategoryItem[];
  activeCategory?: string;
  viewMode?: string;
  totalCount?: number;
  canDataBrowse?: boolean;
}

withDefaults(defineProps<Props>(), {
  activeCategory: "",
  viewMode: "media",
  totalCount: 0,
  canDataBrowse: true,
});

const emit = defineEmits<{
  (e: "switch-mode", mode: string): void;
  (e: "select-category", category: string): void;
  (e: "request-create-category"): void;
  (e: "context-category", payload: { event: MouseEvent; item: any }): void;
  (e: "close"): void;
}>();

function categoryIcon(name: string): string {
  const lower = String(name || "").toLowerCase();
  if (lower.includes("image") || lower.includes("图")) return "image";
  if (lower.includes("video") || lower.includes("视频") || lower.includes("短视频")) return "film";
  if (lower.includes("audio") || lower.includes("音乐") || lower.includes("音频")) return "music";
  if (lower.includes("doc") || lower.includes("文档")) return "file-text";
  if (lower.includes("meme") || lower.includes("表情")) return "sticker";
  return "folder";
}

function onContext(event: MouseEvent, item: any) {
  emit("context-category", { event, item });
}
</script>

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
          <button
            class="icon sm"
            :class="{ 'tool-active': activeRoute === 'trash' }"
            :title="$t('settings.openTrash')"
            @click="$emit('open-trash')"
          >
            <Icon name="trash-2" :size="14" />
          </button>
          <button class="icon sm" :title="$t('sidebar.addCategoryTitle')" @click="$emit('request-create-category')">
            <Icon name="folder-plus" :size="14" />
          </button>
        </div>
      </div>
      <ul class="category-list">
        <li
          class="category-item"
          :class="{ active: activeRoute === 'media' && activeCategory === '' }"
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
          :class="{ active: activeRoute === 'media' && activeCategory === item.category }"
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
  activeRoute?: string;
  viewMode?: string;
  totalCount?: number;
  canDataBrowse?: boolean;
}

withDefaults(defineProps<Props>(), {
  activeCategory: "",
  activeRoute: "",
  viewMode: "media",
  totalCount: 0,
  canDataBrowse: true,
});

const emit = defineEmits<{
  (e: "switch-mode", mode: string): void;
  (e: "select-category", category: string): void;
  (e: "open-trash"): void;
  (e: "request-create-category"): void;
  (e: "context-category", payload: { event: MouseEvent; item: any }): void;
  (e: "close"): void;
}>();

function categoryIcon(name: string): string {
  const lower = String(name || "").toLowerCase();
  const imageWords = ["image", "img", "图片", "图像", "图", "画像", "写真"];
  const videoWords = [
    "video",
    "视频",
    "短视频",
    "影片",
    "映像",
    "動画",
    "ビデオ",
  ];
  const audioWords = [
    "audio",
    "music",
    "音乐",
    "音频",
    "音声",
    "オーディオ",
  ];
  const docWords = ["doc", "document", "text", "文档", "資料", "ドキュメント"];
  const memeWords = ["meme", "sticker", "emoji", "表情", "贴纸", "スタンプ"];
  if (containsAny(lower, imageWords)) return "image";
  if (containsAny(lower, videoWords)) return "film";
  if (containsAny(lower, audioWords)) return "music";
  if (containsAny(lower, docWords)) return "file-text";
  if (containsAny(lower, memeWords)) return "sticker";
  return "folder";
}

function containsAny(text: string, words: string[]): boolean {
  return words.some((word) => {
    const key = String(word || "").toLowerCase().trim();
    return !!key && text.includes(key);
  });
}

function onContext(event: MouseEvent, item: any) {
  emit("context-category", { event, item });
}
</script>

<style scoped>
.sidebar-tools .tool-active {
  color: var(--primary);
  border-color: color-mix(in srgb, var(--primary) 35%, var(--line));
  background: color-mix(in srgb, var(--primary) 14%, var(--surface));
}
</style>

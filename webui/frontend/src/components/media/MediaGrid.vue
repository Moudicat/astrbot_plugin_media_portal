<template>
  <section style="display: flex; flex-direction: column; gap: 14px">
    <div v-if="visibleStatCards.length" class="panel stat-grid">
      <div
        v-for="card in visibleStatCards"
        :key="card.key"
        class="stat-card"
        :data-tone="card.tone"
      >
        <div class="avatar"><Icon :name="card.icon" :size="18" /></div>
        <div class="meta">
          <small>{{ card.label }}</small>
          <strong>{{ card.value }}</strong>
        </div>
      </div>
    </div>

    <div class="panel" style="display: flex; flex-direction: column; gap: 10px">
      <div class="toolbar">
        <div class="toolbar-search">
          <div class="input-wrap">
            <span class="icon-slot"><Icon name="search" :size="16" /></span>
            <input
              ref="searchInput"
              v-model="localQuery"
              type="search"
              inputmode="search"
              enterkeyhint="search"
              autocomplete="off"
              :placeholder="$t('media.searchPlaceholder')"
              @keyup.enter="submitSearch"
            />
            <button
              v-if="localQuery"
              class="icon sm input-clear"
              type="button"
              :title="$t('media.clearSearch')"
              :aria-label="$t('media.clearSearch')"
              @click="clearSearch"
            >
              <Icon name="x" :size="14" />
            </button>
          </div>
          <button
            class="primary search-submit"
            type="button"
            :title="$t('media.searchBtn')"
            :aria-label="$t('media.searchBtn')"
            @click="submitSearch"
          >
            <Icon name="search" :size="15" />
            <span class="hide-mobile">{{ $t("media.searchBtn") }}</span>
          </button>
        </div>
        <div class="toolbar-actions">
          <button
            class="icon view-mode-btn mobile-inline"
            type="button"
            :title="viewModeToggleLabel"
            :aria-label="viewModeToggleLabel"
            @click="ui.toggleGridMode()"
          >
            <Icon :name="ui.gridMode === 'card' ? 'list' : 'layout-grid'" :size="15" />
          </button>
          <button class="accent" :title="$t('media.uploadTitle')" @click="$emit('open-upload')">
            <Icon name="upload" :size="15" />
            <span class="hide-mobile">{{ $t("media.uploadBtn") }}</span>
          </button>
        </div>
      </div>

      <div class="kind-tabs">
        <button
          v-for="tab in kindTabs"
          :key="tab.id"
          class="chip"
          :class="{ active: kind === tab.id }"
          @click="pickKind(tab.id)"
        >
          <Icon :name="tab.icon" :size="13" />
          {{ tab.label }}
        </button>
        <button
          class="chip view-mode-btn pc-only"
          type="button"
          style="margin-left: auto"
          :title="viewModeToggleLabel"
          :aria-label="viewModeToggleLabel"
          @click="ui.toggleGridMode()"
        >
          <Icon :name="ui.gridMode === 'card' ? 'list' : 'layout-grid'" :size="14" />
        </button>
      </div>

      <div v-if="categories.length" class="category-tabs mobile-only">
        <button
          class="chip"
          :class="{ active: activeCategory === '' }"
          @click="$emit('select-category', '')"
        >
          <Icon name="layers" :size="13" />
          {{ $t("media.allCategories") }}
        </button>
        <button
          v-for="cat in categories"
          :key="cat.category"
          class="chip"
          :class="{ active: activeCategory === cat.category }"
          :title="cat.description || cat.category"
          @click="$emit('select-category', cat.category)"
        >
          <Icon name="folder" :size="13" />
          {{ cat.category }}
          <span class="chip-count">{{ cat.count }}</span>
        </button>
      </div>

      <div
        v-if="selectedIds.length"
        ref="inlineSelectionBar"
        class="selection-bar"
        :class="{ 'is-hidden-when-pinned': pinned }"
        aria-hidden="false"
      >
        <span>
          <Icon name="check-check" :size="14" style="vertical-align: -2px" />
          {{ $t("media.selectedCount", { count: selectedIds.length }) }}
        </span>
        <div class="actions">
          <button class="sm" @click="$emit('clear-selection')">
            <Icon name="x" :size="14" /> {{ $t("media.cancelSelection") }}
          </button>
          <button class="sm" :title="$t('media.batchCategoryTitle')" @click="$emit('batch-change-category')">
            <Icon name="folder-input" :size="14" /> {{ $t("media.batchCategory") }}
          </button>
          <button class="danger sm" @click="$emit('batch-delete')">
            <Icon name="trash-2" :size="14" /> {{ $t("media.batchDelete") }}
          </button>
        </div>
      </div>
    </div>

    <teleport v-if="teleportReady" to="#topbar-pinned-slot">
      <transition name="pinned-slide">
        <div
          v-if="pinned && selectedIds.length"
          class="selection-bar--pinned"
          role="toolbar"
          :aria-label="$t('media.selectedCount', { count: selectedIds.length })"
        >
          <div class="actions">
            <button class="sm pinned-optional" type="button" :title="$t('media.cancelSelection')" @click="$emit('clear-selection')">
              <Icon name="x" :size="14" />
              <span class="hide-mobile">{{ $t("common.cancel") }}</span>
            </button>
            <button class="sm pinned-secondary" type="button" :title="$t('media.batchCategoryTitle')" @click="$emit('batch-change-category')">
              <Icon name="folder-input" :size="14" />
              <span class="hide-mobile">{{ $t("media.batchCategory") }}</span>
            </button>
            <button class="danger sm" type="button" :title="$t('media.batchDelete')" @click="$emit('batch-delete')">
              <Icon name="trash-2" :size="14" />
              <span class="hide-mobile">{{ $t("media.batchDelete") }}</span>
            </button>
          </div>
        </div>
      </transition>
    </teleport>

    <div v-if="loading" class="skeleton-grid">
      <div v-for="n in 8" :key="n" class="skeleton-card">
        <div class="sk-media"></div>
        <div class="sk-line"></div>
        <div class="sk-line short"></div>
      </div>
    </div>

    <div v-else-if="!items.length && hasActiveFilter" class="empty panel">
      <div class="illus"><Icon name="search-x" :size="36" /></div>
      <strong>{{ $t("media.emptyNoResultsTitle") }}</strong>
      <span>{{ $t("media.emptyNoResultsHint") }}</span>
      <div style="display: flex; gap: 8px; margin-top: 6px">
        <button class="sm" type="button" @click="resetFilters">
          <Icon name="eraser" :size="15" /> {{ $t("media.emptyNoResultsReset") }}
        </button>
      </div>
    </div>

    <div v-else-if="!items.length" class="empty panel">
      <div class="illus"><Icon name="package-open" :size="36" /></div>
      <strong>{{ $t("media.emptyTitle") }}</strong>
      <span>{{ $t("media.emptyHint") }}</span>
      <div style="display: flex; gap: 8px; margin-top: 6px">
        <button class="primary" @click="$emit('open-upload')">
          <Icon name="upload" :size="15" /> {{ $t("media.emptyAction") }}
        </button>
      </div>
    </div>

    <div v-else class="media-grid">
      <MediaCard
        v-for="item in items"
        :key="item.id"
        :item="item"
        :selected="selectedIds.includes(item.id)"
        :readonly-token="readonlyToken"
        @toggle-select="$emit('toggle-select', $event)"
        @preview="$emit('preview', $event)"
        @detail="$emit('detail', $event)"
        @copy-link="$emit('copy-link', $event)"
        @context-media="$emit('context-media', $event)"
      />
    </div>

    <footer v-if="totalPages > 0" class="pager">
      <button class="icon sm" :disabled="page <= 1" @click="$emit('page-change', page - 1)">
        <Icon name="chevron-left" :size="15" />
      </button>
      <span>{{ $t("media.pagerText", { page, total: totalPages, count: totalCount }) }}</span>
      <button class="icon sm" :disabled="page >= totalPages" @click="$emit('page-change', page + 1)">
        <Icon name="chevron-right" :size="15" />
      </button>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import Icon from "@/components/common/Icon.vue";
import MediaCard from "./MediaCard.vue";
import type { CategoryItem, MediaItem, MediaStats } from "@/api/types";
import { useUiStore, type StatVisibility } from "@/stores/ui";

const ui = useUiStore();

interface Props {
  items: MediaItem[];
  loading?: boolean;
  selectedIds: Array<string | number>;
  query?: string;
  kind?: string;
  page?: number;
  totalPages?: number;
  totalCount?: number;
  readonlyToken?: string;
  stats?: MediaStats;
  activeCategory?: string;
  categories?: CategoryItem[];
  statVisibility: StatVisibility;
}

const props = withDefaults(defineProps<Props>(), {
  loading: false,
  query: "",
  kind: "",
  page: 1,
  totalPages: 0,
  totalCount: 0,
  readonlyToken: "",
  stats: () => ({}),
  activeCategory: "",
  categories: () => [],
});

const emit = defineEmits<{
  (e: "search", query: string): void;
  (e: "change-kind", kind: string): void;
  (e: "toggle-select", id: string | number): void;
  (e: "preview", item: MediaItem): void;
  (e: "detail", item: MediaItem): void;
  (e: "open-upload"): void;
  (e: "page-change", page: number): void;
  (e: "clear-selection"): void;
  (e: "batch-delete"): void;
  (e: "batch-change-category"): void;
  (e: "copy-link", id: string | number): void;
  (e: "select-category", category: string): void;
  (e: "context-media", payload: { event: MouseEvent; item: MediaItem }): void;
}>();

const { t } = useI18n();

const SEARCH_DEBOUNCE_MS = 350;

const localQuery = ref(props.query);
const pinned = ref(false);
const teleportReady = ref(false);
const searchInput = ref<HTMLInputElement | null>(null);
const inlineSelectionBar = ref<HTMLDivElement | null>(null);

let searchTimer: ReturnType<typeof setTimeout> | null = null;
let lastEmittedQuery = props.query ?? "";

function clearSearchTimer() {
  if (searchTimer !== null) {
    clearTimeout(searchTimer);
    searchTimer = null;
  }
}

function emitSearchIfChanged(value: string) {
  const next = value ?? "";
  if (next === lastEmittedQuery) return;
  lastEmittedQuery = next;
  emit("search", next);
}

watch(
  () => props.query,
  (value) => {
    const next = value ?? "";
    localQuery.value = next;
    lastEmittedQuery = next;
    clearSearchTimer();
  },
);

watch(localQuery, (value) => {
  const next = value ?? "";
  if (next === lastEmittedQuery) {
    clearSearchTimer();
    return;
  }
  clearSearchTimer();
  searchTimer = setTimeout(() => {
    searchTimer = null;
    emitSearchIfChanged(next);
  }, SEARCH_DEBOUNCE_MS);
});

watch(
  () => props.selectedIds,
  (value) => {
    if (Array.isArray(value) && value.length > 0) {
      nextTick(updatePinned);
    } else {
      pinned.value = false;
    }
  },
  { immediate: true },
);

onMounted(() => {
  teleportReady.value = !!document.getElementById("topbar-pinned-slot");
  if (!teleportReady.value) {
    nextTick(() => {
      teleportReady.value = !!document.getElementById("topbar-pinned-slot");
    });
  }
  window.addEventListener("scroll", updatePinned, { passive: true });
  window.addEventListener("resize", updatePinned);
  nextTick(updatePinned);
});
onBeforeUnmount(() => {
  window.removeEventListener("scroll", updatePinned);
  window.removeEventListener("resize", updatePinned);
  clearSearchTimer();
});

function updatePinned() {
  if (!props.selectedIds || !props.selectedIds.length) {
    if (pinned.value) pinned.value = false;
    return;
  }
  const el = inlineSelectionBar.value;
  if (!el) {
    if (pinned.value) pinned.value = false;
    return;
  }
  const topbar = document.querySelector(".topbar");
  const refBottom = topbar ? Math.ceil(topbar.getBoundingClientRect().bottom) : 72;
  const rect = el.getBoundingClientRect();
  const next = rect.bottom < refBottom + 4;
  if (next !== pinned.value) pinned.value = next;
}

const statCards = computed(() => {
  const stats = props.stats || {};
  const categories = stats.categories || [];
  const totalSize = stats.total_size_human || stats.total_size || "-";
  const kindCount = (target: string) => (stats.by_kind && stats.by_kind[target]) || 0;
  return [
    {
      key: "total",
      label: t("media.stats.totalLabel"),
      value: stats.total_count ?? props.totalCount ?? 0,
      icon: "library",
      tone: "primary",
    },
    {
      key: "image",
      label: t("media.stats.imageLabel"),
      value: kindCount("image"),
      icon: "image",
      tone: "violet",
    },
    {
      key: "video",
      label: t("media.stats.videoLabel"),
      value: kindCount("video"),
      icon: "film",
      tone: "info",
    },
    {
      key: "audio",
      label: t("media.stats.audioLabel"),
      value: kindCount("audio"),
      icon: "music",
      tone: "accent",
    },
    {
      key: "cat",
      label: t("media.stats.categoryLabel"),
      value: categories.length,
      icon: "folder",
      tone: "warning",
    },
    {
      key: "size",
      label: t("media.stats.sizeLabel"),
      value: totalSize,
      icon: "database",
      tone: "primary",
    },
  ];
});

const visibleStatCards = computed(() => {
  const vis = props.statVisibility || {};
  return statCards.value.filter((card) => (vis as any)[card.key] !== false);
});

const viewModeToggleLabel = computed(() =>
  ui.gridMode === "card" ? t("media.viewMode.toList") : t("media.viewMode.toCard"),
);

const kindTabs = computed(() => [
  { id: "", label: t("media.kind.all"), icon: "layers" },
  { id: "image", label: t("media.kind.image"), icon: "image" },
  { id: "video", label: t("media.kind.video"), icon: "film" },
  { id: "audio", label: t("media.kind.audio"), icon: "music" },
]);

function submitSearch() {
  clearSearchTimer();
  emitSearchIfChanged(localQuery.value ?? "");
  searchInput.value?.blur();
}
function clearSearch() {
  clearSearchTimer();
  localQuery.value = "";
  emitSearchIfChanged("");
  searchInput.value?.focus();
}
function pickKind(kind: string) {
  emit("change-kind", kind);
}

const hasActiveFilter = computed(() => {
  const q = (props.query ?? "").trim();
  const k = props.kind ?? "";
  const cat = props.activeCategory ?? "";
  return !!(q || k || cat);
});

function resetFilters() {
  clearSearchTimer();
  if (localQuery.value) {
    localQuery.value = "";
  }
  if ((props.query ?? "") !== "") {
    emitSearchIfChanged("");
  }
  if ((props.kind ?? "") !== "") {
    emit("change-kind", "");
  }
  if ((props.activeCategory ?? "") !== "") {
    emit("select-category", "");
  }
}
</script>

<template>
  <section style="display: flex; flex-direction: column; gap: 14px">
    <div class="panel" style="display: flex; flex-direction: column; gap: 10px">
      <div class="toolbar">
        <div class="toolbar-search">
          <div class="input-wrap">
            <span class="icon-slot"><Icon name="search" :size="16" /></span>
            <input
              v-model="query"
              type="search"
              inputmode="search"
              enterkeyhint="search"
              autocomplete="off"
              :placeholder="$t('trash.searchPlaceholder')"
              @keyup.enter="reload(1)"
            />
          </div>
          <button class="primary search-submit" type="button" @click="reload(1)">
            <Icon name="search" :size="15" />
            <span class="hide-mobile">{{ $t("trash.searchBtn") }}</span>
          </button>
        </div>
        <div class="toolbar-actions">
          <button class="ghost" :disabled="loading" @click="reload(page)">
            <Icon name="refresh-cw" :size="14" />
            <span>{{ $t("trash.refresh") }}</span>
          </button>
        </div>
      </div>
    </div>

    <div v-if="loading" class="panel empty">
      <span>{{ $t("common.loading") }}</span>
    </div>

    <div v-else-if="!items.length" class="panel empty">
      <div class="illus"><Icon name="trash-2" :size="32" /></div>
      <strong>{{ $t("trash.emptyTitle") }}</strong>
      <span>{{ $t("trash.emptyHint") }}</span>
    </div>

    <div v-else class="panel" style="display: flex; flex-direction: column; gap: 10px">
      <article
        v-for="item in items"
        :key="item.id"
        class="trash-row"
      >
        <div class="trash-preview">
          <div class="trash-preview-fallback">
            <Icon
              :name="
                item.kind === 'image'
                  ? 'image'
                  : item.kind === 'video'
                    ? 'film'
                    : item.kind === 'audio'
                      ? 'music'
                      : 'file'
              "
              :size="16"
            />
          </div>
        </div>
        <div class="trash-meta">
          <strong class="ellipsis" :title="item.filename">{{ item.filename }}</strong>
          <div class="trash-sub">
            <span>{{ item.category }}</span>
            <span class="dot"></span>
            <span class="mono">{{ item.size_human || formatSize(item.size || 0) }}</span>
            <template v-if="item.deleted_at">
              <span class="dot"></span>
              <span class="mono">{{
                $t("trash.deletedAt", { time: formatTimestamp(item.deleted_at) || "-" })
              }}</span>
            </template>
            <template v-if="item.remaining_days !== undefined">
              <span class="dot"></span>
              <span class="mono">{{
                $t("trash.remainingDays", { days: Number(item.remaining_days || 0) })
              }}</span>
            </template>
          </div>
        </div>
        <div class="trash-actions">
          <button class="sm" @click="restore(item)">
            <Icon name="corner-up-left" :size="13" />
            {{ $t("trash.restore") }}
          </button>
          <button class="danger sm" @click="purge(item)">
            <Icon name="trash-2" :size="13" />
            {{ $t("trash.purge") }}
          </button>
        </div>
      </article>
    </div>

    <footer v-if="totalPages > 0" class="pager">
      <button class="icon sm" :disabled="page <= 1" @click="reload(page - 1)">
        <Icon name="chevron-left" :size="15" />
      </button>
      <span>{{ $t("trash.pagerText", { page, total: totalPages, count: total }) }}</span>
      <button class="icon sm" :disabled="page >= totalPages" @click="reload(page + 1)">
        <Icon name="chevron-right" :size="15" />
      </button>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { onMounted, ref } from "vue";
import { useI18n } from "vue-i18n";
import Icon from "@/components/common/Icon.vue";
import { mediaApi } from "@/api/media";
import type { TrashItem } from "@/api/types";
import { useToastStore } from "@/stores/toast";
import { useConfirmStore } from "@/stores/confirm";
import { useMediaStore } from "@/stores/media";
import { useCategoryStore } from "@/stores/category";
import { formatSize, formatTimestamp } from "@/utils/format";

const { t } = useI18n();
const toast = useToastStore();
const confirm = useConfirmStore();
const media = useMediaStore();
const category = useCategoryStore();

const loading = ref(false);
const items = ref<TrashItem[]>([]);
const query = ref("");
const page = ref(1);
const total = ref(0);
const totalPages = ref(0);

async function reload(nextPage = 1) {
  loading.value = true;
  try {
    const data = await mediaApi.listTrash({
      query: query.value.trim(),
      page: nextPage,
      page_size: 20,
    });
    items.value = data.items || [];
    page.value = data.page || nextPage;
    total.value = data.total || 0;
    totalPages.value = data.total_pages || 0;
  } catch (error) {
    toast.push((error as Error).message, "error");
  } finally {
    loading.value = false;
  }
}

async function restore(item: TrashItem) {
  const ok = await confirm.confirm({
    title: t("trash.restoreTitle"),
    message: t("trash.restoreConfirm", { name: item.filename }),
    confirmText: t("trash.restore"),
    tone: "primary",
    icon: "corner-up-left",
  });
  if (!ok) return;
  try {
    await mediaApi.restoreTrash(item.id);
    toast.push(t("trash.restoreDone", { name: item.filename }), "success");
    await Promise.all([reload(page.value), media.fetchList(), media.fetchStats(), category.fetch()]);
  } catch (error) {
    toast.push((error as Error).message, "error");
  }
}

async function purge(item: TrashItem) {
  const ok = await confirm.confirm({
    title: t("trash.purgeTitle"),
    message: t("trash.purgeConfirm", { name: item.filename }),
    detail: t("trash.purgeDetail"),
    confirmText: t("trash.purge"),
    tone: "danger",
    icon: "trash-2",
  });
  if (!ok) return;
  try {
    await mediaApi.purgeTrash(item.id);
    toast.push(t("trash.purgeDone", { name: item.filename }), "success");
    await reload(page.value);
  } catch (error) {
    toast.push((error as Error).message, "error");
  }
}

onMounted(() => {
  reload(1).catch((error) => toast.push((error as Error).message, "error"));
});
</script>

<style scoped>
.trash-row {
  display: grid;
  grid-template-columns: 64px minmax(0, 1fr) auto;
  gap: 10px;
  align-items: center;
}

.trash-preview {
  width: 64px;
  height: 64px;
  border: 1px solid var(--line-soft);
  border-radius: 10px;
  overflow: hidden;
  background: var(--surface-soft);
  padding: 0;
}

.trash-preview-fallback {
  width: 100%;
  height: 100%;
  display: grid;
  place-items: center;
  color: var(--text-muted);
}

.trash-meta {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.trash-sub {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
  color: var(--text-muted);
  font-size: 12px;
}

.trash-sub .dot {
  width: 3px;
  height: 3px;
  border-radius: 999px;
  background: currentColor;
  opacity: 0.5;
}

.trash-actions {
  display: inline-flex;
  gap: 8px;
  flex-wrap: wrap;
  justify-content: flex-end;
}
</style>

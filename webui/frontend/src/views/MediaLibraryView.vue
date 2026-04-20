<template>
  <MediaGrid
    :items="media.items"
    :loading="media.loading"
    :query="media.filters.query"
    :kind="media.filters.kind"
    :page="media.filters.page"
    :total-pages="media.pagination.totalPages"
    :total-count="media.pagination.total"
    :selected-ids="media.selectedIds"
    :readonly-token="auth.readonlyToken"
    :stats="media.stats"
    :active-category="media.filters.category"
    :categories="category.items"
    :stat-visibility="ui.statVisibility"
    @search="onSearch"
    @change-kind="onKindChange"
    @select-category="onSelectCategory"
    @toggle-select="media.toggleSelect"
    @preview="layout.previewItem"
    @detail="layout.openDetail"
    @open-upload="layout.openUpload('file')"
    @page-change="onPageChange"
    @clear-selection="media.clearSelection()"
    @batch-delete="batchDelete"
    @batch-change-category="layout.openBatchCategory"
    @copy-link="layout.copyMediaLink"
    @context-media="layout.openMediaContext"
  />
</template>

<script setup lang="ts">
import { inject } from "vue";
import { useI18n } from "vue-i18n";
import MediaGrid from "@/components/media/MediaGrid.vue";
import { useAuthStore } from "@/stores/auth";
import { useCategoryStore } from "@/stores/category";
import { useMediaStore } from "@/stores/media";
import { useUiStore } from "@/stores/ui";
import { useToastStore } from "@/stores/toast";
import { useConfirmStore } from "@/stores/confirm";

interface LayoutActions {
  openDetail: (item: any) => void;
  previewItem: (item: any) => void;
  openUpload: (mode?: "file" | "url") => void;
  openMediaContext: (payload: { event: MouseEvent; item: any }) => void;
  openBatchCategory: () => void;
  copyMediaLink: (id: string | number) => void;
}

const layout = inject<LayoutActions>("layoutActions")!;

const { t } = useI18n();
const auth = useAuthStore();
const category = useCategoryStore();
const media = useMediaStore();
const ui = useUiStore();
const toast = useToastStore();
const confirm = useConfirmStore();

function onSearch(query: string) {
  media.setSearch(query);
  media.fetchList().catch((error) => toast.push((error as Error).message, "error"));
}
function onKindChange(kind: string) {
  media.setKind(kind);
  media.fetchList().catch((error) => toast.push((error as Error).message, "error"));
}
function onPageChange(page: number) {
  media.setPage(page);
  media.fetchList().catch((error) => toast.push((error as Error).message, "error"));
}
function onSelectCategory(cat: string) {
  media.selectCategory(cat);
  media.fetchList().catch((error) => toast.push((error as Error).message, "error"));
  ui.setSidebarOpen(false);
}

async function batchDelete() {
  if (!media.selectedIds.length) return;
  const count = media.selectedIds.length;
  const ok = await confirm.confirm({
    title: t("mediaAction.batchDeleteTitle"),
    message: t("mediaAction.batchDeleteConfirm", { count }),
    detail: t("mediaAction.batchDeleteDetail"),
    confirmText: t("mediaAction.batchDeleteBtn", { count }),
    tone: "danger",
    icon: "trash-2",
  });
  if (!ok) return;
  let success = 0;
  for (const id of media.selectedIds) {
    try {
      await media.remove(id);
      success += 1;
    } catch (_e) {
      // ignore per-item
    }
  }
  toast.push(
    t("mediaAction.batchDeleteDone", { ok: success, total: count }),
    success === count ? "success" : "warning",
  );
  media.clearSelection();
  await Promise.all([media.fetchList(), category.fetch(), media.fetchStats()]);
}
</script>

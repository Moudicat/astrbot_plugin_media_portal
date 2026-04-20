<template>
  <div class="app-root">
    <transition name="fade">
      <div v-if="globalDragging" class="global-drop-overlay" @click.stop>
        <div class="global-drop-card">
          <Icon name="upload-cloud" :size="48" />
          <h3>{{ $t("upload.globalDropTitle") }}</h3>
          <p class="muted">
            {{
              $t("upload.globalDropHint", {
                category: media.filters.category || "default",
              })
            }}
          </p>
        </div>
      </div>
    </transition>

    <TopBar
      :theme="ui.theme"
      :selected-count="media.selectedIds.length"
      @toggle-sidebar="ui.setSidebarOpen(!ui.sidebarOpen)"
      @toggle-theme="ui.toggleTheme"
      @refresh="refreshAll"
      @settings="settingsVisible = true"
      @logout="handleLogout"
    />

    <div
      v-if="ui.sidebarOpen"
      class="sidebar-backdrop mobile-only"
      @click="ui.setSidebarOpen(false)"
    ></div>

    <main class="layout">
      <div class="sidebar-wrap" :class="{ open: ui.sidebarOpen }">
        <Sidebar
          :categories="category.items"
          :active-category="media.filters.category"
          :view-mode="viewMode"
          :total-count="media.stats.total_count || 0"
          :can-data-browse="config.canDataBrowse"
          @switch-mode="switchMode"
          @select-category="selectCategory"
          @request-create-category="categoryCreateVisible = true"
          @context-category="onContextCategory"
        />
      </div>

      <section class="content">
        <router-view />
      </section>

      <MediaDrawer
        :visible="drawerVisible"
        :media="selectedMedia"
        :categories="category.items"
        :readonly-token="auth.readonlyToken"
        @close="drawerVisible = false"
        @update="updateMedia"
        @delete="deleteMedia"
        @copy-link="copyMediaLink"
        @preview="previewItem"
      />
    </main>

    <UploadDialog
      :visible="uploadVisible"
      :categories="category.items"
      :active-category="media.filters.category"
      :initial-mode="uploadMode"
      :max-file-size-mb="config.maxMb"
      @close="uploadVisible = false"
      @upload-files="onUploadFiles"
      @save-url="onSaveUrl"
    />

    <PlayerModal
      :visible="playerVisible"
      :item="playerItem"
      :readonly-token="auth.readonlyToken"
      :can-navigate="playerList.length > 1"
      @close="playerVisible = false"
      @next="playerShift(1)"
      @prev="playerShift(-1)"
      @copy-link="copyPreviewLink"
    />

    <AudioDock
      :item="audioDockItem"
      :readonly-token="auth.readonlyToken"
      @close="audioDockItem = null"
    />

    <DataFileModal
      :preview="dataBrowser.preview"
      @close="dataBrowser.closePreview()"
      @copy="copyDataPreviewContent"
      @download="downloadDataFile"
    />

    <CategoryCreateDialog
      :visible="categoryCreateVisible"
      :existing="category.items"
      @close="categoryCreateVisible = false"
      @submit="onCreateCategory"
    />

    <CategoryRenameDialog
      :visible="categoryRenameVisible"
      :category="categoryRenameTarget"
      :existing="category.items"
      @close="closeCategoryRename"
      @submit="onRenameCategory"
    />

    <BatchCategoryDialog
      :visible="batchCategoryVisible"
      :count="media.selectedIds.length"
      :categories="category.items"
      :active-category="media.filters.category"
      @close="batchCategoryVisible = false"
      @submit="onSubmitBatchCategory"
    />

    <SettingsDialog
      :visible="settingsVisible"
      :stat-visibility="ui.statVisibility"
      @close="settingsVisible = false"
      @prune-categories="pruneCategories"
      @update-stat-visibility="ui.updateStatVisibility"
    />

    <UploadProgress
      :jobs="upload.jobs"
      :open="upload.panelOpen"
      @toggle="upload.toggle()"
      @cancel="upload.cancel($event)"
      @dismiss="upload.dismiss($event)"
      @clear-finished="upload.clearFinished()"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, provide, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import { useI18n } from "vue-i18n";
import Icon from "@/components/common/Icon.vue";
import Sidebar from "@/components/layout/Sidebar.vue";
import TopBar from "@/components/layout/TopBar.vue";
import MediaDrawer from "@/components/media/MediaDrawer.vue";
import UploadDialog from "@/components/media/UploadDialog.vue";
import PlayerModal from "@/components/media/PlayerModal.vue";
import AudioDock from "@/components/media/AudioDock.vue";
import UploadProgress from "@/components/media/UploadProgress.vue";
import DataFileModal from "@/components/data/DataFileModal.vue";
import CategoryCreateDialog from "@/components/category/CategoryCreateDialog.vue";
import CategoryRenameDialog from "@/components/category/CategoryRenameDialog.vue";
import BatchCategoryDialog from "@/components/category/BatchCategoryDialog.vue";
import SettingsDialog from "@/components/settings/SettingsDialog.vue";
import { useAuthStore } from "@/stores/auth";
import { useConfigStore } from "@/stores/config";
import { useMediaStore } from "@/stores/media";
import { useCategoryStore } from "@/stores/category";
import { useDataBrowserStore } from "@/stores/dataBrowser";
import { useUploadStore } from "@/stores/upload";
import { useUiStore } from "@/stores/ui";
import { useToastStore } from "@/stores/toast";
import { useConfirmStore } from "@/stores/confirm";
import { buildDataFileUrl } from "@/api/data";
import { mediaApi } from "@/api/media";
import { buildMediaDirectUrl, shareAbsoluteUrl } from "@/utils/url";
import { copyText } from "@/utils/clipboard";
import type { CategoryItem, ContextMenuEntry, MediaItem } from "@/api/types";
import type { DataTreeItem } from "@/api/types";

const { t } = useI18n();
const router = useRouter();
const route = useRoute();

const auth = useAuthStore();
const config = useConfigStore();
const media = useMediaStore();
const category = useCategoryStore();
const dataBrowser = useDataBrowserStore();
const upload = useUploadStore();
const ui = useUiStore();
const toast = useToastStore();
const confirm = useConfirmStore();

const drawerVisible = ref(false);
const selectedMedia = ref<MediaItem | null>(null);
const uploadVisible = ref(false);
const uploadMode = ref<"file" | "url">("file");
const playerVisible = ref(false);
const playerItem = ref<any>(null);
const playerList = ref<any[]>([]);
const playerSource = ref<"media" | "data">("media");
const audioDockItem = ref<any>(null);
const categoryCreateVisible = ref(false);
const categoryRenameVisible = ref(false);
const categoryRenameTarget = ref<CategoryItem | null>(null);
const batchCategoryVisible = ref(false);
const settingsVisible = ref(false);

const viewMode = computed(() => (route.name === "data" ? "data" : "media"));

const globalDragging = ref(false);
let dragDepth = 0;
let dragHideTimer: ReturnType<typeof setTimeout> | null = null;

provide("layoutActions", {
  openDetail,
  previewItem,
  openUpload,
  openMediaContext,
  openBatchCategory,
  copyMediaLink,
});

upload.setRefreshHandler(() => {
  media.fetchList().catch((error) => toast.push((error as Error).message, "error"));
  category.fetch().catch(() => undefined);
  media.fetchStats();
});
upload.setErrorHandler((text) => toast.push(text, "error"));

onMounted(async () => {
  ui.applyTheme();
  attachGlobalUploadHandlers();
  if (!auth.token) return;
  try {
    await bootstrap();
  } catch (error) {
    const err = error as Error;
    toast.push(t("bootstrap.initError", { message: err.message }), "error");
    await auth.logout(false);
    router.replace({ name: "login" });
  }
});

onBeforeUnmount(() => {
  detachGlobalUploadHandlers();
});

async function bootstrap() {
  await config.fetch();
  await Promise.all([category.fetch(), media.fetchStats(), media.fetchList()]);
  if (viewMode.value === "data" && config.canDataBrowse) {
    await dataBrowser.fetchTree("");
  }
}

function refreshAll() {
  const jobs =
    viewMode.value === "media"
      ? [category.fetch(), media.fetchList(), media.fetchStats()]
      : [dataBrowser.fetchTree(dataBrowser.path)];
  Promise.all(jobs)
    .then(() => toast.push(t("media.refreshed"), "success"))
    .catch((error) => toast.push((error as Error).message, "error"));
}

async function handleLogout() {
  await auth.logout();
  toast.push(t("login.loggedOut"), "info");
  router.replace({ name: "login" });
}

function switchMode(mode: string) {
  ui.setSidebarOpen(false);
  if (mode === "data") {
    if (!config.canDataBrowse) return;
    router.push({ name: "data" });
    dataBrowser.fetchTree(dataBrowser.path || "").catch((error) =>
      toast.push((error as Error).message, "error"),
    );
  } else {
    router.push({ name: "media" });
    media.fetchList().catch((error) => toast.push((error as Error).message, "error"));
  }
}

function selectCategory(cat: string) {
  media.selectCategory(cat);
  media.fetchList().catch((error) => toast.push((error as Error).message, "error"));
  ui.setSidebarOpen(false);
}

async function openDetail(item: MediaItem) {
  try {
    selectedMedia.value = await media.detail(item.id);
    drawerVisible.value = true;
  } catch (error) {
    toast.push((error as Error).message, "error");
  }
}

function previewItem(item: MediaItem) {
  if (item.kind === "audio") {
    audioDockItem.value = item;
    playerVisible.value = false;
    playerItem.value = null;
    return;
  }
  playerList.value = media.items.filter((entry) => entry && entry.kind !== "audio");
  playerSource.value = "media";
  playerItem.value = item;
  playerVisible.value = true;
}

function openUpload(mode: "file" | "url" = "file") {
  uploadMode.value = mode;
  uploadVisible.value = true;
}

function playerIdentity(item: any): string {
  if (!item) return "";
  if (item.id != null) return `id:${item.id}`;
  if (item.path) return `path:${item.path}`;
  if (item.filename) return `file:${item.filename}`;
  return "";
}
function playerShift(delta: number) {
  if (!playerItem.value) return;
  const list = playerList.value || [];
  if (!list.length) return;
  const key = playerIdentity(playerItem.value);
  let idx = list.findIndex((entry) => playerIdentity(entry) === key);
  if (idx < 0) idx = 0;
  const nextIdx = (idx + delta + list.length) % list.length;
  const next = list[nextIdx];
  if (!next) return;
  if (playerSource.value === "data") {
    const directUrl = buildDataFileUrl(next.path, { token: auth.dataToken });
    playerItem.value = { ...next, directUrl, filename: next.name };
  } else {
    playerItem.value = next;
  }
}

async function updateMedia(payload: Record<string, any>) {
  try {
    const updated = await media.patch(payload.id, payload);
    toast.push(t("drawer.saved"), "success");
    selectedMedia.value = updated;
    drawerVisible.value = false;
    await Promise.all([category.fetch(), media.fetchList(), media.fetchStats()]);
  } catch (error) {
    toast.push((error as Error).message, "error");
  }
}

async function deleteMedia(id: string | number) {
  const ok = await confirm.confirm({
    title: t("mediaAction.deleteTitle"),
    message: t("mediaAction.deleteConfirm"),
    detail: t("mediaAction.deleteDetail"),
    confirmText: t("mediaAction.deleteBtn"),
    tone: "danger",
    icon: "trash-2",
  });
  if (!ok) return;
  try {
    await media.remove(id);
    toast.push(t("mediaAction.deleted"), "success");
    drawerVisible.value = false;
    selectedMedia.value = null;
    await Promise.all([media.fetchList(), category.fetch(), media.fetchStats()]);
  } catch (error) {
    toast.push((error as Error).message, "error");
  }
}

async function copyMediaLink(mediaId: string | number) {
  try {
    const detail = await media.detail(mediaId);
    const raw = detail.public_url || "";
    if (!raw) throw new Error(t("mediaAction.linkEmpty"));
    const text = shareAbsoluteUrl(raw, config.publicBaseUrl);
    await copyText(text);
    toast.push(t("mediaAction.linkCopied"), "success");
  } catch (error) {
    toast.push((error as Error).message, "error");
  }
}
async function copyPreviewLink(payload: { id?: string | number; url?: string }) {
  if (!payload) return;
  if (payload.id != null) return copyMediaLink(payload.id);
  if (payload.url) {
    try {
      const text = shareAbsoluteUrl(payload.url, config.publicBaseUrl);
      if (!text) throw new Error(t("mediaAction.urlEmpty"));
      await copyText(text);
      toast.push(t("mediaAction.linkCopied"), "success");
    } catch (error) {
      toast.push((error as Error).message, "error");
    }
  }
}

async function copyDataPreviewContent() {
  if (!dataBrowser.preview || !dataBrowser.preview.content) return;
  try {
    await copyText(dataBrowser.preview.content);
    toast.push(t("dataFile.contentCopied"), "success");
  } catch (error) {
    toast.push((error as Error).message, "error");
  }
}

function downloadDataFile(payload: { path: string; name: string }) {
  if (!payload?.path) return;
  const url = buildDataFileUrl(payload.path, { token: auth.dataToken, download: true });
  const link = document.createElement("a");
  link.href = url;
  link.download = payload.name || "";
  link.rel = "noopener";
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
}

function hasFiles(event: DragEvent): boolean {
  const types = event.dataTransfer?.types;
  if (!types) return false;
  const anyTypes = types as unknown as { contains?: (v: string) => boolean; length: number };
  if (typeof anyTypes.contains === "function") {
    return anyTypes.contains("Files");
  }
  return Array.prototype.indexOf.call(types, "Files") >= 0;
}

function onWindowDragEnter(event: DragEvent) {
  if (!hasFiles(event)) return;
  if (route.name === "login") return;
  event.preventDefault();
  dragDepth += 1;
  if (dragHideTimer) {
    clearTimeout(dragHideTimer);
    dragHideTimer = null;
  }
  globalDragging.value = true;
}

function onWindowDragOver(event: DragEvent) {
  if (!hasFiles(event)) return;
  if (route.name === "login") return;
  event.preventDefault();
  if (event.dataTransfer) event.dataTransfer.dropEffect = "copy";
  globalDragging.value = true;
}

function onWindowDragLeave(event: DragEvent) {
  if (!hasFiles(event)) return;
  dragDepth = Math.max(0, dragDepth - 1);
  if (dragDepth === 0) {
    if (dragHideTimer) clearTimeout(dragHideTimer);
    dragHideTimer = setTimeout(() => {
      globalDragging.value = false;
      dragHideTimer = null;
    }, 80);
  }
}

function onWindowDrop(event: DragEvent) {
  const hasPayload = hasFiles(event);
  dragDepth = 0;
  if (dragHideTimer) {
    clearTimeout(dragHideTimer);
    dragHideTimer = null;
  }
  globalDragging.value = false;
  if (!hasPayload) return;
  if (route.name === "login") return;
  event.preventDefault();
  event.stopPropagation();
  const incoming = Array.from(event.dataTransfer?.files || []);
  if (!incoming.length) return;
  enqueueDropped(incoming);
}

function onWindowPaste(event: ClipboardEvent) {
  if (route.name === "login") return;
  if (!auth.token) return;
  const target = event.target as HTMLElement | null;
  if (target) {
    const tag = (target.tagName || "").toLowerCase();
    if (
      tag === "input" ||
      tag === "textarea" ||
      target.isContentEditable ||
      target.closest?.("input, textarea, [contenteditable='true']")
    ) {
      return;
    }
  }
  const clipboardFiles: File[] = [];
  const items = event.clipboardData?.items;
  if (items && items.length) {
    for (const item of Array.from(items)) {
      if (item.kind === "file") {
        const f = item.getAsFile();
        if (f) clipboardFiles.push(normalizePastedFile(f));
      }
    }
  }
  const dtFiles = Array.from(event.clipboardData?.files || []);
  for (const f of dtFiles) {
    if (!clipboardFiles.some((x) => x.name === f.name && x.size === f.size)) {
      clipboardFiles.push(normalizePastedFile(f));
    }
  }
  if (!clipboardFiles.length) return;
  event.preventDefault();
  enqueueDropped(clipboardFiles, { fromPaste: true });
}

function normalizePastedFile(file: File): File {
  if (file.name && file.name !== "image.png" && file.name !== "blob") return file;
  const ext = guessExtFromType(file.type);
  if (!ext) return file;
  const stamp = new Date()
    .toISOString()
    .replace(/[-:]/g, "")
    .replace(/\..+$/, "")
    .replace("T", "-");
  const newName = `clipboard-${stamp}.${ext}`;
  try {
    return new File([file], newName, {
      type: file.type,
      lastModified: file.lastModified || Date.now(),
    });
  } catch (_e) {
    return file;
  }
}

function guessExtFromType(mime: string): string {
  if (!mime) return "";
  const map: Record<string, string> = {
    "image/png": "png",
    "image/jpeg": "jpg",
    "image/jpg": "jpg",
    "image/gif": "gif",
    "image/webp": "webp",
    "image/bmp": "bmp",
    "image/svg+xml": "svg",
  };
  return map[mime] || "";
}

function enqueueDropped(incoming: File[], opts: { fromPaste?: boolean } = {}) {
  if (!auth.token) return;
  if (!incoming.length) return;
  const targetCategory = media.filters.category || "default";
  const maxBytes = config.maxBytes;
  const maxMb = config.maxMb;
  const accepted: File[] = [];
  const rejected: File[] = [];
  for (const file of incoming) {
    if (maxBytes > 0 && Number(file.size) > maxBytes) rejected.push(file);
    else accepted.push(file);
  }
  if (rejected.length) {
    const names = rejected.map((f) => f.name).join("、");
    toast.push(
      t("upload.skippedOversize", { count: rejected.length, mb: maxMb, names }),
      "warning",
    );
  }
  if (!accepted.length) return;
  for (const file of accepted) {
    upload.enqueue(file, targetCategory, "");
  }
  toast.push(
    opts.fromPaste
      ? t("upload.pasteQueued", { count: accepted.length, category: targetCategory })
      : t("upload.dropQueued", { count: accepted.length, category: targetCategory }),
    "success",
  );
}

function attachGlobalUploadHandlers() {
  window.addEventListener("dragenter", onWindowDragEnter);
  window.addEventListener("dragover", onWindowDragOver);
  window.addEventListener("dragleave", onWindowDragLeave);
  window.addEventListener("drop", onWindowDrop);
  window.addEventListener("paste", onWindowPaste);
}

function detachGlobalUploadHandlers() {
  window.removeEventListener("dragenter", onWindowDragEnter);
  window.removeEventListener("dragover", onWindowDragOver);
  window.removeEventListener("dragleave", onWindowDragLeave);
  window.removeEventListener("drop", onWindowDrop);
  window.removeEventListener("paste", onWindowPaste);
}

function onUploadFiles(payload: { category: string; description: string; files: File[] }) {
  const files = Array.from(payload.files || []);
  if (!files.length) return;
  const maxBytes = config.maxBytes;
  const maxMb = config.maxMb;
  const accepted: File[] = [];
  const rejected: File[] = [];
  for (const file of files) {
    if (maxBytes > 0 && Number(file.size) > maxBytes) rejected.push(file);
    else accepted.push(file);
  }
  if (rejected.length) {
    const names = rejected.map((f) => f.name).join("、");
    toast.push(
      t("upload.skippedOversize", { count: rejected.length, mb: maxMb, names }),
      "warning",
    );
  }
  if (!accepted.length) return;
  for (const file of accepted) {
    upload.enqueue(file, payload.category || "default", payload.description || "");
  }
}

async function onSaveUrl(payload: {
  category: string;
  description: string;
  url: string;
  filename: string;
}) {
  try {
    await mediaApi.saveUrl(payload);
    toast.push(t("upload.remoteSaved"), "success");
    await Promise.all([media.fetchList(), category.fetch(), media.fetchStats()]);
  } catch (error) {
    toast.push((error as Error).message, "error");
  }
}

async function onCreateCategory(payload: { category: string; description: string }) {
  try {
    await category.create(payload);
    toast.push(t("categoryCreate.createdOk", { name: payload.category }), "success");
    categoryCreateVisible.value = false;
  } catch (error) {
    toast.push((error as Error).message, "error");
  }
}

function closeCategoryRename() {
  categoryRenameVisible.value = false;
  categoryRenameTarget.value = null;
}

async function onRenameCategory(payload: {
  oldName: string;
  newName: string;
  description: string;
}) {
  if (!payload?.oldName) return;
  const body: { new_name?: string; description?: string } = {};
  if (payload.newName && payload.newName !== payload.oldName) body.new_name = payload.newName;
  if (payload.description !== undefined) body.description = payload.description;
  if (!Object.keys(body).length) {
    closeCategoryRename();
    return;
  }
  try {
    const result = await category.update(payload.oldName, body);
    const finalName = (result && result.category) || payload.newName;
    if (media.filters.category === payload.oldName) {
      media.filters.category = finalName;
    }
    if (payload.newName !== payload.oldName) {
      toast.push(t("categoryRename.renamedOk", { name: finalName }), "success");
    } else {
      toast.push(t("categoryRename.descUpdated"), "success");
    }
    await Promise.all([category.fetch(), media.fetchStats(), media.fetchList()]);
    closeCategoryRename();
  } catch (error) {
    toast.push((error as Error).message, "error");
  }
}

function openBatchCategory() {
  if (!media.selectedIds.length) {
    toast.push(t("batchCategory.selectFirst"), "info");
    return;
  }
  batchCategoryVisible.value = true;
}

async function onSubmitBatchCategory(payload: { category: string }) {
  const target = payload?.category || "";
  if (!target || !media.selectedIds.length) {
    batchCategoryVisible.value = false;
    return;
  }
  const ids = [...media.selectedIds];
  let ok = 0;
  let firstError = "";
  for (const id of ids) {
    try {
      await media.patch(id, { category: target });
      ok += 1;
    } catch (error) {
      if (!firstError) firstError = (error as Error).message || "unknown";
    }
  }
  batchCategoryVisible.value = false;
  media.clearSelection();
  if (ok === ids.length) {
    toast.push(t("batchCategory.movedOk", { count: ok, target }), "success");
  } else if (ok > 0) {
    let message = t("batchCategory.movedPartial", { ok, total: ids.length, target });
    if (firstError) message += t("batchCategory.movedFirstError", { error: firstError });
    toast.push(message, "warning");
  } else {
    toast.push(
      firstError
        ? t("batchCategory.movedFailedDetail", { error: firstError })
        : t("batchCategory.movedFailed"),
      "error",
    );
  }
  await Promise.all([category.fetch(), media.fetchStats(), media.fetchList()]);
}

async function pruneCategories() {
  const ok = await confirm.confirm({
    title: t("categoryAction.pruneTitle"),
    message: t("categoryAction.pruneConfirm"),
    confirmText: t("categoryAction.pruneBtn"),
    tone: "warning",
    icon: "eraser",
  });
  if (!ok) return;
  try {
    const result = await category.prune();
    const count = result.removed_count || 0;
    if (count > 0) {
      const names = (result.removed || []).join("、");
      toast.push(
        names
          ? t("categoryAction.pruneDone", { count, names })
          : t("categoryAction.pruneDoneNoNames", { count }),
        "success",
      );
      if (media.filters.category && (result.removed || []).includes(media.filters.category)) {
        media.filters.category = "";
      }
    } else {
      toast.push(t("categoryAction.pruneNone"), "info");
    }
    await Promise.all([category.fetch(), media.fetchStats(), media.fetchList()]);
  } catch (error) {
    toast.push((error as Error).message, "error");
  }
}

function onContextCategory({ event, item }: { event: MouseEvent; item: any }) {
  if (!item) return;
  if (item.isAll) {
    ui.openContextMenu(
      event,
      [{ key: "noop", icon: "lock", label: t("sidebar.ctxNoModify"), disabled: true }],
      { kind: "category", item, onSelect: () => undefined },
    );
    return;
  }
  const isDefault = item.category === "default";
  const items: ContextMenuEntry[] = [
    {
      key: "rename",
      icon: "pencil",
      label: isDefault ? t("sidebar.ctxRenameDisabled") : t("sidebar.ctxRename"),
      tone: "primary",
      disabled: isDefault,
    },
    { divider: true, key: `cat_d_${item.category || ""}` },
    {
      key: "delete",
      icon: "trash-2",
      label: isDefault ? t("sidebar.ctxDeleteDisabled") : t("sidebar.ctxDelete"),
      tone: "danger",
      disabled: isDefault,
    },
  ];
  ui.openContextMenu(event, items, {
    kind: "category",
    item,
    onSelect(key: string) {
      ui.closeContextMenu();
      if (!item || item.category === "default") return;
      if (key === "rename") {
        categoryRenameTarget.value = { ...item };
        categoryRenameVisible.value = true;
      } else if (key === "delete") {
        confirmDeleteCategory(item);
      }
    },
  });
}

async function confirmDeleteCategory(item: CategoryItem) {
  if (!item || item.category === "default") return;
  const count = Number(item.count || 0);
  const message =
    count > 0
      ? t("categoryAction.deleteWithChildren", { name: item.category, count })
      : t("categoryAction.deleteConfirm", { name: item.category });
  const detail = count > 0 ? t("categoryAction.deleteDetail") : "";
  const ok = await confirm.confirm({
    title: t("categoryAction.deleteTitle"),
    message,
    detail,
    confirmText: t("categoryAction.deleteBtn"),
    tone: "danger",
    icon: "trash-2",
  });
  if (!ok) return;
  try {
    const result = await category.remove(item.category, true);
    const removedRows = result?.deleted_rows || 0;
    if (media.filters.category === item.category) media.filters.category = "";
    toast.push(
      removedRows > 0
        ? t("categoryAction.deletedWithCount", { name: item.category, count: removedRows })
        : t("categoryAction.deletedOk", { name: item.category }),
      "success",
    );
    await Promise.all([category.fetch(), media.fetchStats(), media.fetchList()]);
  } catch (error) {
    toast.push((error as Error).message, "error");
  }
}

function openMediaContext({ event, item }: { event: MouseEvent; item: MediaItem }) {
  if (!item) return;
  const items: ContextMenuEntry[] = [
    { key: "copy-link", icon: "link-2", label: t("mediaAction.ctxCopyLink"), tone: "primary" },
    { key: "save", icon: "download", label: t("mediaAction.ctxSave"), tone: "accent" },
    { key: "open", icon: "external-link", label: t("mediaAction.ctxOpen") },
    { divider: true, key: `d_${item.id || ""}` },
    { key: "delete", icon: "trash-2", label: t("mediaAction.ctxDelete"), tone: "danger" },
  ];
  ui.openContextMenu(event, items, {
    kind: "media",
    item,
    onSelect(key: string) {
      ui.closeContextMenu();
      handleMediaContextAction(key, item);
    },
  });
}

async function handleMediaContextAction(key: string, item: MediaItem) {
  switch (key) {
    case "copy-link":
      await copyMediaLink(item.id);
      break;
    case "save":
      await downloadMedia(item);
      break;
    case "open":
      openMediaInNewTab(item);
      break;
    case "delete":
      await deleteMedia(item.id);
      break;
    default:
      break;
  }
}

async function downloadMedia(item: MediaItem) {
  try {
    let url = "";
    try {
      const detail = await media.detail(item.id);
      url = detail?.public_url || buildMediaDirectUrl(item.category, item.filename, auth.readonlyToken);
    } catch (_e) {
      url = buildMediaDirectUrl(item.category, item.filename, auth.readonlyToken);
    }
    if (!url) throw new Error(t("mediaAction.linkGetEmpty"));
    const link = document.createElement("a");
    link.href = url;
    link.download = item.filename || "";
    link.rel = "noopener";
    link.target = "_blank";
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  } catch (error) {
    toast.push((error as Error).message || t("mediaAction.downloadFailed"), "error");
  }
}

function openMediaInNewTab(item: MediaItem) {
  const url = buildMediaDirectUrl(item.category, item.filename, auth.readonlyToken);
  if (!url) {
    toast.push(t("mediaAction.linkGetFailed"), "error");
    return;
  }
  window.open(url, "_blank", "noopener");
}

defineExpose({
  openDataFile(item: DataTreeItem) {
    handleDataFile(item);
  },
});

function handleDataFile(item: DataTreeItem) {
  const directUrl = buildDataFileUrl(item.path, { token: auth.dataToken });
  if (item.kind === "image" || item.kind === "video" || item.kind === "audio") {
    const previewItem = { ...item, directUrl, filename: item.name };
    if (item.kind === "audio") {
      audioDockItem.value = previewItem;
      playerVisible.value = false;
      playerItem.value = null;
      return;
    }
    playerList.value = (dataBrowser.items || []).filter(
      (entry) => entry && !entry.is_dir && (entry.kind === "image" || entry.kind === "video"),
    );
    playerSource.value = "data";
    playerItem.value = previewItem;
    playerVisible.value = true;
    return;
  }
  dataBrowser
    .openText(item, (p) => buildDataFileUrl(p, { token: auth.dataToken, download: true }))
    .catch((error) => toast.push((error as Error).message, "error"));
}

provide("handleDataFile", handleDataFile);
</script>

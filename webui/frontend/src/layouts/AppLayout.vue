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
      :sidebar-visible="sidebarVisible"
      @toggle-sidebar="ui.toggleSidebar"
      @toggle-theme="ui.toggleTheme"
      @refresh="refreshAll"
      @intelligence="intelligenceVisible = true"
      @settings="settingsVisible = true"
      @logout="handleLogout"
    />

    <div
      v-if="ui.sidebarOpen"
      class="sidebar-backdrop mobile-only"
      @click="ui.setSidebarOpen(false)"
    ></div>

    <main class="layout" :class="{ 'sidebar-collapsed': ui.sidebarCollapsed }">
      <div class="sidebar-wrap" :class="{ open: ui.sidebarOpen }">
        <Sidebar
          :categories="category.items"
          :active-category="route.name === 'media' ? media.filters.category : ''"
          :active-route="String(route.name || '')"
          :view-mode="viewMode"
          :total-count="media.stats.total_count || 0"
          :can-data-browse="config.canDataBrowse"
          :can-face-browse="config.canFaceBrowse"
          @switch-mode="switchMode"
          @select-category="selectCategory"
          @open-trash="openTrashView"
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
      :trash-retention-days="config.trashRetentionDays"
      @close="settingsVisible = false"
      @prune-categories="pruneCategories"
      @update-stat-visibility="ui.updateStatVisibility"
      @open-duplicates="openDuplicatesView"
      @update-trash-retention="updateTrashRetention"
      @purge-trash-expired="purgeExpiredTrash"
    />

    <IntelligenceDialog
      :visible="intelligenceVisible"
      @close="intelligenceVisible = false"
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
import { computed, onBeforeUnmount, onMounted, provide, ref, watch } from "vue";
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
import IntelligenceDialog from "@/components/settings/IntelligenceDialog.vue";
import { useAuthStore } from "@/stores/auth";
import { useConfigStore } from "@/stores/config";
import { useMediaStore } from "@/stores/media";
import { useCategoryStore } from "@/stores/category";
import { useDataBrowserStore } from "@/stores/dataBrowser";
import { useUploadStore } from "@/stores/upload";
import { useProgressStore } from "@/stores/progress";
import { useUiStore } from "@/stores/ui";
import { useToastStore } from "@/stores/toast";
import { useConfirmStore } from "@/stores/confirm";
import { buildDataFileUrl } from "@/api/data";
import { mediaApi } from "@/api/media";
import { ApiError } from "@/api/client";
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
const progress = useProgressStore();
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
const intelligenceVisible = ref(false);

const viewMode = computed(() => {
  if (route.name === "data") return "data";
  if (route.name === "faces") return "face";
  return "media";
});

const PC_HOVER_QUERY = "(hover: hover) and (pointer: fine)";
const isPcHoverDevice = ref(
  typeof window !== "undefined" && typeof window.matchMedia === "function"
    ? window.matchMedia(PC_HOVER_QUERY).matches
    : true,
);
let pcHoverMql: MediaQueryList | null = null;
const onPcHoverChange = (event: MediaQueryListEvent) => {
  isPcHoverDevice.value = event.matches;
};

const sidebarVisible = computed(() =>
  isPcHoverDevice.value ? !ui.sidebarCollapsed : ui.sidebarOpen,
);

function routeCategoryValue(raw: unknown): string {
  if (Array.isArray(raw)) return String(raw[0] || "");
  return typeof raw === "string" ? raw : "";
}

function buildMediaRouteQuery(categoryValue: string): Record<string, string> {
  const normalized = String(categoryValue || "").trim();
  return normalized ? { category: normalized } : {};
}

function syncMediaFilterFromRoute() {
  if (route.name !== "media") return;
  const categoryFromRoute = routeCategoryValue(route.query.category);
  if (media.filters.category !== categoryFromRoute) {
    media.selectCategory(categoryFromRoute);
  }
}

async function syncMediaCategoryToRoute(categoryValue: string) {
  if (route.name !== "media") return;
  const current = routeCategoryValue(route.query.category);
  const normalized = String(categoryValue || "").trim();
  if (current === normalized) return;
  try {
    await router.replace({ name: "media", query: buildMediaRouteQuery(normalized) });
  } catch (_error) {
    // ignore duplicated navigation
  }
}

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

watch(
  () => [route.name, route.query.category],
  () => {
    if (route.name !== "media") return;
    syncMediaFilterFromRoute();
    media.fetchList().catch((error) => toast.push((error as Error).message, "error"));
  },
);

onMounted(async () => {
  ui.applyTheme();
  attachGlobalUploadHandlers();
  if (typeof window !== "undefined" && typeof window.matchMedia === "function") {
    pcHoverMql = window.matchMedia(PC_HOVER_QUERY);
    isPcHoverDevice.value = pcHoverMql.matches;
    if (typeof pcHoverMql.addEventListener === "function") {
      pcHoverMql.addEventListener("change", onPcHoverChange);
    } else if (typeof (pcHoverMql as any).addListener === "function") {
      (pcHoverMql as any).addListener(onPcHoverChange);
    }
  }
  if (!auth.token) return;
  try {
    await bootstrap();
  } catch (error) {
    const err = error as Error;
    toast.push(t("bootstrap.initError", { message: err.message }), "error");
    await auth.logout(false);
    router.replace({ name: "login" });
  }
  progress.start();
});

onBeforeUnmount(() => {
  detachGlobalUploadHandlers();
  progress.stop();
  if (pcHoverMql) {
    if (typeof pcHoverMql.removeEventListener === "function") {
      pcHoverMql.removeEventListener("change", onPcHoverChange);
    } else if (typeof (pcHoverMql as any).removeListener === "function") {
      (pcHoverMql as any).removeListener(onPcHoverChange);
    }
    pcHoverMql = null;
  }
});

async function bootstrap() {
  await config.fetch();
  syncMediaFilterFromRoute();
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
  } else if (mode === "face") {
    if (!config.canFaceBrowse) return;
    router.push({ name: "faces" });
  } else {
    router.push({
      name: "media",
      query: buildMediaRouteQuery(media.filters.category || ""),
    });
    media.fetchList().catch((error) => toast.push((error as Error).message, "error"));
  }
}

function openTrashView() {
  settingsVisible.value = false;
  ui.setSidebarOpen(false);
  router.push({ name: "trash" });
}

function openDuplicatesView() {
  settingsVisible.value = false;
  ui.setSidebarOpen(false);
  router.push({ name: "duplicates" });
}

async function updateTrashRetention(days: number) {
  try {
    await mediaApi.setTrashSettings(days);
    await config.fetch();
    toast.push(t("settings.trashRetentionSaved"), "success");
  } catch (error) {
    toast.push((error as Error).message, "error");
  }
}

async function purgeExpiredTrash() {
  const ok = await confirm.confirm({
    title: t("settings.trashPurgeTitle"),
    message: t("settings.trashPurgeConfirm"),
    confirmText: t("settings.trashPurgeNow"),
    tone: "warning",
    icon: "trash-2",
  });
  if (!ok) return;
  try {
    const result = await mediaApi.purgeExpiredTrash();
    toast.push(t("settings.trashPurgedDone", { count: result.purged || 0 }), "success");
  } catch (error) {
    toast.push((error as Error).message, "error");
  }
}

async function selectCategory(cat: string) {
  ui.setSidebarOpen(false);
  const normalized = String(cat || "").trim();
  if (route.name !== "media") {
    try {
      await router.push({ name: "media", query: buildMediaRouteQuery(normalized) });
    } catch (_error) {
      // ignore duplicated navigation
    }
    return;
  }
  await syncMediaCategoryToRoute(normalized);
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

function resetGlobalDragState() {
  dragDepth = 0;
  if (dragHideTimer) {
    clearTimeout(dragHideTimer);
    dragHideTimer = null;
  }
  globalDragging.value = false;
}

function onWindowDragEnter(event: DragEvent) {
  if (!hasFiles(event)) return;
  if (route.name === "login") return;
  event.preventDefault();
  if (uploadVisible.value) {
    resetGlobalDragState();
    return;
  }
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
  if (uploadVisible.value) {
    if (globalDragging.value) resetGlobalDragState();
    return;
  }
  globalDragging.value = true;
}

function onWindowDragLeave(event: DragEvent) {
  if (!hasFiles(event)) return;
  if (uploadVisible.value) return;
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
  resetGlobalDragState();
  if (!hasPayload) return;
  if (route.name === "login") return;
  if (uploadVisible.value) {
    // 优先交给 UploadDialog 内部的 dropzone 处理；阻止默认行为以避免浏览器打开文件
    event.preventDefault();
    return;
  }
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
    await mediaApi.saveUrl({ ...payload, duplicate_policy: "error" });
    toast.push(t("upload.remoteSaved"), "success");
    await Promise.all([media.fetchList(), category.fetch(), media.fetchStats()]);
  } catch (error) {
    const apiError = error as ApiError;
    const detail = (apiError && apiError.detail) || null;
    const code = detail && typeof detail === "object" ? (detail as any).code : "";
    if (apiError.status === 409 && code === "duplicate_sha256") {
      const existing = (detail as any).existing || {};
      const ok = await confirm.confirm({
        title: t("upload.duplicateTitle"),
        message: t("upload.duplicateMessage", { name: existing.filename || payload.filename || "-" }),
        detail: t("upload.duplicateDetail"),
        confirmText: t("upload.duplicateContinue"),
        cancelText: t("upload.duplicateCancel"),
        tone: "warning",
        icon: "alert-triangle",
      });
      if (!ok) {
        toast.push(t("upload.duplicateCancelled"), "info");
        return;
      }
      try {
        await mediaApi.saveUrl({ ...payload, duplicate_policy: "force" });
        toast.push(t("upload.remoteSaved"), "success");
        await Promise.all([media.fetchList(), category.fetch(), media.fetchStats()]);
      } catch (innerError) {
        toast.push((innerError as Error).message, "error");
      }
      return;
    }
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
      media.selectCategory(finalName);
      await syncMediaCategoryToRoute(finalName);
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
        media.selectCategory("");
        await syncMediaCategoryToRoute("");
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
    if (media.filters.category === item.category) {
      media.selectCategory("");
      await syncMediaCategoryToRoute("");
    }
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

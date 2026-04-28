<template>
  <div class="faces-view">
    <div class="faces-toolbar">
      <div class="faces-toolbar-info">
        <h2>
          <Icon name="user" :size="20" />
          <span>{{ $t("face.title") }}</span>
        </h2>
        <p class="muted">{{ $t("face.subtitle") }}</p>
      </div>
      <div class="faces-toolbar-actions">
        <button
          class="ghost sm"
          :disabled="cleanupPending || !faceFeatureEnabled"
          :title="$t('face.cleanupHint')"
          @click="onCleanupOrphans"
        >
          <Icon name="trash" :size="14" />
          <span>{{ $t("face.cleanupOrphans") }}</span>
        </button>
        <button
          class="ghost sm"
          :disabled="rebuildPending || !faceFeatureEnabled"
          :title="$t('face.rebuildThumbsHint')"
          @click="onRebuildThumbs"
        >
          <Icon name="image" :size="14" />
          <span>{{ $t("face.rebuildThumbs") }}</span>
        </button>
        <button
          class="ghost sm"
          :disabled="!canRecluster || reclusterPending"
          @click="onRecluster"
        >
          <Icon name="rotate-ccw" :size="14" />
          <span>{{ $t("face.recluster") }}</span>
        </button>
        <button
          class="primary sm"
          :disabled="!canScan || scanPending || statusInfo.scanning"
          @click="onScan"
        >
          <Icon name="scan-line" :size="14" />
          <span>{{
            statusInfo.scanning ? $t("face.scanRunning") : $t("face.scan")
          }}</span>
        </button>
      </div>
    </div>

    <section v-if="!faceFeatureEnabled" class="faces-empty">
      <Icon name="info" :size="20" />
      <h3>{{ $t("face.featureDisabledTitle") }}</h3>
      <p class="muted">{{ $t("face.featureDisabledHint") }}</p>
    </section>

    <template v-else>
      <section class="faces-stats">
        <div class="stat">
          <div class="stat-label">{{ $t("face.statPersons") }}</div>
          <div class="stat-value">{{ statusInfo.person_count }}</div>
        </div>
        <div class="stat">
          <div class="stat-label">{{ $t("face.statFaces") }}</div>
          <div class="stat-value">{{ statusInfo.face_count }}</div>
        </div>
        <div class="stat">
          <div class="stat-label">{{ $t("face.statLastRun") }}</div>
          <div class="stat-value">
            {{ formatTime(statusInfo.stats.last_run_at) }}
          </div>
        </div>
        <div class="stat">
          <div class="stat-label">{{ $t("face.statEngine") }}</div>
          <div class="stat-value">
            <span :class="['pill', statusInfo.engine_ready ? 'on' : 'off']">
              {{
                statusInfo.engine_ready
                  ? $t("face.engineReady")
                  : $t("face.engineNotReady")
              }}
            </span>
          </div>
        </div>
      </section>

      <section v-if="statusInfo.stats.last_error" class="faces-warning">
        <Icon name="info" :size="14" />
        <span>{{ statusInfo.stats.last_error }}</span>
      </section>

      <section class="faces-grid">
        <div
          v-for="person in persons"
          :key="person.id"
          class="face-card"
          :class="{
            active: selectedId === person.id,
            batch: selectedIds.has(person.id),
            named: !!person.name,
          }"
          @click="onSelectPerson(person, $event)"
          @contextmenu.prevent="onPersonContext($event, person)"
        >
          <div class="face-thumb">
            <img
              v-if="person.sample_face_id"
              :src="thumbUrl(person.sample_face_id)"
              :alt="person.name || ''"
              loading="lazy"
              @error="onThumbError($event)"
            />
            <div v-else class="face-thumb-placeholder">
              <Icon name="user" :size="40" />
            </div>
            <button
              class="plain face-card-check"
              type="button"
              :class="{ on: selectedIds.has(person.id) }"
              :title="$t('face.ctxSelect')"
              :aria-pressed="selectedIds.has(person.id) ? 'true' : 'false'"
              @click.stop="toggleSelect(person.id)"
            >
              <Icon name="check" :size="14" />
            </button>
            <span class="face-card-badge">
              {{ $t("face.faceCount", { count: person.face_count }) }}
            </span>
          </div>
          <div class="face-card-meta">
            <div class="face-card-name" :title="person.name || ''">
              {{ person.name || $t("face.unnamedPerson", { id: person.id }) }}
            </div>
            <div class="face-card-id muted">#{{ person.id }}</div>
          </div>
        </div>
        <div v-if="!persons.length && !loading" class="faces-empty">
          <Icon name="info" :size="20" />
          <h3>{{ $t("face.emptyTitle") }}</h3>
          <p class="muted">{{ $t("face.emptyHint") }}</p>
        </div>
      </section>

      <transition name="batchbar">
        <div v-if="selectedIds.size > 0" class="faces-batchbar">
          <div class="faces-batchbar-info">
            <Icon name="layers" :size="14" />
            <span>
              {{ $t("face.batchSelected", { count: selectedIds.size }) }}
            </span>
          </div>
          <div class="faces-batchbar-actions">
            <button
              class="primary sm"
              :disabled="selectedIds.size < 2"
              @click="onMergeBatch"
            >
              <Icon name="layers" :size="14" />
              <span>{{ $t("face.merge") }}</span>
            </button>
            <button class="ghost sm" @click="clearBatch">
              <Icon name="x" :size="14" />
              <span>{{ $t("face.clearSelection") }}</span>
            </button>
          </div>
        </div>
      </transition>
    </template>

    <FacePersonDrawer
      :visible="drawerVisible"
      :person="drawerPerson"
      :faces="drawerFaces"
      :readonly-token="auth.readonlyToken"
      @close="drawerVisible = false"
      @rename="onRename"
      @delete="onDelete"
      @split="onSplit"
      @merge-into="onMergeInto"
      @refresh="reloadAfterChange"
      @preview-media="onPreviewFromFace"
    />

    <PlayerModal
      :visible="previewVisible"
      :item="previewItem"
      :readonly-token="auth.readonlyToken"
      :can-navigate="previewList.length > 1"
      @close="closePreview"
      @next="shiftPreview(1)"
      @prev="shiftPreview(-1)"
      @copy-link="onCopyPreviewLink"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onBeforeUnmount, ref } from "vue";
import { useI18n } from "vue-i18n";
import Icon from "@/components/common/Icon.vue";
import FacePersonDrawer from "@/components/face/FacePersonDrawer.vue";
import PlayerModal from "@/components/media/PlayerModal.vue";
import { intelligenceApi } from "@/api/intelligence";
import type {
  FacePerson,
  FaceItem,
  FaceStatusResp,
} from "@/api/intelligence";
import { useAuthStore } from "@/stores/auth";
import { useConfigStore } from "@/stores/config";
import { useToastStore } from "@/stores/toast";
import { useConfirmStore } from "@/stores/confirm";
import { useUiStore } from "@/stores/ui";
import { useProgressStore } from "@/stores/progress";

const { t } = useI18n();
const auth = useAuthStore();
const config = useConfigStore();
const toast = useToastStore();
const confirm = useConfirmStore();
const ui = useUiStore();
const progressStore = useProgressStore();

const persons = ref<FacePerson[]>([]);
const selectedId = ref<number | null>(null);
const selectedIds = ref<Set<number>>(new Set());
const drawerVisible = ref(false);
const drawerPerson = ref<FacePerson | null>(null);
const drawerFaces = ref<FaceItem[]>([]);
const statusInfo = ref<FaceStatusResp>({
  engine_ready: false,
  face_count: 0,
  person_count: 0,
  scanning: false,
  stats: {},
});
const scanPending = ref(false);
const reclusterPending = ref(false);
const cleanupPending = ref(false);
const rebuildPending = ref(false);
const loading = ref(false);
let pollTimer: ReturnType<typeof setInterval> | null = null;

const faceFeatureEnabled = computed(() => config.canFaceBrowse);
const canScan = computed(
  () => faceFeatureEnabled.value && statusInfo.value.engine_ready,
);
const canRecluster = computed(
  () => faceFeatureEnabled.value && statusInfo.value.person_count > 0,
);

function thumbUrl(faceId: number): string {
  return intelligenceApi.faceThumbUrl(faceId, auth.readonlyToken);
}

function formatTime(ts?: number): string {
  if (!ts || !Number.isFinite(ts)) return "-";
  const d = new Date(ts * 1000);
  return d.toLocaleString();
}

function onThumbError(event: Event) {
  const img = event.target as HTMLImageElement;
  img.style.opacity = "0";
}

async function refreshPersons() {
  if (!faceFeatureEnabled.value) return;
  loading.value = true;
  try {
    const data = await intelligenceApi.faceListPersons();
    persons.value = data.persons || [];
  } catch (error) {
    toast.push((error as Error).message, "error");
  } finally {
    loading.value = false;
  }
}

async function refreshStatus() {
  if (!faceFeatureEnabled.value) return;
  try {
    statusInfo.value = await intelligenceApi.faceStatus();
  } catch (error) {
    // ignore
  }
}

function startPolling() {
  stopPolling();
  pollTimer = setInterval(async () => {
    await refreshStatus();
    if (statusInfo.value.scanning) return;
    if (
      statusInfo.value.stats.last_run_at &&
      lastSeenRunAt.value !== statusInfo.value.stats.last_run_at
    ) {
      lastSeenRunAt.value = statusInfo.value.stats.last_run_at;
      await refreshPersons();
    }
  }, 4000);
}

function stopPolling() {
  if (pollTimer) {
    clearInterval(pollTimer);
    pollTimer = null;
  }
}

const lastSeenRunAt = ref<number>(0);

async function onScan() {
  if (!canScan.value) return;
  scanPending.value = true;
  try {
    await intelligenceApi.faceScan();
    toast.push(t("face.scanQueued"), "success");
    progressStore.bump();
    await refreshStatus();
  } catch (error) {
    toast.push((error as Error).message, "error");
  } finally {
    scanPending.value = false;
  }
}

async function onCleanupOrphans() {
  if (!faceFeatureEnabled.value) return;
  const ok = await confirm.confirm({
    title: t("face.cleanupTitle"),
    message: t("face.cleanupConfirm"),
    confirmText: t("face.cleanupBtn"),
    tone: "danger",
    icon: "trash",
  });
  if (!ok) return;
  cleanupPending.value = true;
  try {
    const result = await intelligenceApi.faceCleanupOrphans();
    toast.push(
      t("face.cleanupDone", { count: result.removed }),
      "success",
    );
    await reloadAfterChange();
  } catch (error) {
    toast.push((error as Error).message, "error");
  } finally {
    cleanupPending.value = false;
  }
}

async function onRebuildThumbs() {
  if (!faceFeatureEnabled.value) return;
  const ok = await confirm.confirm({
    title: t("face.rebuildThumbsTitle"),
    message: t("face.rebuildThumbsConfirm"),
    confirmText: t("face.rebuildThumbsBtn"),
    tone: "warning",
    icon: "image",
  });
  if (!ok) return;
  rebuildPending.value = true;
  try {
    const result = await intelligenceApi.faceRebuildThumbs();
    toast.push(
      t("face.rebuildThumbsDone", {
        processed: result.processed,
        failed: result.failed,
      }),
      "success",
    );
    await reloadAfterChange();
  } catch (error) {
    toast.push((error as Error).message, "error");
  } finally {
    rebuildPending.value = false;
  }
}

async function onRecluster() {
  if (!canRecluster.value) return;
  const ok = await confirm.confirm({
    title: t("face.reclusterTitle"),
    message: t("face.reclusterConfirm"),
    confirmText: t("face.reclusterBtn"),
    tone: "warning",
    icon: "rotate-ccw",
  });
  if (!ok) return;
  reclusterPending.value = true;
  try {
    const report = await intelligenceApi.faceRecluster();
    toast.push(
      t("face.reclusterDone", {
        before: report.persons_before,
        after: report.persons_after,
      }),
      "success",
    );
    await reloadAfterChange();
  } catch (error) {
    toast.push((error as Error).message, "error");
  } finally {
    reclusterPending.value = false;
  }
}

async function reloadAfterChange() {
  await Promise.all([refreshPersons(), refreshStatus()]);
  if (selectedId.value) {
    await openPersonDetail(selectedId.value);
  }
}

interface PreviewMediaItem {
  id?: number;
  filename?: string;
  category?: string;
  kind?: string;
  size?: number;
  size_human?: string;
  rel_path?: string;
}

const previewVisible = ref(false);
const previewItem = ref<PreviewMediaItem | null>(null);
const previewList = ref<PreviewMediaItem[]>([]);

function faceToPreviewItem(face: FaceItem): PreviewMediaItem | null {
  const meta = face.media;
  if (!meta || !meta.filename || !meta.category) return null;
  return {
    id: meta.id,
    filename: meta.filename,
    category: meta.category,
    kind: meta.kind || "image",
    size: meta.size,
    size_human: meta.size_human,
    rel_path: meta.rel_path,
  };
}

function onPreviewFromFace(face: FaceItem) {
  const item = faceToPreviewItem(face);
  if (!item) {
    toast.push(t("face.drawer.previewUnavailable"), "warning");
    return;
  }
  const list: PreviewMediaItem[] = [];
  const seen = new Set<string>();
  for (const f of drawerFaces.value || []) {
    const candidate = faceToPreviewItem(f);
    if (!candidate) continue;
    const key = candidate.id != null ? `id:${candidate.id}` : `f:${candidate.category}|${candidate.filename}`;
    if (seen.has(key)) continue;
    seen.add(key);
    list.push(candidate);
  }
  previewList.value = list.length ? list : [item];
  previewItem.value = item;
  previewVisible.value = true;
}

function previewKey(item: PreviewMediaItem | null): string {
  if (!item) return "";
  if (item.id != null) return `id:${item.id}`;
  if (item.filename && item.category) return `f:${item.category}|${item.filename}`;
  return "";
}

function shiftPreview(delta: number) {
  if (!previewItem.value) return;
  const list = previewList.value || [];
  if (list.length < 2) return;
  const key = previewKey(previewItem.value);
  let idx = list.findIndex((entry) => previewKey(entry) === key);
  if (idx < 0) idx = 0;
  const next = list[(idx + delta + list.length) % list.length];
  if (next) previewItem.value = next;
}

function closePreview() {
  previewVisible.value = false;
}

async function onCopyPreviewLink(payload: { id?: string | number; url?: string }) {
  try {
    let link = "";
    if (payload && payload.url) {
      link = payload.url;
    } else if (previewItem.value && previewItem.value.category && previewItem.value.filename) {
      const token = auth.readonlyToken
        ? `?token=${encodeURIComponent(auth.readonlyToken)}`
        : "";
      link = `/files/${encodeURIComponent(previewItem.value.category)}/${encodeURIComponent(previewItem.value.filename)}${token}`;
    }
    if (!link) return;
    const absolute = new URL(link, window.location.origin).toString();
    await navigator.clipboard.writeText(absolute);
    toast.push(t("face.drawer.linkCopied"), "success");
  } catch (error) {
    toast.push((error as Error).message, "error");
  }
}

async function openPersonDetail(personId: number) {
  try {
    const data = await intelligenceApi.facePersonDetail(personId, 200, 0);
    drawerPerson.value = data.person;
    drawerFaces.value = data.faces || [];
    drawerVisible.value = true;
  } catch (error) {
    toast.push((error as Error).message, "error");
  }
}

async function onSelectPerson(person: FacePerson, event: MouseEvent) {
  if (event.shiftKey || event.metaKey || event.ctrlKey) {
    toggleSelect(person.id);
    return;
  }
  selectedId.value = person.id;
  await openPersonDetail(person.id);
}

function toggleSelect(personId: number) {
  const next = new Set(selectedIds.value);
  if (next.has(personId)) next.delete(personId);
  else next.add(personId);
  selectedIds.value = next;
}

function clearBatch() {
  selectedIds.value = new Set();
}

async function onRename(payload: { id: number; name: string }) {
  try {
    await intelligenceApi.facePersonRename(payload.id, payload.name);
    toast.push(t("face.renameDone"), "success");
    await reloadAfterChange();
  } catch (error) {
    toast.push((error as Error).message, "error");
  }
}

async function onDelete(personId: number) {
  const ok = await confirm.confirm({
    title: t("face.deletePersonTitle"),
    message: t("face.deletePersonConfirm"),
    confirmText: t("face.deletePersonBtn"),
    tone: "danger",
    icon: "trash-2",
  });
  if (!ok) return;
  try {
    await intelligenceApi.facePersonDelete(personId);
    toast.push(t("face.deletePersonDone"), "success");
    drawerVisible.value = false;
    await reloadAfterChange();
  } catch (error) {
    toast.push((error as Error).message, "error");
  }
}

async function onSplit(payload: { personId: number; faceIds: number[] }) {
  try {
    await intelligenceApi.facePersonSplit(payload.personId, payload.faceIds);
    toast.push(t("face.splitDone", { count: payload.faceIds.length }), "success");
    await reloadAfterChange();
  } catch (error) {
    toast.push((error as Error).message, "error");
  }
}

async function onMergeInto(payload: { sourceId: number; targetId: number }) {
  try {
    await intelligenceApi.facePersonsMerge(payload.targetId, [payload.sourceId]);
    toast.push(t("face.mergeDone", { count: 1 }), "success");
    drawerVisible.value = false;
    await reloadAfterChange();
  } catch (error) {
    toast.push((error as Error).message, "error");
  }
}

async function onMergeBatch() {
  if (selectedIds.value.size < 2) return;
  const ids = [...selectedIds.value];
  const target = ids[0];
  const sources = ids.slice(1);
  const ok = await confirm.confirm({
    title: t("face.mergeBatchTitle"),
    message: t("face.mergeBatchConfirm", { count: sources.length, target }),
    confirmText: t("face.mergeBatchBtn"),
    tone: "warning",
    icon: "layers",
  });
  if (!ok) return;
  try {
    await intelligenceApi.facePersonsMerge(target, sources);
    toast.push(t("face.mergeDone", { count: sources.length }), "success");
    selectedIds.value = new Set();
    await reloadAfterChange();
  } catch (error) {
    toast.push((error as Error).message, "error");
  }
}

function onPersonContext(event: MouseEvent, person: FacePerson) {
  ui.openContextMenu(
    event,
    [
      { key: "open", icon: "scan-line", label: t("face.ctxOpen") },
      { key: "select", icon: "check", label: t("face.ctxSelect") },
      { divider: true, key: `pd_${person.id}` },
      { key: "rename", icon: "pencil", label: t("face.ctxRename") },
      { key: "delete", icon: "trash-2", label: t("face.ctxDelete"), tone: "danger" },
    ],
    {
      kind: "face-person",
      item: person,
      onSelect(key: string) {
        ui.closeContextMenu();
        if (key === "open") {
          selectedId.value = person.id;
          openPersonDetail(person.id);
        } else if (key === "select") {
          toggleSelect(person.id);
        } else if (key === "rename") {
          renameWithPrompt(person);
        } else if (key === "delete") {
          onDelete(person.id);
        }
      },
    },
  );
}

async function renameWithPrompt(person: FacePerson) {
  const next = window.prompt(t("face.renamePromptLabel"), person.name || "");
  if (next === null) return;
  await onRename({ id: person.id, name: next.trim() });
}

onMounted(async () => {
  if (!faceFeatureEnabled.value) return;
  await Promise.all([refreshPersons(), refreshStatus()]);
  startPolling();
});

onBeforeUnmount(() => {
  stopPolling();
});
</script>

<style scoped>
.faces-view {
  display: flex;
  flex-direction: column;
  gap: 18px;
  padding: 18px 20px 80px;
}

.faces-toolbar {
  display: flex;
  flex-wrap: wrap;
  gap: 14px;
  align-items: flex-end;
  justify-content: space-between;
  padding: 16px 18px;
  border-radius: 14px;
  background: linear-gradient(
    135deg,
    color-mix(in srgb, var(--primary) 8%, var(--surface)) 0%,
    var(--surface) 60%
  );
  border: 1px solid var(--line);
}
.faces-toolbar-info h2 {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 0 0 6px;
  font-size: 20px;
  font-weight: 600;
  color: var(--text);
}
.faces-toolbar-info h2 :deep(svg) {
  color: var(--primary);
}
.faces-toolbar-info p {
  margin: 0;
  font-size: 13px;
}
.faces-toolbar-actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  align-items: center;
}

.faces-stats {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: 12px;
}
.stat {
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: 12px;
  padding: 14px 16px;
  display: flex;
  flex-direction: column;
  gap: 6px;
  transition: border-color 0.15s ease;
}
.stat:hover {
  border-color: color-mix(in srgb, var(--primary) 25%, var(--line));
}
.stat-label {
  font-size: 12px;
  color: var(--muted);
  letter-spacing: 0.02em;
}
.stat-value {
  font-size: 20px;
  font-weight: 600;
  word-break: break-all;
}
.pill {
  display: inline-flex;
  align-items: center;
  padding: 3px 10px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 500;
}
.pill.on {
  background: color-mix(in srgb, var(--success, #4ade80) 18%, transparent);
  color: color-mix(in srgb, var(--success, #4ade80) 90%, var(--text));
}
.pill.off {
  background: color-mix(in srgb, var(--muted) 18%, transparent);
  color: var(--muted);
}

.faces-warning {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 14px;
  border-radius: 10px;
  background: color-mix(in srgb, var(--warning, #facc15) 14%, transparent);
  color: color-mix(in srgb, var(--warning, #facc15) 80%, var(--text));
  font-size: 13px;
  border: 1px solid color-mix(in srgb, var(--warning, #facc15) 30%, transparent);
}

.faces-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(170px, 1fr));
  gap: 14px;
}

.face-card {
  position: relative;
  border-radius: 14px;
  overflow: hidden;
  cursor: pointer;
  background: var(--surface);
  border: 1px solid var(--line);
  transition: transform 0.15s ease, border-color 0.15s ease,
    box-shadow 0.15s ease;
}
.face-card:hover {
  border-color: color-mix(in srgb, var(--primary) 40%, var(--line));
  transform: translateY(-2px);
  box-shadow: 0 6px 18px rgba(0, 0, 0, 0.08);
}
.face-card.active {
  border-color: var(--primary);
  box-shadow: 0 0 0 2px color-mix(in srgb, var(--primary) 22%, transparent);
}
.face-card.batch {
  border-color: var(--primary);
  box-shadow: 0 0 0 2px color-mix(in srgb, var(--primary) 30%, transparent);
}
.face-card.named .face-card-name {
  color: var(--text);
}

.face-thumb {
  position: relative;
  aspect-ratio: 1;
  width: 100%;
  background:
    radial-gradient(
      circle at 50% 35%,
      color-mix(in srgb, var(--primary) 18%, transparent),
      color-mix(in srgb, var(--muted) 10%, transparent) 70%
    );
  overflow: hidden;
}
.face-thumb img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
  transition: transform 0.4s ease;
}
.face-card:hover .face-thumb img {
  transform: scale(1.04);
}
.face-thumb-placeholder {
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  color: color-mix(in srgb, var(--text) 35%, transparent);
}

.face-card-check {
  position: absolute;
  top: 8px;
  right: 8px;
  width: 28px;
  height: 28px;
  min-height: 28px;
  min-width: 28px;
  flex: none;
  border-radius: 50%;
  border: 1.5px solid rgba(255, 255, 255, 0.85);
  background: rgba(15, 23, 42, 0.45);
  color: rgba(255, 255, 255, 0.95);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  padding: 0;
  margin: 0;
  line-height: 1;
  box-sizing: border-box;
  backdrop-filter: blur(4px);
  -webkit-backdrop-filter: blur(4px);
  transition: background 0.15s ease, transform 0.15s ease,
    border-color 0.15s ease;
  z-index: 2;
  opacity: 0;
}
.face-card:hover .face-card-check,
.face-card.batch .face-card-check,
.face-card-check.on {
  opacity: 1;
}
.face-card-check.on {
  background: var(--primary);
  border-color: var(--primary);
  color: #fff;
}
.face-card-check:hover {
  transform: scale(1.08);
  border-color: #fff;
}
.face-card-check :deep(svg) {
  flex: none;
  display: block;
}

.face-card-badge {
  position: absolute;
  bottom: 8px;
  left: 8px;
  padding: 3px 8px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 500;
  background: rgba(15, 23, 42, 0.6);
  color: #fff;
  backdrop-filter: blur(6px);
}

.face-card-meta {
  padding: 10px 12px 12px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}
.face-card-name {
  font-weight: 500;
  font-size: 13.5px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  flex: 1;
  min-width: 0;
  color: var(--muted);
}
.face-card.named .face-card-name {
  color: var(--text);
}
.face-card-id {
  font-size: 11.5px;
  flex-shrink: 0;
  font-variant-numeric: tabular-nums;
}

.faces-empty {
  grid-column: 1 / -1;
  display: flex;
  flex-direction: column;
  gap: 8px;
  align-items: center;
  text-align: center;
  padding: 40px 16px;
  border: 1px dashed var(--line);
  border-radius: 14px;
  background: var(--surface);
  color: var(--muted);
}
.faces-empty h3 {
  margin: 4px 0 0;
  color: var(--text);
}

.faces-batchbar {
  position: sticky;
  bottom: 18px;
  margin: 0 auto;
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 10px 14px;
  background: color-mix(in srgb, var(--surface) 95%, transparent);
  border: 1px solid var(--line);
  border-radius: 999px;
  box-shadow:
    0 12px 32px rgba(0, 0, 0, 0.18),
    0 2px 8px rgba(0, 0, 0, 0.08);
  backdrop-filter: blur(12px);
  font-size: 13px;
  z-index: 5;
  max-width: 90%;
}
.faces-batchbar-info {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-weight: 500;
  color: var(--text);
}
.faces-batchbar-actions {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.batchbar-enter-from,
.batchbar-leave-to {
  opacity: 0;
  transform: translateY(8px);
}
.batchbar-enter-active,
.batchbar-leave-active {
  transition: opacity 0.18s ease, transform 0.18s ease;
}
</style>

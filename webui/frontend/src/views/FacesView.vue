<template>
  <div class="faces-view">
    <div class="faces-toolbar">
      <div class="faces-toolbar-info">
        <h2>{{ $t("face.title") }}</h2>
        <p class="muted">{{ $t("face.subtitle") }}</p>
      </div>
      <div class="faces-toolbar-actions">
        <button
          class="ghost"
          :disabled="!canRecluster || reclusterPending"
          @click="onRecluster"
        >
          <Icon name="rotate-ccw" :size="14" />
          {{ $t("face.recluster") }}
        </button>
        <button
          class="primary"
          :disabled="!canScan || scanPending || statusInfo.scanning"
          @click="onScan"
        >
          <Icon name="scan-line" :size="14" />
          {{ statusInfo.scanning ? $t("face.scanRunning") : $t("face.scan") }}
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
          :class="{ active: selectedId === person.id, batch: selectedIds.has(person.id) }"
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
              <Icon name="image" :size="24" />
            </div>
          </div>
          <div class="face-card-meta">
            <div class="face-card-name">
              {{ person.name || $t("face.unnamedPerson", { id: person.id }) }}
            </div>
            <div class="face-card-count">
              {{ $t("face.faceCount", { count: person.face_count }) }}
            </div>
          </div>
          <input
            class="face-card-check"
            type="checkbox"
            :checked="selectedIds.has(person.id)"
            @click.stop="toggleSelect(person.id)"
            @change.stop
          />
        </div>
        <div v-if="!persons.length && !loading" class="faces-empty">
          <Icon name="info" :size="20" />
          <h3>{{ $t("face.emptyTitle") }}</h3>
          <p class="muted">{{ $t("face.emptyHint") }}</p>
        </div>
      </section>

      <div v-if="selectedIds.size > 1" class="faces-batchbar">
        <span>
          {{ $t("face.batchSelected", { count: selectedIds.size }) }}
        </span>
        <button class="ghost" @click="onMergeBatch">
          <Icon name="layers" :size="14" />
          {{ $t("face.merge") }}
        </button>
        <button class="ghost" @click="clearBatch">
          {{ $t("face.clearSelection") }}
        </button>
      </div>
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
    />
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onBeforeUnmount, ref } from "vue";
import { useI18n } from "vue-i18n";
import Icon from "@/components/common/Icon.vue";
import FacePersonDrawer from "@/components/face/FacePersonDrawer.vue";
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

const { t } = useI18n();
const auth = useAuthStore();
const config = useConfigStore();
const toast = useToastStore();
const confirm = useConfirmStore();
const ui = useUiStore();

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
    await refreshStatus();
  } catch (error) {
    toast.push((error as Error).message, "error");
  } finally {
    scanPending.value = false;
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
  gap: 16px;
  padding: 16px 18px 30px;
}

.faces-toolbar {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  align-items: flex-end;
  justify-content: space-between;
}
.faces-toolbar h2 {
  margin: 0 0 4px;
  font-size: 18px;
}
.faces-toolbar-actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.faces-stats {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
  gap: 10px;
}
.stat {
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: 10px;
  padding: 10px 12px;
}
.stat-label {
  font-size: 12px;
  color: var(--muted);
  margin-bottom: 4px;
}
.stat-value {
  font-size: 16px;
  font-weight: 500;
  word-break: break-all;
}
.pill {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 999px;
  font-size: 12px;
}
.pill.on {
  background: color-mix(in srgb, var(--success, #4ade80) 16%, transparent);
  color: color-mix(in srgb, var(--success, #4ade80) 90%, var(--text));
}
.pill.off {
  background: color-mix(in srgb, var(--muted) 18%, transparent);
  color: var(--muted);
}

.faces-warning {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 12px;
  border-radius: 8px;
  background: color-mix(in srgb, var(--warning, #facc15) 14%, transparent);
  color: color-mix(in srgb, var(--warning, #facc15) 80%, var(--text));
  font-size: 13px;
}

.faces-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(160px, 1fr));
  gap: 12px;
}

.face-card {
  position: relative;
  border-radius: 12px;
  overflow: hidden;
  cursor: pointer;
  background: var(--surface);
  border: 1px solid var(--line);
  transition: transform 0.12s ease, border-color 0.12s ease;
}
.face-card:hover {
  border-color: color-mix(in srgb, var(--primary) 35%, var(--line));
  transform: translateY(-1px);
}
.face-card.active {
  border-color: var(--primary);
}
.face-card.batch {
  border-color: color-mix(in srgb, var(--primary) 60%, var(--line));
  box-shadow: 0 0 0 2px color-mix(in srgb, var(--primary) 25%, transparent);
}

.face-thumb {
  aspect-ratio: 1;
  width: 100%;
  background: color-mix(in srgb, var(--muted) 8%, transparent);
  display: flex;
  align-items: center;
  justify-content: center;
}
.face-thumb img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}
.face-thumb-placeholder {
  color: var(--muted);
}

.face-card-meta {
  padding: 8px 10px;
}
.face-card-name {
  font-weight: 500;
  font-size: 13px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.face-card-count {
  font-size: 12px;
  color: var(--muted);
}
.face-card-check {
  position: absolute;
  top: 8px;
  right: 8px;
  margin: 0;
  width: 16px;
  height: 16px;
  cursor: pointer;
  z-index: 2;
}

.faces-empty {
  display: flex;
  flex-direction: column;
  gap: 6px;
  align-items: center;
  text-align: center;
  padding: 30px 12px;
  border: 1px dashed var(--line);
  border-radius: 12px;
  background: var(--surface);
}
.faces-empty h3 {
  margin: 4px 0 0;
}

.faces-batchbar {
  position: sticky;
  bottom: 12px;
  align-self: center;
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: 999px;
  box-shadow: 0 6px 24px rgba(0, 0, 0, 0.12);
  font-size: 13px;
}
</style>

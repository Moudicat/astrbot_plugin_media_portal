<template>
  <section class="settings-section intelligence-section">
    <h4>{{ $t("settings.intelligence.title") }}</h4>

    <ul class="settings-toggle-list intel-master-toggle">
      <li
        class="settings-toggle"
        :class="{ disabled: !featureToggle }"
        role="switch"
        :aria-checked="featureToggle ? 'true' : 'false'"
        :aria-disabled="busy ? 'true' : 'false'"
        @click="onFeatureToggle"
      >
        <div class="settings-toggle-icon">
          <Icon name="cpu" :size="14" />
        </div>
        <div class="settings-toggle-body">
          <span class="settings-toggle-title">
            {{ $t("settings.intelligence.featureLabel") }}
          </span>
          <span class="settings-toggle-desc">
            {{ $t("settings.intelligence.featureHint") }}
          </span>
        </div>
        <span
          class="switch"
          :class="{ on: featureToggle }"
          role="presentation"
        ></span>
      </li>
    </ul>

    <div class="settings-row">
      <div class="label">
        <strong>{{ $t("settings.intelligence.mirrorLabel") }}</strong>
        <small>{{ $t("settings.intelligence.mirrorHint") }}</small>
      </div>
      <div class="settings-actions-row">
        <input
          v-model="mirrorDraft"
          type="text"
          :placeholder="defaultMirrorPlaceholder"
          style="min-width: 240px"
          :disabled="busy"
        />
        <button class="ghost" :disabled="busy" @click="saveMirror">
          <Icon name="save" :size="14" />
          <span>{{ $t("common.save") }}</span>
        </button>
      </div>
    </div>

    <div v-if="!list?.feature_enabled" class="totp-banner muted">
      <Icon name="info" :size="14" />
      <span>{{ $t("settings.intelligence.featureBannerOff") }}</span>
    </div>

    <ul class="intel-models" v-else>
      <li
        v-for="model in list.models"
        :key="model.key"
        class="intel-model"
        :class="model.capability"
      >
        <div class="intel-model-head">
          <div class="intel-model-title">
            <span class="intel-model-tag" :class="model.capability">
              {{
                model.capability === "clip"
                  ? $t("settings.intelligence.tagClip")
                  : $t("settings.intelligence.tagFace")
              }}
            </span>
            <strong>{{ model.display_name }}</strong>
          </div>
          <span class="intel-status-pill" :class="model.status">
            {{ statusLabel(model.status) }}
          </span>
        </div>

        <p class="muted small intel-model-desc">{{ model.description }}</p>

        <div
          class="intel-toggle-row"
          :class="{ disabled: !capabilityToggle(model.capability) }"
          role="switch"
          :aria-checked="capabilityToggle(model.capability) ? 'true' : 'false'"
          :aria-disabled="busy || !list.feature_enabled ? 'true' : 'false'"
          @click="
            !busy &&
              list.feature_enabled &&
              onCapabilityToggle(
                model.capability,
                !capabilityToggle(model.capability),
              )
          "
        >
          <div class="intel-toggle-body">
            <span class="intel-toggle-title">
              {{ $t("settings.intelligence.enableCapability") }}
            </span>
            <span class="intel-toggle-desc muted small">
              {{ $t("settings.intelligence.enableCapabilityHint") }}
            </span>
          </div>
          <span
            class="switch"
            :class="{ on: capabilityToggle(model.capability) }"
            role="presentation"
          ></span>
        </div>

        <div v-if="model.last_error" class="intel-error">
          <Icon name="alert-triangle" :size="13" />
          <span>{{ model.last_error }}</span>
        </div>

        <div v-if="model.status === 'downloading'" class="intel-progress">
          <div class="intel-progress-bar">
            <div
              class="intel-progress-fill"
              :style="{ width: `${progressPercent(model)}%` }"
            ></div>
          </div>
          <small class="muted">{{ progressText(model) }}</small>
        </div>

        <div class="intel-actions">
          <button
            v-if="model.status !== 'ready' && model.status !== 'downloading'"
            class="primary sm"
            :disabled="busy"
            @click="downloadOne(model.key)"
          >
            <Icon name="download" :size="14" />
            <span>{{ $t("settings.intelligence.download") }}</span>
          </button>
          <button
            v-if="model.status === 'downloading'"
            class="ghost sm"
            :disabled="busy"
            @click="cancelOne(model.key)"
          >
            <Icon name="x" :size="14" />
            <span>{{ $t("settings.intelligence.cancel") }}</span>
          </button>
          <button
            v-if="model.status === 'ready' || model.status === 'partial'"
            class="ghost sm danger"
            :disabled="busy"
            @click="removeOne(model.key)"
          >
            <Icon name="trash" :size="14" />
            <span>{{ $t("settings.intelligence.remove") }}</span>
          </button>
          <a
            v-if="model.homepage"
            class="intel-homepage-link muted small"
            :href="model.homepage"
            target="_blank"
            rel="noopener"
          >
            <Icon name="external-link" :size="12" />
            <span>{{ $t("settings.intelligence.homepage") }}</span>
          </a>
        </div>
      </li>
    </ul>

    <div v-if="clipReady" class="intel-clip-panel">
      <div class="settings-row">
        <div class="label">
          <strong>{{ $t("settings.intelligence.clipIndexLabel") }}</strong>
          <small>
            {{
              $t("settings.intelligence.clipIndexHint", {
                count: clipStatus?.indexed_count ?? 0,
              })
            }}
          </small>
        </div>
        <div class="settings-actions-row">
          <button
            class="primary"
            :disabled="busy || clipStatus?.scanning"
            @click="onScan"
          >
            <Icon name="scan-line" :size="14" />
            <span>{{
              clipStatus?.scanning
                ? $t("settings.intelligence.clipScanning")
                : $t("settings.intelligence.clipScan")
            }}</span>
          </button>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from "vue";
import { useI18n } from "vue-i18n";
import Icon from "@/components/common/Icon.vue";
import { useToastStore } from "@/stores/toast";
import { useConfigStore } from "@/stores/config";
import {
  intelligenceApi,
  type IntelligenceListResp,
  type ModelSnapshot,
  type ModelStatus,
  type ClipStatusResp,
} from "@/api/intelligence";

const { t } = useI18n();
const toast = useToastStore();
const configStore = useConfigStore();

const busy = ref(false);
const list = ref<IntelligenceListResp | null>(null);
const clipStatus = ref<ClipStatusResp | null>(null);
const featureToggle = ref(false);
const mirrorDraft = ref("");

let pollTimer: ReturnType<typeof setTimeout> | null = null;

const defaultMirrorPlaceholder = "https://hf-mirror.com";

const clipReady = computed(() => {
  if (!list.value) return false;
  const clip = list.value.models.find((m) => m.capability === "clip");
  return list.value.feature_enabled && list.value.clip_enabled && clip?.status === "ready";
});

onMounted(async () => {
  await refresh();
  scheduleRefresh();
});

onUnmounted(() => {
  if (pollTimer) {
    clearTimeout(pollTimer);
    pollTimer = null;
  }
});

function scheduleRefresh() {
  if (pollTimer) clearTimeout(pollTimer);
  pollTimer = setTimeout(async () => {
    await refresh().catch(() => undefined);
    scheduleRefresh();
  }, 2500);
}

async function refresh() {
  try {
    const data = await intelligenceApi.listModels();
    list.value = data;
    featureToggle.value = data.feature_enabled;
    if (mirrorDraft.value === "") mirrorDraft.value = data.hf_mirror_url || "";
    if (data.clip_enabled) {
      const status = await intelligenceApi.clipStatus().catch(() => null);
      clipStatus.value = status;
    } else {
      clipStatus.value = null;
    }
  } catch (error) {
    toast.push((error as Error).message, "error");
  }
}

function capabilityToggle(capability: "clip" | "face") {
  if (!list.value) return false;
  return capability === "clip"
    ? list.value.clip_enabled
    : list.value.face_enabled;
}

async function onCapabilityToggle(capability: "clip" | "face", value: boolean) {
  await patch({ [`${capability}_enabled`]: value });
}

async function onFeatureToggle() {
  if (busy.value) return;
  const next = !featureToggle.value;
  featureToggle.value = next;
  await patch({ feature_enabled: next });
}

async function patch(payload: Record<string, unknown>) {
  busy.value = true;
  try {
    await intelligenceApi.patchSettings(payload);
    await refresh();
    await configStore.fetch().catch(() => undefined);
    toast.push(t("settings.intelligence.saved"), "success");
  } catch (error) {
    toast.push((error as Error).message, "error");
  } finally {
    busy.value = false;
  }
}

async function saveMirror() {
  await patch({ hf_mirror_url: mirrorDraft.value.trim() });
}

async function downloadOne(key: string) {
  busy.value = true;
  try {
    await intelligenceApi.startDownload(key);
    toast.push(t("settings.intelligence.downloadStarted"), "success");
    await refresh();
  } catch (error) {
    toast.push((error as Error).message, "error");
  } finally {
    busy.value = false;
  }
}

async function cancelOne(key: string) {
  busy.value = true;
  try {
    await intelligenceApi.cancelDownload(key);
    toast.push(t("settings.intelligence.downloadCancelled"), "success");
    await refresh();
  } catch (error) {
    toast.push((error as Error).message, "error");
  } finally {
    busy.value = false;
  }
}

async function removeOne(key: string) {
  if (!window.confirm(t("settings.intelligence.removeConfirm"))) return;
  busy.value = true;
  try {
    await intelligenceApi.removeModel(key);
    toast.push(t("settings.intelligence.removed"), "success");
    await refresh();
  } catch (error) {
    toast.push((error as Error).message, "error");
  } finally {
    busy.value = false;
  }
}

async function onScan() {
  busy.value = true;
  try {
    const result = await intelligenceApi.clipScan();
    if (!result.started) {
      toast.push(t("settings.intelligence.clipScanBusy"), "info");
    } else {
      toast.push(t("settings.intelligence.clipScanStarted"), "success");
    }
    await refresh();
  } catch (error) {
    toast.push((error as Error).message, "error");
  } finally {
    busy.value = false;
  }
}

function statusLabel(status: ModelStatus): string {
  switch (status) {
    case "ready":
      return t("settings.intelligence.statusReady");
    case "downloading":
      return t("settings.intelligence.statusDownloading");
    case "partial":
      return t("settings.intelligence.statusPartial");
    case "failed":
      return t("settings.intelligence.statusFailed");
    case "cancelled":
      return t("settings.intelligence.statusCancelled");
    case "corrupted":
      return t("settings.intelligence.statusCorrupted");
    default:
      return t("settings.intelligence.statusNotDownloaded");
  }
}

function progressPercent(m: ModelSnapshot) {
  if (!m.progress_total || m.progress_total <= 0) return 0;
  return Math.min(100, Math.round((m.progress_bytes / m.progress_total) * 100));
}

function progressText(m: ModelSnapshot) {
  if (m.progress_total) {
    return `${formatBytes(m.progress_bytes)} / ${formatBytes(m.progress_total)} · ${m.current_file}`;
  }
  return `${formatBytes(m.progress_bytes)} · ${m.current_file}`;
}

function formatBytes(bytes: number) {
  if (!bytes || bytes <= 0) return "0 B";
  const units = ["B", "KB", "MB", "GB"];
  let value = bytes;
  let i = 0;
  while (value >= 1024 && i < units.length - 1) {
    value /= 1024;
    i += 1;
  }
  return `${value.toFixed(value < 10 && i > 0 ? 2 : 0)} ${units[i]}`;
}
</script>

<style scoped>
.intel-master-toggle {
  margin: 4px 0 12px;
  grid-template-columns: 1fr;
}

.intel-master-toggle .settings-toggle-title {
  font-size: 14px;
}

.intel-master-toggle .settings-toggle-desc {
  white-space: normal;
  line-height: 1.45;
}

.intel-models {
  list-style: none;
  margin: 4px 0 0;
  padding: 0;
  display: grid;
  gap: 12px;
}

.intel-model {
  border: 1px solid var(--border, rgba(0, 0, 0, 0.08));
  border-radius: 12px;
  padding: 14px 16px;
  background: var(--surface, rgba(255, 255, 255, 0.4));
  display: grid;
  gap: 10px;
}

.intel-model-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 10px;
}

.intel-model-title {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.intel-model-title strong {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.intel-model-tag {
  display: inline-flex;
  align-items: center;
  padding: 2px 8px;
  border-radius: 999px;
  font-size: 11px;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  background: rgba(99, 102, 241, 0.12);
  color: #4f46e5;
  flex-shrink: 0;
}

.intel-model-tag.face {
  background: rgba(236, 72, 153, 0.12);
  color: #db2777;
}

.intel-status-pill {
  font-size: 12px;
  padding: 2px 8px;
  border-radius: 999px;
  background: rgba(148, 163, 184, 0.18);
  flex-shrink: 0;
}

.intel-status-pill.ready {
  background: rgba(34, 197, 94, 0.16);
  color: #15803d;
}

.intel-status-pill.downloading {
  background: rgba(59, 130, 246, 0.18);
  color: #1d4ed8;
}

.intel-status-pill.failed,
.intel-status-pill.corrupted {
  background: rgba(239, 68, 68, 0.16);
  color: #b91c1c;
}

.intel-model-desc {
  margin: 0;
}

.intel-toggle-row {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 12px;
  border-radius: 10px;
  background: var(--surface-2, rgba(15, 23, 42, 0.04));
  border: 1px solid var(--border, rgba(0, 0, 0, 0.06));
  cursor: pointer;
  transition: background var(--transition-fast, 0.15s ease),
    border-color var(--transition-fast, 0.15s ease);
}

.intel-toggle-row:hover:not(.disabled) {
  background: var(--surface-strong, rgba(15, 23, 42, 0.06));
}

.intel-toggle-row[aria-disabled="true"] {
  cursor: not-allowed;
  opacity: 0.55;
}

.intel-toggle-body {
  display: flex;
  flex-direction: column;
  gap: 2px;
  flex: 1;
  min-width: 0;
}

.intel-toggle-title {
  font-weight: 600;
  font-size: 13.5px;
  color: var(--text, inherit);
}

.intel-toggle-desc {
  font-size: 12px;
  line-height: 1.45;
}

.intel-error {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 10px;
  border-radius: 8px;
  background: rgba(239, 68, 68, 0.08);
  color: #b91c1c;
  font-size: 12px;
}

.intel-progress {
  display: grid;
  gap: 4px;
}

.intel-progress-bar {
  height: 6px;
  border-radius: 999px;
  background: rgba(148, 163, 184, 0.25);
  overflow: hidden;
}

.intel-progress-fill {
  height: 100%;
  background: var(--primary, #6366f1);
  transition: width 0.4s ease;
}

.intel-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
}

.intel-homepage-link {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  margin-left: auto;
  text-decoration: none;
}

.intel-homepage-link:hover {
  color: var(--primary, #6366f1);
}

.intel-clip-panel {
  margin-top: 14px;
  border-top: 1px dashed var(--border, rgba(0, 0, 0, 0.08));
  padding-top: 12px;
}
</style>

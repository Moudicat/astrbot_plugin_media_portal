<template>
  <section class="settings-section intelligence-section">
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

    <div class="settings-row intel-mirror-row">
      <div class="label">
        <strong>{{ $t("settings.intelligence.mirrorLabel") }}</strong>
        <small>{{ $t("settings.intelligence.mirrorHint") }}</small>
      </div>
      <div class="settings-actions-row intel-mirror-actions">
        <input
          v-model="mirrorDraft"
          type="text"
          :placeholder="defaultMirrorPlaceholder"
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
            <div class="intel-model-name">
              <strong>{{ friendlyName(model.capability) }}</strong>
              <span
                class="intel-model-tech muted small"
                :title="
                  $t('settings.intelligence.modelTechId', {
                    name: model.display_name,
                  })
                "
              >
                {{ model.display_name }}
              </span>
            </div>
          </div>
          <span class="intel-status-pill" :class="model.status">
            {{ statusLabel(model) }}
          </span>
        </div>

        <p class="muted small intel-model-desc">
          {{ friendlyDescription(model.capability) }}
        </p>

        <div
          v-if="hasMissingDeps(model)"
          class="intel-deps-warning"
          role="alert"
        >
          <Icon name="alert-triangle" :size="13" />
          <div class="intel-deps-warning-body">
            <strong>{{
              $t("settings.intelligence.missingDepsTitle", {
                count: model.missing_deps.length,
              })
            }}</strong>
            <span class="muted small intel-deps-warning-list">
              {{ formatMissingDeps(model) }}
            </span>
          </div>
        </div>

        <div
          class="intel-toggle-row"
          :class="{
            disabled: !capabilityToggle(model.capability),
            'not-ready': !isModelReady(model),
          }"
          role="switch"
          :aria-checked="capabilityToggle(model.capability) ? 'true' : 'false'"
          :aria-disabled="
            busy || !list.feature_enabled || !isModelReady(model)
              ? 'true'
              : 'false'
          "
          @click="
            !busy &&
              list.feature_enabled &&
              isModelReady(model) &&
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
              {{
                isModelReady(model)
                  ? $t("settings.intelligence.enableCapabilityHint")
                  : $t("settings.intelligence.enableCapabilityNeedDownload")
              }}
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
          <template v-if="model.phase === 'installing_deps'">
            <div class="intel-progress-bar indeterminate">
              <div class="intel-progress-fill"></div>
            </div>
            <small class="muted intel-deps-text">
              <Icon name="loader-2" :size="12" class="spin" />
              <span>{{ depsInstallText(model) }}</span>
            </small>
          </template>
          <template v-else-if="model.phase === 'checking_deps'">
            <div class="intel-progress-bar indeterminate">
              <div class="intel-progress-fill"></div>
            </div>
            <small class="muted intel-deps-text">
              <Icon name="loader-2" :size="12" class="spin" />
              <span>{{ $t("settings.intelligence.depsChecking") }}</span>
            </small>
          </template>
          <template v-else>
            <div class="intel-progress-bar">
              <div
                class="intel-progress-fill"
                :style="{ width: `${progressPercent(model)}%` }"
              ></div>
            </div>
            <small class="muted">{{ progressText(model) }}</small>
          </template>
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
            v-if="model.status === 'ready' && hasMissingDeps(model)"
            class="primary sm"
            :disabled="busy"
            @click="installDepsOne(model.key)"
          >
            <Icon name="package-plus" :size="14" />
            <span>{{ $t("settings.intelligence.installDeps") }}</span>
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

    <div v-if="faceReady" class="intel-face-panel">
      <h5 class="intel-face-title">
        <Icon name="sliders-horizontal" :size="14" />
        <span>{{ $t("settings.intelligence.faceQualityLabel") }}</span>
      </h5>
      <p class="muted small intel-face-hint">
        {{ $t("settings.intelligence.faceQualityHint") }}
      </p>

      <div class="intel-face-grid">
        <label class="intel-face-field">
          <span class="intel-face-field-label">
            {{ $t("settings.intelligence.faceMinDetScore") }}
          </span>
          <input
            type="number"
            min="0"
            max="1"
            step="0.05"
            v-model.number="faceQualityDraft.min_det_score"
            :disabled="busy"
          />
          <small class="muted">
            {{ $t("settings.intelligence.faceMinDetScoreHint") }}
          </small>
        </label>

        <label class="intel-face-field">
          <span class="intel-face-field-label">
            {{ $t("settings.intelligence.faceMinFaceSize") }}
          </span>
          <input
            type="number"
            min="0"
            step="10"
            v-model.number="faceQualityDraft.min_face_size"
            :disabled="busy"
          />
          <small class="muted">
            {{ $t("settings.intelligence.faceMinFaceSizeHint") }}
          </small>
        </label>

        <label class="intel-face-field">
          <span class="intel-face-field-label">
            {{ $t("settings.intelligence.faceMinBlurVar") }}
          </span>
          <input
            type="number"
            min="0"
            step="10"
            v-model.number="faceQualityDraft.min_blur_var"
            :disabled="busy"
          />
          <small class="muted">
            {{ $t("settings.intelligence.faceMinBlurVarHint") }}
          </small>
        </label>
      </div>

      <div class="intel-face-actions">
        <button class="ghost sm" :disabled="busy" @click="resetFaceQuality">
          <Icon name="rotate-ccw" :size="14" />
          <span>{{ $t("settings.intelligence.faceQualityReset") }}</span>
        </button>
        <button class="primary sm" :disabled="busy" @click="saveFaceQuality">
          <Icon name="save" :size="14" />
          <span>{{ $t("settings.intelligence.faceQualitySave") }}</span>
        </button>
        <button
          class="ghost sm danger"
          :disabled="busy"
          @click="prunePoorFaces"
          :title="$t('settings.intelligence.facePruneHint')"
        >
          <Icon name="filter" :size="14" />
          <span>{{ $t("settings.intelligence.facePrune") }}</span>
        </button>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, reactive, ref } from "vue";
import { useI18n } from "vue-i18n";
import Icon from "@/components/common/Icon.vue";
import { useToastStore } from "@/stores/toast";
import { useConfigStore } from "@/stores/config";
import { useProgressStore } from "@/stores/progress";
import {
  intelligenceApi,
  type IntelligenceListResp,
  type ModelSnapshot,
  type ClipStatusResp,
} from "@/api/intelligence";

const { t } = useI18n();
const toast = useToastStore();
const configStore = useConfigStore();
const progressStore = useProgressStore();

const FACE_QUALITY_DEFAULTS = {
  min_det_score: 0.6,
  min_face_size: 60,
  min_blur_var: 60,
};

const busy = ref(false);
const list = ref<IntelligenceListResp | null>(null);
const clipStatus = ref<ClipStatusResp | null>(null);
const featureToggle = ref(false);
const mirrorDraft = ref("");
const faceQualityDraft = reactive({ ...FACE_QUALITY_DEFAULTS });
const faceQualityDirty = ref(false);

let pollTimer: ReturnType<typeof setTimeout> | null = null;

const defaultMirrorPlaceholder = "https://hf-mirror.com";

const clipReady = computed(() => {
  if (!list.value) return false;
  const clip = list.value.models.find((m) => m.capability === "clip");
  return list.value.feature_enabled && list.value.clip_enabled && clip?.status === "ready";
});

const faceReady = computed(() => {
  if (!list.value) return false;
  const face = list.value.models.find((m) => m.capability === "face");
  return (
    list.value.feature_enabled &&
    list.value.face_enabled &&
    face?.status === "ready"
  );
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
    if (data.face_quality && !faceQualityDirty.value) {
      faceQualityDraft.min_det_score = roundFloat(
        data.face_quality.min_det_score ?? FACE_QUALITY_DEFAULTS.min_det_score,
        2,
      );
      faceQualityDraft.min_face_size = Math.max(
        0,
        Math.round(
          data.face_quality.min_face_size ?? FACE_QUALITY_DEFAULTS.min_face_size,
        ),
      );
      faceQualityDraft.min_blur_var = roundFloat(
        data.face_quality.min_blur_var ?? FACE_QUALITY_DEFAULTS.min_blur_var,
        1,
      );
    }
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

function roundFloat(value: number, digits: number): number {
  if (typeof value !== "number" || Number.isNaN(value)) return 0;
  const factor = Math.pow(10, digits);
  return Math.round(value * factor) / factor;
}

function capabilityToggle(capability: "clip" | "face") {
  if (!list.value) return false;
  return capability === "clip"
    ? list.value.clip_enabled
    : list.value.face_enabled;
}

function friendlyName(capability: "clip" | "face") {
  return capability === "clip"
    ? t("settings.intelligence.clipFriendlyName")
    : t("settings.intelligence.faceFriendlyName");
}

function friendlyDescription(capability: "clip" | "face") {
  return capability === "clip"
    ? t("settings.intelligence.clipFriendlyDesc")
    : t("settings.intelligence.faceFriendlyDesc");
}

function isModelReady(model: ModelSnapshot) {
  return model.status === "ready";
}

function hasMissingDeps(model: ModelSnapshot): boolean {
  return Array.isArray(model.missing_deps) && model.missing_deps.length > 0;
}

function formatMissingDeps(model: ModelSnapshot): string {
  const list = Array.isArray(model.missing_deps) ? model.missing_deps : [];
  return list.join("、");
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
    progressStore.bump();
    await refresh();
  } catch (error) {
    toast.push((error as Error).message, "error");
  } finally {
    busy.value = false;
  }
}

async function installDepsOne(key: string) {
  busy.value = true;
  try {
    await intelligenceApi.startDownload(key);
    toast.push(t("settings.intelligence.installDepsStarted"), "success");
    progressStore.bump();
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
    progressStore.bump();
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
      progressStore.bump();
    }
    await refresh();
  } catch (error) {
    toast.push((error as Error).message, "error");
  } finally {
    busy.value = false;
  }
}

function clampFaceQuality() {
  const score = Number(faceQualityDraft.min_det_score);
  faceQualityDraft.min_det_score = roundFloat(
    Math.min(1, Math.max(0, Number.isFinite(score) ? score : FACE_QUALITY_DEFAULTS.min_det_score)),
    2,
  );
  const size = Number(faceQualityDraft.min_face_size);
  faceQualityDraft.min_face_size = Math.max(
    0,
    Math.round(Number.isFinite(size) ? size : FACE_QUALITY_DEFAULTS.min_face_size),
  );
  const blur = Number(faceQualityDraft.min_blur_var);
  faceQualityDraft.min_blur_var = roundFloat(
    Math.max(0, Number.isFinite(blur) ? blur : FACE_QUALITY_DEFAULTS.min_blur_var),
    1,
  );
}

async function saveFaceQuality() {
  clampFaceQuality();
  faceQualityDirty.value = true;
  await patch({
    face_min_det_score: faceQualityDraft.min_det_score,
    face_min_face_size: faceQualityDraft.min_face_size,
    face_min_blur_var: faceQualityDraft.min_blur_var,
  });
  faceQualityDirty.value = false;
}

function resetFaceQuality() {
  Object.assign(faceQualityDraft, FACE_QUALITY_DEFAULTS);
  faceQualityDirty.value = true;
}

async function prunePoorFaces() {
  clampFaceQuality();
  if (
    !window.confirm(
      t("settings.intelligence.facePruneConfirm", {
        score: faceQualityDraft.min_det_score,
        size: faceQualityDraft.min_face_size,
        blur: faceQualityDraft.min_blur_var,
      }),
    )
  ) {
    return;
  }
  busy.value = true;
  try {
    await intelligenceApi.patchSettings({
      face_min_det_score: faceQualityDraft.min_det_score,
      face_min_face_size: faceQualityDraft.min_face_size,
      face_min_blur_var: faceQualityDraft.min_blur_var,
    });
    const result = await intelligenceApi.facePrune({
      min_det_score: faceQualityDraft.min_det_score,
      min_face_size: faceQualityDraft.min_face_size,
      min_blur_var: faceQualityDraft.min_blur_var,
    });
    faceQualityDirty.value = false;
    toast.push(
      t("settings.intelligence.facePruneDone", { count: result.removed }),
      "success",
    );
    await refresh();
  } catch (error) {
    toast.push((error as Error).message, "error");
  } finally {
    busy.value = false;
  }
}

function statusLabel(model: ModelSnapshot): string {
  if (model.status === "downloading") {
    if (model.phase === "installing_deps") {
      return t("settings.intelligence.statusInstallingDeps");
    }
    if (model.phase === "checking_deps") {
      return t("settings.intelligence.statusCheckingDeps");
    }
    return t("settings.intelligence.statusDownloading");
  }
  switch (model.status) {
    case "ready":
      return t("settings.intelligence.statusReady");
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

function depsInstallText(model: ModelSnapshot): string {
  const pending = Array.isArray(model.deps_pending) ? model.deps_pending : [];
  const visible = pending.slice(0, 4);
  const more = pending.length - visible.length;
  const display = visible.join("、") + (more > 0 ? `… (+${more})` : "");
  if (!display) {
    return t("settings.intelligence.depsInstallingGeneric");
  }
  return t("settings.intelligence.depsInstalling", {
    count: pending.length || model.deps_total,
    names: display,
  });
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

.intel-mirror-row {
  flex-wrap: nowrap;
  align-items: center;
  gap: 16px;
}

.intel-mirror-row .label {
  flex: 1 1 auto;
  min-width: 0;
}

.intel-mirror-actions {
  flex: 1 1 320px;
  flex-wrap: nowrap;
  align-items: center;
  min-width: 0;
}

.intel-mirror-actions input {
  flex: 1 1 auto;
  min-width: 0;
}

.intel-mirror-actions button {
  flex: 0 0 auto;
}

@media (max-width: 560px) {
  .intel-mirror-row {
    flex-wrap: wrap;
  }

  .intel-mirror-actions {
    flex: 1 1 100%;
  }
}

.intel-models {
  list-style: none;
  margin: 4px 0 0;
  padding: 0;
  display: grid;
  gap: 12px;
}

.intel-model {
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 14px 16px;
  background: var(--surface-strong);
  color: var(--text);
  display: grid;
  gap: 10px;
  box-shadow: var(--shadow-sm);
}

html[data-theme="dark"] .intel-model {
  background: var(--surface-1);
  border-color: var(--border-strong);
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

.intel-model-name {
  display: flex;
  flex-direction: column;
  gap: 1px;
  min-width: 0;
}

.intel-model-tech {
  font-size: 11.5px;
  font-family:
    ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono",
    monospace;
  letter-spacing: 0.01em;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  opacity: 0.72;
}

.intel-model-tag {
  display: inline-flex;
  align-items: center;
  padding: 2px 8px;
  border-radius: 999px;
  font-size: 11px;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  background: rgba(99, 102, 241, 0.18);
  color: #6366f1;
  flex-shrink: 0;
}

html[data-theme="dark"] .intel-model-tag {
  background: rgba(99, 102, 241, 0.22);
  color: #a5b4fc;
}

.intel-model-tag.face {
  background: rgba(236, 72, 153, 0.18);
  color: #db2777;
}

html[data-theme="dark"] .intel-model-tag.face {
  background: rgba(236, 72, 153, 0.22);
  color: #f9a8d4;
}

.intel-status-pill {
  font-size: 12px;
  padding: 2px 8px;
  border-radius: 999px;
  background: rgba(148, 163, 184, 0.22);
  color: var(--text-muted);
  flex-shrink: 0;
}

.intel-status-pill.ready {
  background: rgba(34, 197, 94, 0.2);
  color: #15803d;
}

html[data-theme="dark"] .intel-status-pill.ready {
  color: #4ade80;
}

.intel-status-pill.downloading {
  background: rgba(59, 130, 246, 0.22);
  color: #1d4ed8;
}

html[data-theme="dark"] .intel-status-pill.downloading {
  color: #60a5fa;
}

.intel-status-pill.failed,
.intel-status-pill.corrupted {
  background: rgba(239, 68, 68, 0.2);
  color: #b91c1c;
}

html[data-theme="dark"] .intel-status-pill.failed,
html[data-theme="dark"] .intel-status-pill.corrupted {
  color: #f87171;
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
  background: var(--surface-2);
  border: 1px solid var(--border);
  cursor: pointer;
  transition: background var(--transition-fast, 0.15s ease),
    border-color var(--transition-fast, 0.15s ease);
}

.intel-toggle-row:hover:not(.disabled) {
  background: var(--surface-hover);
  border-color: var(--border-strong);
}

.intel-toggle-row[aria-disabled="true"] {
  cursor: not-allowed;
  opacity: 0.55;
}

.intel-toggle-row.not-ready {
  background: rgba(245, 158, 11, 0.12);
  border-color: rgba(245, 158, 11, 0.32);
}

.intel-toggle-row.not-ready .intel-toggle-desc {
  color: #b45309;
}

html[data-theme="dark"] .intel-toggle-row.not-ready {
  background: rgba(245, 158, 11, 0.18);
}

html[data-theme="dark"] .intel-toggle-row.not-ready .intel-toggle-desc {
  color: #fbbf24;
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

.intel-deps-warning {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 8px 12px;
  border-radius: 10px;
  background: rgba(245, 158, 11, 0.14);
  border: 1px solid rgba(245, 158, 11, 0.32);
  color: #b45309;
  font-size: 12.5px;
  line-height: 1.5;
}

html[data-theme="dark"] .intel-deps-warning {
  background: rgba(245, 158, 11, 0.16);
  color: #fbbf24;
}

html[data-theme="dark"] .intel-deps-warning-list {
  color: #fcd34d;
}

.intel-deps-warning :deep(.icon) {
  flex-shrink: 0;
  margin-top: 2px;
}

.intel-deps-warning-body {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.intel-deps-warning-body strong {
  font-weight: 600;
  font-size: 12.5px;
}

.intel-deps-warning-list {
  font-family:
    ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono",
    monospace;
  word-break: break-all;
  color: #92400e;
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
  position: relative;
}

.intel-progress-fill {
  height: 100%;
  background: var(--primary, #6366f1);
  transition: width 0.4s ease;
}

.intel-progress-bar.indeterminate {
  position: relative;
}

.intel-progress-bar.indeterminate .intel-progress-fill {
  position: absolute;
  width: 38%;
  left: -38%;
  background: linear-gradient(
    90deg,
    rgba(99, 102, 241, 0) 0%,
    var(--primary, #6366f1) 50%,
    rgba(99, 102, 241, 0) 100%
  );
  animation: intel-indeterminate 1.4s ease-in-out infinite;
  transition: none;
}

@keyframes intel-indeterminate {
  0% {
    left: -38%;
  }
  100% {
    left: 100%;
  }
}

.intel-deps-text {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  word-break: break-all;
  line-height: 1.5;
}

.intel-deps-text :deep(.icon.spin) {
  animation: intel-spin 1s linear infinite;
}

@keyframes intel-spin {
  from {
    transform: rotate(0deg);
  }
  to {
    transform: rotate(360deg);
  }
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

.intel-face-panel {
  margin-top: 16px;
  border-top: 1px dashed var(--border, rgba(0, 0, 0, 0.08));
  padding-top: 14px;
  display: grid;
  gap: 10px;
}

.intel-face-title {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13.5px;
  margin: 0;
  font-weight: 600;
}

.intel-face-hint {
  margin: 0;
}

.intel-face-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 12px;
}

.intel-face-field {
  display: grid;
  gap: 4px;
}

.intel-face-field-label {
  font-size: 12px;
  font-weight: 600;
}

.intel-face-field input {
  width: 100%;
}

.intel-face-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
  margin-top: 4px;
}
</style>

<template>
  <div
    v-if="visible"
    class="progress-hub"
    :class="{
      'has-active': hasRunning,
      'has-error': hasError,
      'is-open': panelOpen,
    }"
    @mouseenter="onHoverEnter"
    @mouseleave="onHoverLeave"
  >
    <button
      type="button"
      class="progress-hub-trigger"
      :title="triggerTitle"
      :aria-expanded="panelOpen ? 'true' : 'false'"
      @click="onTriggerClick"
    >
      <span class="progress-hub-ring" :class="ringClass">
        <svg
          viewBox="0 0 36 36"
          width="32"
          height="32"
          aria-hidden="true"
        >
          <circle
            class="progress-hub-ring-track"
            cx="18"
            cy="18"
            r="15.5"
            fill="none"
            stroke-width="3"
          />
          <circle
            v-if="!ringIndeterminate"
            class="progress-hub-ring-fill"
            cx="18"
            cy="18"
            r="15.5"
            fill="none"
            stroke-width="3"
            stroke-linecap="round"
            :stroke-dasharray="circumference"
            :stroke-dashoffset="dashOffset"
            transform="rotate(-90 18 18)"
          />
          <circle
            v-else
            class="progress-hub-ring-fill is-spin"
            cx="18"
            cy="18"
            r="15.5"
            fill="none"
            stroke-width="3"
            stroke-linecap="round"
            :stroke-dasharray="`${circumference * 0.28} ${circumference}`"
          />
        </svg>
        <span class="progress-hub-ring-icon">
          <Icon
            v-if="hasError && !hasRunning"
            name="triangle-alert"
            :size="14"
          />
          <Icon
            v-else-if="!hasRunning"
            name="circle-check"
            :size="14"
          />
          <Icon
            v-else-if="ringIndeterminate"
            :name="leadingIcon"
            :size="14"
          />
          <span v-else class="progress-hub-ring-percent">{{ overallPercent }}%</span>
        </span>
      </span>
      <span class="progress-hub-summary">
        <strong>{{ summaryTitle }}</strong>
        <small v-if="summaryDetail">{{ summaryDetail }}</small>
      </span>
    </button>

    <transition name="progress-hub-panel">
      <div v-if="panelOpen" class="progress-hub-panel" role="dialog">
        <div class="progress-hub-panel-head">
          <strong>{{ $t("progressHub.panelTitle") }}</strong>
          <div class="progress-hub-panel-actions">
            <button
              v-if="hasFinishedUpload"
              type="button"
              class="icon sm"
              :title="$t('uploadProgress.clearFinished')"
              @click="upload.clearFinished()"
            >
              <Icon name="eraser" :size="14" />
            </button>
            <button
              type="button"
              class="icon sm"
              :title="$t('progressHub.collapse')"
              @click="closePanel"
            >
              <Icon name="chevron-up" :size="14" />
            </button>
          </div>
        </div>
        <div class="progress-hub-panel-body">
          <template v-if="uploadJobs.length">
            <div class="progress-hub-section">
              <div class="progress-hub-section-head">
                <Icon name="upload-cloud" :size="13" />
                <span>{{ $t("progressHub.sectionUpload") }}</span>
                <span class="muted small">{{ uploadJobs.length }}</span>
              </div>
              <div
                v-for="job in uploadJobs"
                :key="job.id"
                class="progress-hub-item"
                :class="['upload', job.status]"
              >
                <div class="progress-hub-item-head">
                  <span class="progress-hub-item-icon">
                    <Icon
                      :name="uploadStatusIcon(job.status)"
                      :size="13"
                      :class="job.status === 'uploading' ? 'icon-spin' : ''"
                    />
                  </span>
                  <strong class="progress-hub-item-title" :title="job.name">{{
                    job.name
                  }}</strong>
                  <span class="progress-hub-item-tail mono">
                    <span v-if="job.status === 'uploading'">{{ job.progress || 0 }}%</span>
                    <span v-else>{{ formatBytes(job.size) }}</span>
                  </span>
                  <button
                    v-if="job.status === 'uploading'"
                    type="button"
                    class="icon sm"
                    :title="$t('uploadProgress.cancel')"
                    @click="upload.cancel(job.id)"
                  >
                    <Icon name="x" :size="12" />
                  </button>
                  <button
                    v-else
                    type="button"
                    class="icon sm"
                    :title="$t('uploadProgress.dismiss')"
                    @click="upload.dismiss(job.id)"
                  >
                    <Icon name="x" :size="12" />
                  </button>
                </div>
                <div
                  v-if="job.status === 'uploading'"
                  class="progress-hub-item-bar"
                >
                  <span :style="{ width: (job.progress || 0) + '%' }"></span>
                </div>
                <small class="progress-hub-item-detail">{{
                  uploadStatusLabel(job)
                }}</small>
              </div>
            </div>
          </template>

          <template v-if="backgroundTasks.length">
            <div class="progress-hub-section">
              <div class="progress-hub-section-head">
                <Icon name="brain-circuit" :size="13" />
                <span>{{ $t("progressHub.sectionBackground") }}</span>
                <span class="muted small">{{ backgroundTasks.length }}</span>
              </div>
              <div
                v-for="task in backgroundTasks"
                :key="task.id"
                class="progress-hub-item"
                :class="['bg', task.status]"
              >
                <div class="progress-hub-item-head">
                  <span class="progress-hub-item-icon">
                    <Icon
                      :name="taskIcon(task)"
                      :size="13"
                      :class="
                        task.indeterminate && task.status === 'running'
                          ? 'icon-spin'
                          : ''
                      "
                    />
                  </span>
                  <strong class="progress-hub-item-title">{{
                    taskTitle(task)
                  }}</strong>
                  <span
                    v-if="task.status === 'running' && !task.indeterminate"
                    class="progress-hub-item-tail mono"
                  >{{ task.percent }}%</span>
                  <button
                    v-if="task.cancel && task.status === 'running'"
                    type="button"
                    class="icon sm"
                    :title="$t('progressHub.cancelTask')"
                    @click="task.cancel?.()"
                  >
                    <Icon name="x" :size="12" />
                  </button>
                </div>
                <div
                  v-if="task.status === 'running' && !task.indeterminate"
                  class="progress-hub-item-bar"
                >
                  <span :style="{ width: task.percent + '%' }"></span>
                </div>
                <div
                  v-else-if="task.status === 'running' && task.indeterminate"
                  class="progress-hub-item-bar indeterminate"
                >
                  <span></span>
                </div>
                <small class="progress-hub-item-detail">{{
                  taskDetail(task)
                }}</small>
              </div>
            </div>
          </template>

          <div v-if="!uploadJobs.length && !backgroundTasks.length" class="progress-hub-empty">
            <Icon name="circle-check" :size="20" />
            <span>{{ $t("progressHub.empty") }}</span>
          </div>
        </div>
      </div>
    </transition>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import Icon from "@/components/common/Icon.vue";
import { useUploadStore } from "@/stores/upload";
import { useProgressStore, type ProgressTask } from "@/stores/progress";
import { formatSize } from "@/utils/format";
import type { UploadJob } from "@/api/types";

const { t } = useI18n();
const upload = useUploadStore();
const progress = useProgressStore();

/** 是否手动展开/收起浮层 */
const userOpened = ref<boolean | null>(null);
/** 鼠标悬浮态 */
const hovering = ref(false);
/** 后台任务刚启动时，临时展开几秒以便用户感知任务已开启 */
const flashOpen = ref(false);
/** 离开后关闭的延迟计时器，给鼠标移到 panel 留个缓冲 */
let leaveTimer: ReturnType<typeof setTimeout> | null = null;
let flashTimer: ReturnType<typeof setTimeout> | null = null;

const uploadJobs = computed<UploadJob[]>(() => upload.jobs);
const activeUploads = computed(() => uploadJobs.value.filter((job) => job.status === "uploading"));
const failedUploads = computed(() =>
  uploadJobs.value.filter((job) => job.status === "error" || job.status === "cancelled"),
);
const hasFinishedUpload = computed(() =>
  uploadJobs.value.some((job) => job.status !== "uploading"),
);

const backgroundTasks = computed<ProgressTask[]>(() => progress.backgroundTasks);

const hasRunning = computed(
  () =>
    activeUploads.value.length > 0 ||
    backgroundTasks.value.some((task) => task.status === "running"),
);
const hasError = computed(
  () =>
    failedUploads.value.length > 0 ||
    backgroundTasks.value.some((task) => task.status === "error"),
);
const visible = computed(() => uploadJobs.value.length > 0 || backgroundTasks.value.length > 0);

const overallPercent = computed(() => {
  if (activeUploads.value.length) {
    const totalBytes = activeUploads.value.reduce((sum, job) => sum + (job.size || 0), 0);
    const loadedBytes = activeUploads.value.reduce((sum, job) => sum + (job.loaded || 0), 0);
    if (!totalBytes) return 0;
    return Math.min(100, Math.round((loadedBytes / totalBytes) * 100));
  }
  // 没有上传任务则取后台进度的「最有价值」一个
  const determinate = backgroundTasks.value
    .filter((task) => task.status === "running" && !task.indeterminate)
    .map((task) => task.percent);
  if (determinate.length) {
    return Math.round(determinate.reduce((sum, p) => sum + p, 0) / determinate.length);
  }
  return 0;
});

/** 圆环展示是否进入不确定模式 */
const ringIndeterminate = computed(() => {
  if (activeUploads.value.length) return false;
  if (!backgroundTasks.value.length) return false;
  const running = backgroundTasks.value.filter((task) => task.status === "running");
  if (!running.length) return false;
  return running.every((task) => task.indeterminate);
});

const circumference = 2 * Math.PI * 15.5;
const dashOffset = computed(() => {
  const p = Math.max(0, Math.min(100, overallPercent.value));
  return circumference - (circumference * p) / 100;
});

const ringClass = computed(() => {
  if (!hasRunning.value && hasError.value) return "is-error";
  if (!hasRunning.value) return "is-done";
  return "is-running";
});

const leadingIcon = computed(() => {
  // 在不确定模式下显示当前最重要的运行任务图标
  const running = backgroundTasks.value.find((task) => task.status === "running");
  if (running) return taskIcon(running);
  if (activeUploads.value.length) return "upload-cloud";
  return "loader-2";
});

const summaryTitle = computed(() => {
  if (activeUploads.value.length) {
    return t("progressHub.summaryUploading", {
      count: activeUploads.value.length,
      progress: overallPercent.value,
    });
  }
  const runningBg = backgroundTasks.value.find((task) => task.status === "running");
  if (runningBg) {
    if (runningBg.indeterminate) {
      return taskTitle(runningBg);
    }
    return t("progressHub.summaryWithPercent", {
      percent: runningBg.percent,
      title: taskTitle(runningBg),
    });
  }
  if (hasError.value) return t("progressHub.summaryHasError");
  return t("progressHub.summaryDone");
});

const summaryDetail = computed(() => {
  // header 上只展示极简信息，把详细信息留给 hover 浮层
  const total = uploadJobs.value.length + backgroundTasks.value.length;
  if (!total) return "";
  if (activeUploads.value.length && backgroundTasks.value.some((t) => t.status === "running")) {
    return t("progressHub.summaryMixedDetail", {
      uploads: activeUploads.value.length,
      bg: backgroundTasks.value.filter((task) => task.status === "running").length,
    });
  }
  if (activeUploads.value.length > 1) {
    return t("progressHub.summaryUploadCount", { count: activeUploads.value.length });
  }
  const runningBg = backgroundTasks.value.filter((task) => task.status === "running");
  if (runningBg.length > 1) {
    return t("progressHub.summaryBgCount", { count: runningBg.length });
  }
  return "";
});

const triggerTitle = computed(() => {
  if (panelOpen.value) return t("progressHub.collapse");
  return t("progressHub.expand");
});

/** 哪些任务自动展开 */
const autoOpen = computed(() => {
  // 上传任务存在时默认展开（除非用户手动收起）
  return uploadJobs.value.length > 0;
});

const panelOpen = computed(() => {
  if (!visible.value) return false;
  if (userOpened.value !== null) return userOpened.value;
  if (hovering.value) return true;
  if (flashOpen.value) return true;
  return autoOpen.value;
});

watch(
  () => uploadJobs.value.length,
  (next, prev) => {
    if (next > 0 && prev === 0) {
      // 刚开始有上传任务，重置用户偏好为「自动」
      userOpened.value = null;
    }
    if (next === 0 && backgroundTasks.value.length === 0) {
      userOpened.value = null;
    }
  },
);

/**
 * 后台任务（模型下载、依赖安装、扫描）刚出现"新增运行中任务"时，
 * 短暂展开浮层让用户感知，然后自动收起，仅在 header 上保留圆环 + 描述。
 */
const runningBgCount = computed(
  () => backgroundTasks.value.filter((task) => task.status === "running").length,
);
watch(runningBgCount, (next, prev) => {
  if (next > prev) {
    flashOpen.value = true;
    if (flashTimer) clearTimeout(flashTimer);
    flashTimer = setTimeout(() => {
      flashOpen.value = false;
      flashTimer = null;
    }, 4500);
  }
});

function onTriggerClick() {
  if (panelOpen.value) {
    userOpened.value = false;
  } else {
    userOpened.value = true;
  }
}

function closePanel() {
  userOpened.value = false;
}

function onHoverEnter() {
  if (leaveTimer) {
    clearTimeout(leaveTimer);
    leaveTimer = null;
  }
  hovering.value = true;
}

function onHoverLeave() {
  if (leaveTimer) clearTimeout(leaveTimer);
  leaveTimer = setTimeout(() => {
    hovering.value = false;
    leaveTimer = null;
  }, 160);
}

onBeforeUnmount(() => {
  if (leaveTimer) {
    clearTimeout(leaveTimer);
    leaveTimer = null;
  }
  if (flashTimer) {
    clearTimeout(flashTimer);
    flashTimer = null;
  }
});

function uploadStatusIcon(status: UploadJob["status"]): string {
  if (status === "done") return "circle-check";
  if (status === "error") return "circle-x";
  if (status === "cancelled") return "ban";
  return "loader-2";
}

function uploadStatusLabel(job: UploadJob): string {
  if (job.status === "done") return t("uploadProgress.labelDone");
  if (job.status === "error") return job.message || t("uploadProgress.labelFailed");
  if (job.status === "cancelled") return t("uploadProgress.labelCancelled");
  const loaded = formatSize(job.loaded || 0);
  const total = formatSize(job.size || 0);
  return `${loaded} / ${total} · ${job.progress || 0}%`;
}

function taskIcon(task: ProgressTask): string {
  if (task.kind === "model-download") return "download";
  if (task.kind === "model-deps") return "package-plus";
  if (task.kind === "clip-scan") return "scan-line";
  if (task.kind === "face-scan") return "scan-line";
  return "loader-2";
}

function taskTitle(task: ProgressTask): string {
  const cap = task.meta.capability === "face" ? "Face" : task.meta.capability === "clip" ? "CLIP" : "";
  if (task.kind === "model-download") {
    if (task.status === "running") {
      return t("progressHub.taskTitleModelDownloading", { name: cap || "Model" });
    }
    if (task.status === "done") return t("progressHub.taskTitleModelDone", { name: cap || "Model" });
    if (task.status === "error") return t("progressHub.taskTitleModelFailed", { name: cap || "Model" });
    return t("progressHub.taskTitleModelCancelled", { name: cap || "Model" });
  }
  if (task.kind === "model-deps") {
    if (task.status === "running") return t("progressHub.taskTitleDepsInstalling", { name: cap || "Model" });
    if (task.status === "done") return t("progressHub.taskTitleDepsDone", { name: cap || "Model" });
    if (task.status === "error") return t("progressHub.taskTitleDepsFailed", { name: cap || "Model" });
    return t("progressHub.taskTitleDepsCancelled", { name: cap || "Model" });
  }
  if (task.kind === "clip-scan") {
    if (task.status === "running") return t("progressHub.taskTitleClipScanning");
    if (task.status === "done") return t("progressHub.taskTitleClipScanDone");
    if (task.status === "error") return t("progressHub.taskTitleClipScanFailed");
    return t("progressHub.taskTitleClipScanCancelled");
  }
  if (task.kind === "face-scan") {
    if (task.status === "running") return t("progressHub.taskTitleFaceScanning");
    if (task.status === "done") return t("progressHub.taskTitleFaceScanDone");
    if (task.status === "error") return t("progressHub.taskTitleFaceScanFailed");
    return t("progressHub.taskTitleFaceScanCancelled");
  }
  return "";
}

function taskDetail(task: ProgressTask): string {
  if (task.status === "error" && task.meta.errorMessage) {
    return task.meta.errorMessage;
  }
  if (task.kind === "model-download") {
    if (task.status === "running") {
      const total = task.meta.bytesTotal || 0;
      const done = task.meta.bytesDone || 0;
      const detail = total
        ? `${formatSize(done)} / ${formatSize(total)}`
        : `${formatSize(done)}`;
      return task.meta.currentFile ? `${detail} · ${task.meta.currentFile}` : detail;
    }
    if (task.status === "done") return t("progressHub.detailModelReady");
    if (task.status === "cancelled") return t("uploadProgress.labelCancelled");
    return t("uploadProgress.labelFailed");
  }
  if (task.kind === "model-deps") {
    if (task.status === "running") {
      const visible = (task.meta.depsPending || []).slice(0, 4);
      const more = Math.max(0, (task.meta.depsPending || []).length - visible.length);
      const names = visible.join("、") + (more > 0 ? `… (+${more})` : "");
      if (!names) return t("progressHub.detailDepsGeneric");
      return t("progressHub.detailDepsInstalling", {
        count: task.meta.depsTotal || (task.meta.depsPending || []).length,
        names,
      });
    }
    if (task.status === "done") return t("progressHub.detailDepsDone");
    if (task.status === "cancelled") return t("uploadProgress.labelCancelled");
    return t("uploadProgress.labelFailed");
  }
  if (task.kind === "clip-scan") {
    if (task.status === "running") {
      return t("progressHub.detailClipScanning", {
        indexed: task.meta.indexed || 0,
        failed: task.meta.failed || 0,
      });
    }
    if (task.status === "done") {
      return t("progressHub.detailClipScanDone", { indexed: task.meta.indexed || 0 });
    }
    if (task.status === "cancelled") return t("uploadProgress.labelCancelled");
    return t("uploadProgress.labelFailed");
  }
  if (task.kind === "face-scan") {
    if (task.status === "running") {
      return t("progressHub.detailFaceScanning", {
        processed: task.meta.mediaProcessed || 0,
        indexed: task.meta.facesIndexed || 0,
      });
    }
    if (task.status === "done") {
      return t("progressHub.detailFaceScanDone", {
        faces: task.meta.faceCount || 0,
        persons: task.meta.personCount || 0,
      });
    }
    if (task.status === "cancelled") return t("uploadProgress.labelCancelled");
    return t("uploadProgress.labelFailed");
  }
  return "";
}

function formatBytes(bytes: number) {
  return formatSize(bytes);
}
</script>

<style scoped>
.progress-hub {
  position: relative;
  display: inline-flex;
  align-items: center;
}

.progress-hub-trigger {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  padding: 4px 12px 4px 6px;
  min-height: 40px;
  border-radius: 999px;
  background: var(--surface-1);
  border: 1px solid var(--border);
  color: var(--text);
  cursor: pointer;
  transition: background var(--transition-fast), border-color var(--transition-fast),
    box-shadow var(--transition-fast);
  max-width: min(380px, 36vw);
}

.progress-hub-trigger:hover,
.progress-hub.is-open .progress-hub-trigger {
  border-color: var(--primary-border-strong, var(--border-strong));
  background: var(--surface-strong);
  box-shadow: var(--shadow-sm);
}

.progress-hub.has-error .progress-hub-trigger {
  border-color: rgba(239, 68, 68, 0.4);
}

.progress-hub-ring {
  position: relative;
  width: 32px;
  height: 32px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex: none;
}

.progress-hub-ring svg {
  display: block;
}

.progress-hub-ring-track {
  stroke: var(--border-strong);
  opacity: 0.6;
}

.progress-hub-ring-fill {
  stroke: var(--primary);
  transition: stroke-dashoffset 0.4s ease;
}

.progress-hub-ring.is-done .progress-hub-ring-fill {
  stroke: var(--accent);
}

.progress-hub-ring.is-error .progress-hub-ring-fill {
  stroke: var(--danger);
}

.progress-hub-ring-fill.is-spin {
  animation: progress-hub-spin 1.1s linear infinite;
  transform-origin: center;
}

@keyframes progress-hub-spin {
  to {
    transform: rotate(360deg);
  }
}

.progress-hub-ring-icon {
  position: absolute;
  inset: 0;
  display: grid;
  place-items: center;
  font-size: 11px;
  font-weight: 600;
  color: var(--primary);
  font-variant-numeric: tabular-nums;
  letter-spacing: -0.02em;
  pointer-events: none;
}

.progress-hub-ring.is-done .progress-hub-ring-icon {
  color: var(--accent);
}

.progress-hub-ring.is-error .progress-hub-ring-icon {
  color: var(--danger);
}

.progress-hub-ring-percent {
  font-size: 11px;
  line-height: 1;
}

.progress-hub-summary {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  min-width: 0;
  line-height: 1.2;
  text-align: left;
}

.progress-hub-summary strong {
  font-size: 12.5px;
  font-weight: 600;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 240px;
}

.progress-hub-summary small {
  font-size: 11px;
  color: var(--text-muted);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 240px;
}

@media (max-width: 1100px) {
  .progress-hub-summary {
    display: none;
  }
  .progress-hub-trigger {
    padding: 4px;
    width: 40px;
    justify-content: center;
  }
}

.progress-hub-panel {
  position: absolute;
  top: calc(100% + 10px);
  right: 0;
  width: min(380px, 92vw);
  background: var(--surface-strong);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-lg);
  z-index: var(--z-toast);
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.progress-hub-panel-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 10px 12px;
  border-bottom: 1px solid var(--border);
}

.progress-hub-panel-head strong {
  font-size: 13px;
}

.progress-hub-panel-actions {
  display: inline-flex;
  gap: 4px;
}

.progress-hub-panel-body {
  flex: 1;
  min-height: 0;
  max-height: min(60vh, 480px);
  overflow: auto;
  padding: 10px 12px 12px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.progress-hub-section {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.progress-hub-section-head {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 11.5px;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: var(--text-muted);
}

.progress-hub-section-head .small {
  margin-left: auto;
  text-transform: none;
  letter-spacing: 0;
}

.progress-hub-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 8px 10px;
  border-radius: var(--radius-sm);
  background: var(--surface-1);
  border: 1px solid var(--border);
}

.progress-hub-item.upload.done,
.progress-hub-item.bg.done {
  background: var(--accent-soft);
  border-color: rgba(34, 197, 94, 0.32);
}

.progress-hub-item.upload.error,
.progress-hub-item.upload.cancelled,
.progress-hub-item.bg.error,
.progress-hub-item.bg.cancelled {
  background: var(--danger-soft);
  border-color: rgba(239, 68, 68, 0.3);
}

.progress-hub-item-head {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.progress-hub-item-icon {
  width: 22px;
  height: 22px;
  display: grid;
  place-items: center;
  border-radius: 7px;
  background: var(--surface-2);
  color: var(--text-muted);
  flex: none;
}

.progress-hub-item.upload.uploading .progress-hub-item-icon,
.progress-hub-item.bg.running .progress-hub-item-icon {
  color: var(--primary);
  background: var(--primary-soft);
}

.progress-hub-item.upload.done .progress-hub-item-icon,
.progress-hub-item.bg.done .progress-hub-item-icon {
  color: var(--accent);
  background: rgba(34, 197, 94, 0.18);
}

.progress-hub-item.upload.error .progress-hub-item-icon,
.progress-hub-item.upload.cancelled .progress-hub-item-icon,
.progress-hub-item.bg.error .progress-hub-item-icon,
.progress-hub-item.bg.cancelled .progress-hub-item-icon {
  color: var(--danger);
  background: rgba(239, 68, 68, 0.18);
}

.progress-hub-item-title {
  flex: 1;
  min-width: 0;
  font-size: 12.5px;
  font-weight: 600;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.progress-hub-item-tail {
  flex: none;
  font-size: 11px;
  color: var(--text-muted);
  font-variant-numeric: tabular-nums;
}

.progress-hub-item-bar {
  height: 4px;
  border-radius: 999px;
  overflow: hidden;
  background: var(--surface-2);
  position: relative;
}

.progress-hub-item-bar > span {
  position: absolute;
  inset: 0 auto 0 0;
  background: var(--primary-gradient, linear-gradient(90deg, #6366f1, #22c55e));
  border-radius: inherit;
  transition: width 140ms ease-out;
}

.progress-hub-item-bar.indeterminate > span {
  position: absolute;
  width: 38%;
  left: -38%;
  background: linear-gradient(
    90deg,
    rgba(var(--primary-rgb, 99, 102, 241), 0) 0%,
    var(--primary) 50%,
    rgba(var(--primary-rgb, 99, 102, 241), 0) 100%
  );
  animation: progress-hub-indeterminate 1.4s ease-in-out infinite;
}

@keyframes progress-hub-indeterminate {
  0% {
    left: -38%;
  }
  100% {
    left: 100%;
  }
}

.progress-hub-item-detail {
  font-size: 11.5px;
  color: var(--text-muted);
  word-break: break-word;
  line-height: 1.45;
}

.progress-hub-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  padding: 16px 8px;
  color: var(--text-muted);
  font-size: 12.5px;
}

/* 触摸/移动设备隐藏：使用底部 UploadProgress 浮窗 */
@media (hover: none), (max-width: 720px) {
  .progress-hub {
    display: none;
  }
}

.progress-hub-panel-enter-active,
.progress-hub-panel-leave-active {
  transition: opacity var(--transition-fast), transform var(--transition-fast);
}

.progress-hub-panel-enter-from,
.progress-hub-panel-leave-to {
  opacity: 0;
  transform: translateY(-4px);
}

.icon-spin {
  animation: progress-hub-spin 1.1s linear infinite;
  transform-origin: center;
}
</style>

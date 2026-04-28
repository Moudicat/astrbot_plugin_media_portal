<template>
  <div
    v-if="hasJobs"
    class="upload-progress mobile-only-flex"
    :class="{ expanded, hover: hovering, 'has-error': failed.length }"
    @mouseenter="hovering = true"
    @mouseleave="hovering = false"
  >
    <div class="upload-progress-header" @click="$emit('toggle')">
      <div class="upload-progress-summary">
        <div class="upload-progress-icon">
          <Icon v-if="active.length" name="upload-cloud" :size="18" />
          <Icon v-else-if="failed.length" name="triangle-alert" :size="18" />
          <Icon v-else name="circle-check" :size="18" />
        </div>
        <div class="upload-progress-meta">
          <strong>{{ summary }}</strong>
          <div v-if="active.length" class="upload-progress-bar">
            <span :style="{ width: overallProgress + '%' }"></span>
          </div>
        </div>
      </div>
      <div class="upload-progress-actions" @click.stop>
        <button
          v-if="hasFinished && !active.length"
          class="icon sm"
          :title="$t('uploadProgress.clearFinished')"
          @click="$emit('clear-finished')"
        >
          <Icon name="trash-2" :size="14" />
        </button>
        <button
          class="icon sm"
          :title="expanded ? $t('uploadProgress.collapse') : $t('uploadProgress.expand')"
          @click="$emit('toggle')"
        >
          <Icon :name="expanded ? 'chevron-down' : 'chevron-up'" :size="14" />
        </button>
      </div>
    </div>
    <transition name="upload-panel">
      <div v-if="expanded" class="upload-progress-list">
        <div
          v-for="job in jobs"
          :key="job.id"
          class="upload-progress-item"
          :class="job.status"
        >
          <div class="upload-progress-item-head">
            <span class="upload-progress-item-icon">
              <Icon
                :name="statusIcon(job.status)"
                :size="14"
                :class="job.status === 'uploading' ? 'icon-spin' : ''"
              />
            </span>
            <strong class="upload-progress-name" :title="job.name">{{ job.name }}</strong>
            <span class="upload-progress-size mono">{{ formatBytes(job.size) }}</span>
            <button
              v-if="job.status === 'uploading'"
              class="icon sm"
              :title="$t('uploadProgress.cancel')"
              @click="$emit('cancel', job.id)"
            >
              <Icon name="x" :size="12" />
            </button>
            <button
              v-else
              class="icon sm"
              :title="$t('uploadProgress.dismiss')"
              @click="$emit('dismiss', job.id)"
            >
              <Icon name="x" :size="12" />
            </button>
          </div>
          <div v-if="job.status === 'uploading'" class="upload-progress-bar">
            <span :style="{ width: (job.progress || 0) + '%' }"></span>
          </div>
          <small class="upload-progress-status">{{ statusLabel(job) }}</small>
        </div>
      </div>
    </transition>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from "vue";
import { useI18n } from "vue-i18n";
import Icon from "@/components/common/Icon.vue";
import { formatSize } from "@/utils/format";
import type { UploadJob } from "@/api/types";

interface Props {
  jobs?: UploadJob[];
  open?: boolean;
}

const props = withDefaults(defineProps<Props>(), {
  jobs: () => [],
  open: false,
});

defineEmits<{
  (e: "toggle"): void;
  (e: "cancel", id: string): void;
  (e: "dismiss", id: string): void;
  (e: "clear-finished"): void;
}>();

const { t } = useI18n();
const hovering = ref(false);

const active = computed(() => props.jobs.filter((job) => job.status === "uploading"));
const done = computed(() => props.jobs.filter((job) => job.status === "done"));
const failed = computed(() =>
  props.jobs.filter((job) => job.status === "error" || job.status === "cancelled"),
);
const hasJobs = computed(() => props.jobs.length > 0);
const expanded = computed(() => props.open);
const hasFinished = computed(() => done.value.length + failed.value.length > 0);

const overallProgress = computed(() => {
  if (!active.value.length) {
    return props.jobs.length
      ? Math.round(
          props.jobs.reduce((sum, job) => sum + (job.progress || 0), 0) / props.jobs.length,
        )
      : 0;
  }
  const totalBytes = active.value.reduce((sum, job) => sum + (job.size || 0), 0);
  const loadedBytes = active.value.reduce((sum, job) => sum + (job.loaded || 0), 0);
  if (!totalBytes) return 0;
  return Math.min(100, Math.round((loadedBytes / totalBytes) * 100));
});

const summary = computed(() => {
  if (active.value.length) {
    return t("uploadProgress.uploading", {
      count: active.value.length,
      progress: overallProgress.value,
    });
  }
  if (failed.value.length) {
    return t("uploadProgress.mixed", { done: done.value.length, failed: failed.value.length });
  }
  return t("uploadProgress.done", { count: done.value.length });
});

function statusIcon(status: UploadJob["status"]) {
  if (status === "done") return "circle-check";
  if (status === "error") return "circle-x";
  if (status === "cancelled") return "ban";
  return "loader";
}

function statusLabel(job: UploadJob) {
  if (job.status === "done") return t("uploadProgress.labelDone");
  if (job.status === "error") return job.message || t("uploadProgress.labelFailed");
  if (job.status === "cancelled") return t("uploadProgress.labelCancelled");
  return `${job.progress || 0}%`;
}

function formatBytes(bytes: number) {
  return formatSize(bytes);
}
</script>

<style scoped>
/* 仅在窄屏 / 触摸设备上展示底部上传浮窗，桌面端由 ProgressHub 接管 */
.upload-progress.mobile-only-flex {
  display: none;
}

@media (hover: none), (max-width: 720px) {
  .upload-progress.mobile-only-flex {
    display: block;
  }
}
</style>

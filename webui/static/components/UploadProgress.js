import { Icon } from "./Icon.js";

function formatSize(bytes) {
  const size = Number(bytes) || 0;
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
  if (size < 1024 * 1024 * 1024) return `${(size / 1048576).toFixed(1)} MB`;
  return `${(size / 1073741824).toFixed(2)} GB`;
}

export const UploadProgress = {
  name: "UploadProgress",
  components: { Icon },
  props: {
    jobs: { type: Array, default: () => [] },
    open: { type: Boolean, default: false },
  },
  emits: ["toggle", "cancel", "dismiss", "clear-finished"],
  data() {
    return {
      hovering: false,
    };
  },
  computed: {
    active() {
      return this.jobs.filter((job) => job.status === "uploading");
    },
    done() {
      return this.jobs.filter((job) => job.status === "done");
    },
    failed() {
      return this.jobs.filter(
        (job) => job.status === "error" || job.status === "cancelled"
      );
    },
    hasJobs() {
      return this.jobs.length > 0;
    },
    expanded() {
      return this.open;
    },
    overallProgress() {
      if (!this.active.length) {
        return this.jobs.length
          ? Math.round(
              this.jobs.reduce((sum, job) => sum + (job.progress || 0), 0) /
                this.jobs.length
            )
          : 0;
      }
      const totalBytes = this.active.reduce((sum, job) => sum + (job.size || 0), 0);
      const loadedBytes = this.active.reduce(
        (sum, job) => sum + (job.loaded || 0),
        0
      );
      if (!totalBytes) return 0;
      return Math.min(100, Math.round((loadedBytes / totalBytes) * 100));
    },
    summary() {
      if (this.active.length) {
        return `上传中 · ${this.active.length} · ${this.overallProgress}%`;
      }
      if (this.failed.length) {
        return `完成 · ${this.done.length} 成功 / ${this.failed.length} 失败`;
      }
      return `上传完成 · ${this.done.length}`;
    },
    hasFinished() {
      return this.done.length + this.failed.length > 0;
    },
  },
  methods: {
    formatSize,
    statusIcon(status) {
      if (status === "done") return "circle-check";
      if (status === "error") return "circle-x";
      if (status === "cancelled") return "ban";
      return "loader";
    },
    statusLabel(job) {
      if (job.status === "done") return "成功";
      if (job.status === "error") return job.message || "失败";
      if (job.status === "cancelled") return "已取消";
      return `${job.progress || 0}%`;
    },
  },
  template: `
    <div
      v-if="hasJobs"
      class="upload-progress"
      :class="{ expanded, hover: hovering, 'has-error': failed.length }"
      @mouseenter="hovering = true"
      @mouseleave="hovering = false"
    >
      <div class="upload-progress-header" @click="$emit('toggle')">
        <div class="upload-progress-summary">
          <div class="upload-progress-icon">
            <Icon
              v-if="active.length"
              name="upload-cloud"
              :size="18"
            />
            <Icon
              v-else-if="failed.length"
              name="triangle-alert"
              :size="18"
            />
            <Icon v-else name="circle-check" :size="18" />
          </div>
          <div class="upload-progress-meta">
            <strong>{{ summary }}</strong>
            <div class="upload-progress-bar" v-if="active.length">
              <span :style="{ width: overallProgress + '%' }"></span>
            </div>
          </div>
        </div>
        <div class="upload-progress-actions" @click.stop>
          <button
            v-if="hasFinished && !active.length"
            class="icon sm"
            @click="$emit('clear-finished')"
            title="清除完成"
          >
            <Icon name="trash-2" :size="14" />
          </button>
          <button class="icon sm" @click="$emit('toggle')" :title="expanded ? '收起' : '展开'">
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
              <span class="upload-progress-size mono">{{ formatSize(job.size) }}</span>
              <button
                v-if="job.status === 'uploading'"
                class="icon sm"
                @click="$emit('cancel', job.id)"
                title="取消"
              >
                <Icon name="x" :size="12" />
              </button>
              <button
                v-else
                class="icon sm"
                @click="$emit('dismiss', job.id)"
                title="移除"
              >
                <Icon name="x" :size="12" />
              </button>
            </div>
            <div class="upload-progress-bar" v-if="job.status === 'uploading'">
              <span :style="{ width: (job.progress || 0) + '%' }"></span>
            </div>
            <small class="upload-progress-status">{{ statusLabel(job) }}</small>
          </div>
        </div>
      </transition>
    </div>
  `,
};

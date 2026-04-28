import { defineStore } from "pinia";
import {
  intelligenceApi,
  type ModelSnapshot,
  type ClipStatusResp,
  type FaceStatusResp,
} from "@/api/intelligence";

export type ProgressTaskKind =
  | "model-download"
  | "model-deps"
  | "clip-scan"
  | "face-scan";

export type ProgressTaskStatus = "running" | "done" | "error" | "cancelled";

export interface ProgressTaskMeta {
  /** 模型/能力相关 */
  capability?: "clip" | "face";
  modelKey?: string;
  currentFile?: string;
  bytesDone?: number;
  bytesTotal?: number;
  depsPending?: string[];
  depsTotal?: number;
  /** 扫描相关 */
  indexed?: number;
  failed?: number;
  mediaProcessed?: number;
  facesIndexed?: number;
  faceCount?: number;
  personCount?: number;
  errorMessage?: string;
  /** 完成态摘要文本（已用 i18n 渲染好的字符串，可选） */
  summary?: string;
}

export interface ProgressTask {
  id: string;
  kind: ProgressTaskKind;
  /** 进度百分比 0~100，indeterminate=true 时忽略 */
  percent: number;
  /** 不确定模式（仅显示忙碌动画） */
  indeterminate: boolean;
  status: ProgressTaskStatus;
  /** 任务结束时间戳（毫秒），仅当 status !== "running" 时有意义 */
  finishedAt: number | null;
  /** 取消回调（仅运行中支持） */
  cancel?: (() => void) | null;
  meta: ProgressTaskMeta;
}

const POLL_INTERVAL_MS = 3500;
const FINISHED_LINGER_MS = 6000;

interface BackgroundTaskEntry {
  task: ProgressTask;
  pruneTimer: ReturnType<typeof setTimeout> | null;
}

export const useProgressStore = defineStore("progress", {
  state: () => ({
    background: {} as Record<string, BackgroundTaskEntry>,
    _pollTimer: null as ReturnType<typeof setTimeout> | null,
    _polling: false,
    /** 在 polling 进行中又被 bump，则记下需要再跑一次。 */
    _needsRepoll: false,
    _started: false,
    /**
     * 上一次轮询时观察到的 ``status.stats.last_run_at`` 基线。
     *
     * - 取值 ``-1`` 表示「尚未建立基线」（首次轮询用来校准）；
     * - 当后端的 ``last_run_at`` 比基线增大 → 认为有一次扫描在两次轮询之间完成了，
     *   此时即使我们没有捕获到 ``scanning=true``，也补造一个 ``done`` 条目让用户感知；
     * - 当 ``last_run_at`` 变小（如清空人脸数据后）→ 重新建立基线。
     */
    _lastClipRunAt: -1 as number,
    _lastFaceRunAt: -1 as number,
  }),
  getters: {
    backgroundTasks(state): ProgressTask[] {
      const entries = Object.values(state.background);
      return entries
        .map((entry) => entry.task)
        .sort((a, b) => {
          if (a.status === b.status) return a.id.localeCompare(b.id);
          return a.status === "running" ? -1 : 1;
        });
    },
    runningCount(state): number {
      let count = 0;
      for (const entry of Object.values(state.background)) {
        if (entry.task.status === "running") count += 1;
      }
      return count;
    },
  },
  actions: {
    start() {
      if (this._started) return;
      this._started = true;
      this.scheduleNext(0);
    },
    stop() {
      this._started = false;
      if (this._pollTimer) {
        clearTimeout(this._pollTimer);
        this._pollTimer = null;
      }
      for (const id of Object.keys(this.background)) {
        const entry = this.background[id];
        if (entry?.pruneTimer) {
          clearTimeout(entry.pruneTimer);
        }
      }
      this.background = {};
      this._lastClipRunAt = -1;
      this._lastFaceRunAt = -1;
    },
    scheduleNext(delay: number) {
      if (!this._started) return;
      if (this._pollTimer) {
        clearTimeout(this._pollTimer);
        this._pollTimer = null;
      }
      this._pollTimer = setTimeout(() => {
        this._pollTimer = null;
        this.pollOnce()
          .catch(() => undefined)
          .finally(() => this.scheduleNext(POLL_INTERVAL_MS));
      }, Math.max(0, delay));
    },
    /** 外部触发立刻刷新一次（启动下载/扫描后调用，便于尽快出现进度） */
    bump() {
      this.scheduleNext(80);
    },
    /**
     * 乐观地在进度条里立刻插入一个"扫描进行中"的占位任务。
     *
     * 用于在用户点击「扫描」后立即给到反馈，避免出现以下场景：
     *   - 后端扫描秒级完成（无新增图片）→ 下次轮询拉到 scanning=false → 进度条永远不出现；
     *   - 第一次轮询命中 polling 进行中 → 直到 3.5s 后才更新 → 中间出现感知盲区。
     *
     * 调用后下一次轮询会按真实状态把它纠正为运行中或 done。
     */
    markScanRunning(kind: "clip-scan" | "face-scan") {
      const meta: ProgressTaskMeta =
        kind === "face-scan"
          ? { mediaProcessed: 0, facesIndexed: 0 }
          : { indexed: 0, failed: 0 };
      this.upsertBg({
        id: kind,
        kind,
        percent: 0,
        indeterminate: true,
        status: "running",
        finishedAt: null,
        cancel: null,
        meta,
      });
    },
    async pollOnce() {
      if (this._polling) {
        // 当前正在拉数据，记下"还需要再跑一次"，让本次完成后立刻补一次。
        this._needsRepoll = true;
        return;
      }
      this._polling = true;
      try {
        do {
          this._needsRepoll = false;
          await this._runPollCycle();
        } while (this._needsRepoll);
      } finally {
        this._polling = false;
      }
    },
    async _runPollCycle() {
      const list = await intelligenceApi.listModels().catch(() => null);
      if (!list || !list.feature_enabled) {
        this.purgeKinds(["model-download", "model-deps", "clip-scan", "face-scan"]);
        return;
      }
      for (const model of list.models || []) {
        this.applyModelSnapshot(model);
      }
      const clipModelReady = (list.models || []).some(
        (m) => m.capability === "clip" && m.status === "ready",
      );
      const faceModelReady = (list.models || []).some(
        (m) => m.capability === "face" && m.status === "ready",
      );
      if (list.clip_enabled && clipModelReady) {
        const status = await intelligenceApi.clipStatus().catch(() => null);
        this.applyClipStatus(status);
      } else {
        this.dropById("clip-scan", true);
      }
      if (list.face_enabled && faceModelReady) {
        const status = await intelligenceApi.faceStatus().catch(() => null);
        this.applyFaceStatus(status);
      } else {
        this.dropById("face-scan", true);
      }
    },
    applyModelSnapshot(model: ModelSnapshot) {
      const downloadId = `model-download:${model.key}`;
      const depsId = `model-deps:${model.key}`;
      const isDownloading = model.status === "downloading";
      const isInstallingDeps =
        model.phase === "installing_deps" || model.phase === "checking_deps";

      if (isDownloading && isInstallingDeps) {
        this.upsertBg({
          id: depsId,
          kind: "model-deps",
          percent: 0,
          indeterminate: true,
          status: "running",
          finishedAt: null,
          cancel: () => {
            intelligenceApi.cancelDownload(model.key).catch(() => undefined);
            this.bump();
          },
          meta: {
            capability: model.capability,
            modelKey: model.key,
            depsPending: Array.isArray(model.deps_pending)
              ? [...model.deps_pending]
              : [],
            depsTotal: model.deps_total || (model.deps_pending || []).length,
          },
        });
        this.dropById(downloadId, true);
      } else if (isDownloading) {
        const total = model.progress_total || model.bytes_total || 0;
        const done = model.progress_bytes || model.bytes_complete || 0;
        const percent = total > 0 ? Math.min(100, Math.round((done / total) * 100)) : 0;
        this.upsertBg({
          id: downloadId,
          kind: "model-download",
          percent,
          indeterminate: total <= 0,
          status: "running",
          finishedAt: null,
          cancel: () => {
            intelligenceApi.cancelDownload(model.key).catch(() => undefined);
            this.bump();
          },
          meta: {
            capability: model.capability,
            modelKey: model.key,
            currentFile: model.current_file || "",
            bytesDone: done,
            bytesTotal: total,
          },
        });
        this.dropById(depsId, true);
      } else {
        const terminal = terminalStatusFromModel(model);
        this.finishById(downloadId, terminal, {
          errorMessage: model.last_error || undefined,
        });
        this.finishById(depsId, terminal, {
          errorMessage: model.last_error || undefined,
        });
      }
    },
    applyClipStatus(status: ClipStatusResp | null) {
      const id = "clip-scan";
      if (!status) {
        this.dropById(id, true);
        return;
      }
      const lastRunAt = Number(status.stats?.last_run_at || 0);
      if (status.scanning) {
        this.upsertBg({
          id,
          kind: "clip-scan",
          percent: 0,
          indeterminate: true,
          status: "running",
          finishedAt: null,
          cancel: null,
          meta: {
            indexed: status.stats?.indexed || 0,
            failed: status.stats?.failed || 0,
          },
        });
        return;
      }
      const errMsg = status.stats?.last_error;
      const entry = this.background[id];
      if (entry) {
        // 既有条目（之前观察到 running 或乐观插入），直接转为终止态。
        // ``finishById`` 内部对幂等调用做了去抖，不会反复重置 finishedAt。
        this.finishById(id, errMsg ? "error" : "done", {
          indexed: status.indexed_count,
          failed: status.stats?.failed || 0,
          errorMessage: errMsg || undefined,
        });
        this._lastClipRunAt = lastRunAt;
        return;
      }
      if (this._lastClipRunAt < 0) {
        // 首次轮询：建立基线，但不补造 done，避免页面打开就误显示一次"已完成"。
        this._lastClipRunAt = lastRunAt;
        return;
      }
      if (lastRunAt > this._lastClipRunAt) {
        // 两次轮询之间已经跑完一轮扫描（典型场景：上传后后端自动扫描秒级完成）。
        // 先放一个 running 占位，再立刻 finish，让用户在进度中心看到一次完成提示。
        this.upsertBg({
          id,
          kind: "clip-scan",
          percent: 0,
          indeterminate: false,
          status: "running",
          finishedAt: null,
          cancel: null,
          meta: {
            indexed: status.stats?.indexed || 0,
            failed: status.stats?.failed || 0,
          },
        });
        this.finishById(id, errMsg ? "error" : "done", {
          indexed: status.indexed_count,
          failed: status.stats?.failed || 0,
          errorMessage: errMsg || undefined,
        });
        this._lastClipRunAt = lastRunAt;
      } else if (lastRunAt < this._lastClipRunAt) {
        this._lastClipRunAt = lastRunAt;
      }
    },
    applyFaceStatus(status: FaceStatusResp | null) {
      const id = "face-scan";
      if (!status) {
        this.dropById(id, true);
        return;
      }
      const lastRunAt = Number(status.stats?.last_run_at || 0);
      if (status.scanning) {
        this.upsertBg({
          id,
          kind: "face-scan",
          percent: 0,
          indeterminate: true,
          status: "running",
          finishedAt: null,
          cancel: null,
          meta: {
            mediaProcessed: status.stats?.media_processed || 0,
            facesIndexed: status.stats?.faces_indexed || 0,
          },
        });
        return;
      }
      const errMsg = status.stats?.last_error;
      const entry = this.background[id];
      if (entry) {
        this.finishById(id, errMsg ? "error" : "done", {
          faceCount: status.face_count,
          personCount: status.person_count,
          errorMessage: errMsg || undefined,
        });
        this._lastFaceRunAt = lastRunAt;
        return;
      }
      if (this._lastFaceRunAt < 0) {
        this._lastFaceRunAt = lastRunAt;
        return;
      }
      if (lastRunAt > this._lastFaceRunAt) {
        this.upsertBg({
          id,
          kind: "face-scan",
          percent: 0,
          indeterminate: false,
          status: "running",
          finishedAt: null,
          cancel: null,
          meta: {
            mediaProcessed: status.stats?.media_processed || 0,
            facesIndexed: status.stats?.faces_indexed || 0,
          },
        });
        this.finishById(id, errMsg ? "error" : "done", {
          faceCount: status.face_count,
          personCount: status.person_count,
          errorMessage: errMsg || undefined,
        });
        this._lastFaceRunAt = lastRunAt;
      } else if (lastRunAt < this._lastFaceRunAt) {
        this._lastFaceRunAt = lastRunAt;
      }
    },
    upsertBg(task: ProgressTask) {
      const existing = this.background[task.id];
      if (existing?.pruneTimer) {
        clearTimeout(existing.pruneTimer);
        existing.pruneTimer = null;
      }
      this.background = {
        ...this.background,
        [task.id]: { task, pruneTimer: null },
      };
    },
    finishById(
      id: string,
      status: "done" | "error" | "cancelled",
      metaPatch: Partial<ProgressTaskMeta> = {},
    ) {
      const entry = this.background[id];
      if (!entry) return;
      // 当后端反复返回相同的"已完成"快照时，``applyXxxStatus`` 会反复调用 finishById；
      // 此处保留首次进入终止态时的 finishedAt 与 pruneTimer，避免每次轮询都把
      // "完成倒计时"重置成 6s，导致条目永远无法自动消失。
      const isIdempotent =
        entry.task.status === status && entry.task.finishedAt !== null;
      const finishedAt = isIdempotent
        ? entry.task.finishedAt
        : Date.now();

      let pruneTimer = entry.pruneTimer;
      if (!isIdempotent) {
        if (pruneTimer) clearTimeout(pruneTimer);
        pruneTimer = setTimeout(() => {
          const cur = this.background[id];
          if (!cur) return;
          if (
            cur.task.finishedAt &&
            Date.now() - cur.task.finishedAt >= FINISHED_LINGER_MS
          ) {
            this.dropById(id, false);
          }
        }, FINISHED_LINGER_MS + 80);
      }

      const updated: ProgressTask = {
        ...entry.task,
        status,
        finishedAt,
        cancel: null,
        indeterminate: false,
        percent: status === "done" ? 100 : entry.task.percent,
        meta: { ...entry.task.meta, ...metaPatch },
      };
      this.background = {
        ...this.background,
        [id]: { task: updated, pruneTimer },
      };
    },
    dropById(id: string, _immediate = false) {
      const entry = this.background[id];
      if (!entry) return;
      if (entry.pruneTimer) {
        clearTimeout(entry.pruneTimer);
      }
      const next = { ...this.background };
      delete next[id];
      this.background = next;
    },
    purgeKinds(kinds: ProgressTaskKind[]) {
      const set = new Set(kinds);
      const next = { ...this.background };
      let changed = false;
      for (const [id, entry] of Object.entries(next)) {
        if (set.has(entry.task.kind)) {
          if (entry.pruneTimer) clearTimeout(entry.pruneTimer);
          delete next[id];
          changed = true;
        }
      }
      if (changed) this.background = next;
    },
  },
});

function terminalStatusFromModel(model: ModelSnapshot): "done" | "error" | "cancelled" {
  if (model.status === "ready") return "done";
  if (model.status === "cancelled") return "cancelled";
  if (model.status === "failed" || model.status === "corrupted") return "error";
  return "done";
}

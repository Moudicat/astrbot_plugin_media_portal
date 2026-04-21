<template>
  <transition name="modal">
    <div v-if="visible" class="modal-mask" @click.self="$emit('close')">
      <div class="modal settings-modal">
        <header>
          <h3>
            <Icon name="settings" :size="17" style="vertical-align: -3px" />
            {{ $t("settings.title") }}
          </h3>
          <button class="icon" :title="$t('common.closeEsc')" @click="$emit('close')">
            <Icon name="x" :size="16" />
          </button>
        </header>

        <div class="modal-body settings-body">
          <section class="settings-section">
            <div class="settings-section-head">
              <div>
                <strong>{{ $t("settings.statsTitle") }}</strong>
                <small class="muted">{{ $t("settings.statsHint") }}</small>
              </div>
              <div class="settings-toolbar">
                <button
                  class="ghost sm"
                  :disabled="allOn"
                  :title="$t('settings.showAll')"
                  @click="setAll(true)"
                >
                  <Icon name="eye" :size="13" />
                  <span>{{ $t("settings.showAll") }}</span>
                </button>
                <button
                  class="ghost sm"
                  :disabled="allOff"
                  :title="$t('settings.hideAll')"
                  @click="setAll(false)"
                >
                  <Icon name="eye-off" :size="13" />
                  <span>{{ $t("settings.hideAll") }}</span>
                </button>
              </div>
            </div>
            <ul class="settings-toggle-list">
              <li
                v-for="opt in statOptions"
                :key="opt.key"
                class="settings-toggle"
                :class="{ disabled: !isOn(opt.key) }"
                @click="toggleStat(opt.key)"
              >
                <div class="settings-toggle-icon">
                  <Icon :name="opt.icon" :size="14" />
                </div>
                <div class="settings-toggle-body">
                  <span class="settings-toggle-title">{{ $t(opt.labelKey) }}</span>
                  <span class="settings-toggle-desc">{{ $t(opt.descKey) }}</span>
                </div>
                <span
                  class="switch"
                  :class="{ on: isOn(opt.key) }"
                  role="switch"
                  :aria-checked="isOn(opt.key) ? 'true' : 'false'"
                ></span>
              </li>
            </ul>
          </section>

          <section class="settings-section">
            <h4>{{ $t("settings.appearanceTitle") }}</h4>

            <div class="settings-row">
              <div class="label">
                <strong>{{ $t("settings.themeColor") }}</strong>
                <small>{{ $t("settings.themeColorHint") }}</small>
              </div>
              <div class="theme-color-row">
                <button
                  v-for="color in themeColors"
                  :key="color"
                  class="theme-color-swatch"
                  :class="{ active: ui.themeColor === color }"
                  :style="{ background: presetColor(color) }"
                  :title="color"
                  @click="ui.setThemeColor(color)"
                ></button>
              </div>
            </div>

            <div class="settings-row">
              <div class="label">
                <strong>{{ $t("settings.gridDensity") }}</strong>
                <small>{{ $t("settings.gridDensityHint") }}</small>
              </div>
              <div class="settings-chip-group">
                <button
                  v-for="d in gridDensities"
                  :key="d"
                  :class="{ active: ui.gridDensity === d }"
                  @click="ui.setGridDensity(d)"
                >
                  {{ $t(`settings.density.${d}`) }}
                </button>
              </div>
            </div>

            <div class="settings-row">
              <div class="label">
                <strong>{{ $t("settings.pageSize") }}</strong>
                <small>{{ $t("settings.pageSizeHint") }}</small>
              </div>
              <div class="settings-chip-group">
                <button
                  v-for="size in pageSizes"
                  :key="size"
                  :class="{ active: ui.pageSize === size }"
                  @click="applyPageSize(size)"
                >
                  {{ size }}
                </button>
              </div>
            </div>
          </section>

          <section class="settings-section">
            <div class="settings-section-head">
              <div>
                <strong>{{ $t("settings.languageTitle") }}</strong>
                <small class="muted">{{ $t("settings.languageHint") }}</small>
              </div>
              <LanguageSwitcher />
            </div>
          </section>

          <section class="settings-section">
            <div class="settings-section-head">
              <div>
                <strong>{{ $t("settings.pruneTitle") }}</strong>
                <small class="muted">{{ $t("settings.pruneHint") }}</small>
              </div>
              <button class="ghost" :disabled="pruneBusy" @click="onPrune">
                <Icon name="eraser" :size="14" />
                <span>{{ pruneBusy ? $t("settings.pruneBusy") : $t("settings.pruneNow") }}</span>
              </button>
            </div>
          </section>

          <section class="settings-section">
            <h4>{{ $t("settings.trashTitle") }}</h4>
            <div class="settings-row">
              <div class="label">
                <strong>{{ $t("settings.trashRetentionLabel") }}</strong>
                <small>{{ $t("settings.trashRetentionHint") }}</small>
              </div>
              <div class="settings-actions-row">
                <input
                  v-model.number="trashRetentionDraft"
                  type="number"
                  min="1"
                  max="3650"
                  style="width: 110px"
                />
                <button class="ghost" :disabled="trashSaving" @click="saveTrashRetention">
                  <Icon name="save" :size="14" />
                  <span>{{ trashSaving ? $t("settings.backupBusy") : $t("common.save") }}</span>
                </button>
                <button class="ghost" @click="$emit('purge-trash-expired')">
                  <Icon name="eraser" :size="14" />
                  <span>{{ $t("settings.trashPurgeNow") }}</span>
                </button>
              </div>
            </div>
            <div class="settings-row">
              <div class="label">
                <strong>{{ $t("settings.duplicatesTitle") }}</strong>
                <small>{{ $t("settings.duplicatesHint") }}</small>
              </div>
              <div class="settings-actions-row">
                <button class="ghost" @click="$emit('open-duplicates')">
                  <Icon name="search-x" :size="14" />
                  <span>{{ $t("settings.openDuplicates") }}</span>
                </button>
              </div>
            </div>
          </section>

          <section class="settings-section">
            <h4>{{ $t("settings.backupTitle") }}</h4>
            <div class="settings-row">
              <div class="label">
                <strong>{{ $t("settings.backupExport") }}</strong>
                <small>{{ $t("settings.backupExportHint") }}</small>
              </div>
              <div class="settings-actions-row">
                <button class="ghost" :disabled="exportBusy" @click="onExport(true)">
                  <Icon name="package" :size="14" />
                  <span>{{
                    exportBusy ? $t("settings.backupBusy") : $t("settings.backupExportFull")
                  }}</span>
                </button>
                <button class="ghost" :disabled="exportBusy" @click="onExport(false)">
                  <Icon name="file-down" :size="14" />
                  <span>{{ $t("settings.backupExportMeta") }}</span>
                </button>
              </div>
            </div>

            <div class="settings-row">
              <div class="label">
                <strong>{{ $t("settings.backupImport") }}</strong>
                <small>{{ $t("settings.backupImportHint") }}</small>
              </div>
              <div class="settings-actions-row">
                <label class="switch-inline">
                  <input v-model="replaceMedia" type="checkbox" />
                  <span>{{ $t("settings.backupReplaceMedia") }}</span>
                </label>
                <button class="ghost" :disabled="importBusy" @click="pickImportFile">
                  <Icon name="upload" :size="14" />
                  <span>{{
                    importBusy ? $t("settings.backupBusy") : $t("settings.backupImportBtn")
                  }}</span>
                </button>
                <input
                  ref="importInput"
                  type="file"
                  accept=".gz,.tgz,.tar,application/gzip,application/x-tar"
                  style="display: none"
                  @change="onImportFile"
                />
              </div>
            </div>

            <div class="settings-row">
              <div class="label">
                <strong>{{ $t("settings.settingsIo") }}</strong>
                <small>{{ $t("settings.settingsIoHint") }}</small>
              </div>
              <div class="settings-actions-row">
                <button class="ghost" @click="exportSettings">
                  <Icon name="file-down" :size="14" />
                  <span>{{ $t("settings.settingsExport") }}</span>
                </button>
                <button class="ghost" @click="pickSettingsFile">
                  <Icon name="file-up" :size="14" />
                  <span>{{ $t("settings.settingsImport") }}</span>
                </button>
                <input
                  ref="settingsInput"
                  type="file"
                  accept="application/json,.json"
                  style="display: none"
                  @change="onImportSettings"
                />
              </div>
            </div>
          </section>

        </div>

        <div class="modal-footer">
          <button class="primary" @click="$emit('close')">{{ $t("common.done") }}</button>
        </div>
      </div>
    </div>
  </transition>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import Icon from "@/components/common/Icon.vue";
import LanguageSwitcher from "@/components/common/LanguageSwitcher.vue";
import {
  GRID_DENSITY_KEYS,
  PAGE_SIZE_OPTIONS,
  THEME_COLOR_KEYS,
  THEME_COLOR_PRESETS,
  useUiStore,
  type GridDensity,
  type StatVisibility,
  type ThemeColor,
} from "@/stores/ui";
import { useAuthStore } from "@/stores/auth";
import { useMediaStore } from "@/stores/media";
import { useToastStore } from "@/stores/toast";
import { backupApi } from "@/api/media";

const STAT_CARD_OPTIONS = [
  { key: "total", labelKey: "settings.stat.total", icon: "library", descKey: "settings.stat.totalDesc" },
  { key: "image", labelKey: "settings.stat.image", icon: "image", descKey: "settings.stat.imageDesc" },
  { key: "video", labelKey: "settings.stat.video", icon: "film", descKey: "settings.stat.videoDesc" },
  { key: "audio", labelKey: "settings.stat.audio", icon: "music", descKey: "settings.stat.audioDesc" },
  { key: "cat", labelKey: "settings.stat.cat", icon: "folder", descKey: "settings.stat.catDesc" },
  { key: "size", labelKey: "settings.stat.size", icon: "database", descKey: "settings.stat.sizeDesc" },
] as const;

interface Props {
  visible?: boolean;
  statVisibility?: StatVisibility;
  trashRetentionDays?: number;
}

const props = withDefaults(defineProps<Props>(), {
  visible: false,
  statVisibility: () => ({
    total: true,
    image: true,
    video: true,
    audio: true,
    cat: true,
    size: true,
  }),
  trashRetentionDays: 30,
});

const emit = defineEmits<{
  (e: "close"): void;
  (e: "prune-categories"): void;
  (e: "update-stat-visibility", payload: Partial<StatVisibility>): void;
  (e: "open-duplicates"): void;
  (e: "update-trash-retention", days: number): void;
  (e: "purge-trash-expired"): void;
}>();

const { t } = useI18n();

const ui = useUiStore();
const auth = useAuthStore();
const media = useMediaStore();
const toast = useToastStore();

const pruneBusy = ref(false);
const exportBusy = ref(false);
const importBusy = ref(false);
const trashSaving = ref(false);
const trashRetentionDraft = ref(Number(props.trashRetentionDays || 30) || 30);
const replaceMedia = ref(false);
const importInput = ref<HTMLInputElement | null>(null);
const settingsInput = ref<HTMLInputElement | null>(null);

const statOptions = STAT_CARD_OPTIONS;
const themeColors = THEME_COLOR_KEYS;
const gridDensities = GRID_DENSITY_KEYS;
const pageSizes = PAGE_SIZE_OPTIONS;

const allOn = computed(() =>
  STAT_CARD_OPTIONS.every((opt) => (props.statVisibility as any)[opt.key] !== false),
);
const allOff = computed(() =>
  STAT_CARD_OPTIONS.every((opt) => (props.statVisibility as any)[opt.key] === false),
);

function onKey(event: KeyboardEvent) {
  if (!props.visible) return;
  if (event.key === "Escape") emit("close");
}

watch(
  () => props.visible,
  (value) => {
    if (value) {
      pruneBusy.value = false;
      trashSaving.value = false;
      trashRetentionDraft.value = Number(props.trashRetentionDays || 30) || 30;
      window.addEventListener("keydown", onKey);
    } else {
      window.removeEventListener("keydown", onKey);
    }
  },
);

watch(
  () => props.trashRetentionDays,
  (value) => {
    if (!props.visible) return;
    trashRetentionDraft.value = Number(value || 30) || 30;
  },
);

onBeforeUnmount(() => {
  window.removeEventListener("keydown", onKey);
});

function onPrune() {
  pruneBusy.value = true;
  emit("prune-categories");
  setTimeout(() => {
    pruneBusy.value = false;
  }, 1200);
}

function isOn(key: string) {
  return (props.statVisibility as any)[key] !== false;
}

function toggleStat(key: string) {
  emit("update-stat-visibility", { [key]: !isOn(key) } as Partial<StatVisibility>);
}

function setAll(value: boolean) {
  const payload: Record<string, boolean> = {};
  for (const opt of STAT_CARD_OPTIONS) payload[opt.key] = value;
  emit("update-stat-visibility", payload as Partial<StatVisibility>);
}

function presetColor(color: ThemeColor) {
  return THEME_COLOR_PRESETS[color]?.primary || "#6366f1";
}

function saveTrashRetention() {
  const normalized = Math.max(1, Math.min(3650, Number(trashRetentionDraft.value) || 30));
  trashRetentionDraft.value = normalized;
  trashSaving.value = true;
  emit("update-trash-retention", normalized);
  setTimeout(() => {
    trashSaving.value = false;
  }, 500);
}

function applyPageSize(size: number) {
  ui.setPageSize(size);
  media.filters.page_size = size;
  media.filters.page = 1;
  media.fetchList().catch((error) => toast.push((error as Error).message, "error"));
}

async function onExport(includeMedia: boolean) {
  if (exportBusy.value) return;
  exportBusy.value = true;
  try {
    const url = backupApi.exportUrl(includeMedia);
    const headers: Record<string, string> = {};
    if (auth.token) headers.Authorization = `Bearer ${auth.token}`;
    const resp = await fetch(url, { headers });
    if (!resp.ok) {
      let detail = "导出失败";
      try {
        const j = await resp.json();
        if (j && j.detail) detail = j.detail;
      } catch (_e) {
        // ignore
      }
      throw new Error(detail);
    }
    const disposition = resp.headers.get("content-disposition") || "";
    const blob = await resp.blob();
    const downloadUrl = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = downloadUrl;
    a.download = extractFilename(disposition, includeMedia);
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    setTimeout(() => URL.revokeObjectURL(downloadUrl), 5000);
    toast.push(t("settings.backupExportDone"), "success");
  } catch (error) {
    toast.push((error as Error).message || t("settings.backupExportFailed"), "error");
  } finally {
    exportBusy.value = false;
  }
}

function extractFilename(disposition: string, includeMedia: boolean): string {
  const utf8 = /filename\*=UTF-8''([^;\s]+)/i.exec(disposition);
  if (utf8 && utf8[1]) {
    try {
      return decodeURIComponent(utf8[1]);
    } catch (_e) {
      return utf8[1];
    }
  }
  const ascii = /filename="?([^";]+)"?/i.exec(disposition);
  if (ascii && ascii[1]) return ascii[1];
  const stamp = new Date()
    .toISOString()
    .replace(/[-:]/g, "")
    .replace(/\..+$/, "")
    .replace("T", "-");
  return `media-portal-backup-${stamp}-${includeMedia ? "full" : "meta"}.tar.gz`;
}

function pickImportFile() {
  importInput.value?.click();
}

async function onImportFile(event: Event) {
  const input = event.target as HTMLInputElement;
  const file = input.files?.[0];
  input.value = "";
  if (!file) return;
  if (!window.confirm(t("settings.backupImportConfirm"))) return;
  importBusy.value = true;
  try {
    const result = await backupApi.importArchive(file, { replaceMedia: replaceMedia.value });
    toast.push(
      t("settings.backupImportDone", { parts: (result.restored || []).join("、") || "-" }),
      "success",
    );
    setTimeout(() => {
      window.location.reload();
    }, 800);
  } catch (error) {
    toast.push((error as Error).message || t("settings.backupImportFailed"), "error");
  } finally {
    importBusy.value = false;
  }
}

function exportSettings() {
  try {
    const payload = {
      version: 1,
      exportedAt: Date.now(),
      theme: ui.theme,
      themeColor: ui.themeColor,
      gridDensity: ui.gridDensity,
      gridMode: ui.gridMode,
      pageSize: ui.pageSize,
      statVisibility: ui.statVisibility,
    };
    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `media-portal-settings-${Date.now()}.json`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    setTimeout(() => URL.revokeObjectURL(url), 2000);
    toast.push(t("settings.settingsExportDone"), "success");
  } catch (error) {
    toast.push((error as Error).message || t("settings.settingsExportFailed"), "error");
  }
}

function pickSettingsFile() {
  settingsInput.value?.click();
}

async function onImportSettings(event: Event) {
  const input = event.target as HTMLInputElement;
  const file = input.files?.[0];
  input.value = "";
  if (!file) return;
  try {
    const text = await file.text();
    const data = JSON.parse(text) as Record<string, any>;
    if (typeof data !== "object" || data === null) throw new Error("invalid settings file");
    if (typeof data.theme === "string" && (data.theme === "dark" || data.theme === "light")) {
      ui.theme = data.theme;
      ui.applyTheme();
    }
    if (typeof data.themeColor === "string") ui.setThemeColor(data.themeColor as ThemeColor);
    if (typeof data.gridDensity === "string") ui.setGridDensity(data.gridDensity as GridDensity);
    if (typeof data.gridMode === "string") ui.setGridMode(data.gridMode as any);
    if (typeof data.pageSize === "number") {
      ui.setPageSize(data.pageSize);
      media.filters.page_size = ui.pageSize;
    }
    if (data.statVisibility && typeof data.statVisibility === "object") {
      emit("update-stat-visibility", data.statVisibility as Partial<StatVisibility>);
    }
    toast.push(t("settings.settingsImportDone"), "success");
  } catch (error) {
    toast.push((error as Error).message || t("settings.settingsImportFailed"), "error");
  }
}
</script>

<style scoped>
.switch-inline {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 12.5px;
  color: var(--text-muted);
  cursor: pointer;
}

.switch-inline input {
  width: auto;
  margin: 0;
  accent-color: var(--primary);
}
</style>

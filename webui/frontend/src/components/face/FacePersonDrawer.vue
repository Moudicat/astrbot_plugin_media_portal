<template>
  <transition name="drawer">
    <div v-if="visible" class="drawer-mask" @click.self="$emit('close')">
      <aside class="drawer face-drawer">
        <header>
          <h3>
            <Icon name="user" :size="16" style="vertical-align: -3px" />
            {{ headerTitle }}
          </h3>
          <button class="icon" :title="$t('drawer.close')" @click="$emit('close')">
            <Icon name="x" :size="16" />
          </button>
        </header>

        <div v-if="!person" class="empty">
          <div class="illus"><Icon name="file-question" :size="30" /></div>
          <strong>{{ $t("face.drawer.emptyTitle") }}</strong>
        </div>
        <template v-else>
          <div class="drawer-content">
            <section class="meta-block">
              <div class="face-summary">
                <div class="face-summary-thumb">
                  <img
                    v-if="person.sample_face_id"
                    :src="thumbUrl(person.sample_face_id)"
                    :alt="person.name || ''"
                  />
                  <div v-else class="face-thumb-placeholder">
                    <Icon name="image" :size="22" />
                  </div>
                </div>
                <div class="face-summary-meta">
                  <input
                    v-model="renameDraft"
                    class="face-rename-input"
                    :placeholder="$t('face.drawer.renamePlaceholder', { id: person.id })"
                    @keyup.enter="commitRename"
                  />
                  <div class="face-summary-row">
                    <span class="muted">
                      {{ $t("face.drawer.id", { id: person.id }) }}
                    </span>
                    <span class="muted">
                      {{ $t("face.drawer.faceCount", { count: person.face_count }) }}
                    </span>
                  </div>
                </div>
              </div>
              <div class="face-actions">
                <button class="primary" :disabled="!renameDirty" @click="commitRename">
                  <Icon name="save" :size="14" />
                  {{ $t("face.drawer.saveName") }}
                </button>
                <button class="ghost" @click="$emit('refresh')">
                  <Icon name="rotate-ccw" :size="14" />
                  {{ $t("face.drawer.refresh") }}
                </button>
                <button class="danger" @click="$emit('delete', person.id)">
                  <Icon name="trash-2" :size="14" />
                  {{ $t("face.drawer.delete") }}
                </button>
              </div>
            </section>

            <section class="meta-block">
              <h4 class="meta-title">
                {{ $t("face.drawer.facesTitle") }}
                <span v-if="selectedFaceIds.size" class="muted">
                  {{ $t("face.drawer.selectedFaces", { count: selectedFaceIds.size }) }}
                </span>
              </h4>
              <div v-if="selectedFaceIds.size" class="face-batchbar">
                <button class="ghost" @click="clearFaceSelection">
                  {{ $t("face.drawer.clearSelection") }}
                </button>
                <button class="primary" @click="commitSplit">
                  <Icon name="scissors" :size="14" />
                  {{ $t("face.drawer.splitToNew") }}
                </button>
              </div>
              <div class="face-grid">
                <div
                  v-for="face in faces"
                  :key="face.id"
                  class="face-cell"
                  :class="{ active: selectedFaceIds.has(face.id) }"
                  :title="$t('face.drawer.previewHint')"
                  @click="onCellClick(face)"
                >
                  <img
                    :src="thumbUrl(face.id)"
                    :alt="face.media?.filename || ''"
                    loading="lazy"
                    @error="onThumbError($event)"
                  />
                  <div class="face-cell-meta">
                    <span class="ellipsis" :title="face.media?.filename || ''">
                      {{ face.media?.filename || $t("face.drawer.unknownFile") }}
                    </span>
                    <span class="muted">
                      {{ scorePercent(face.det_score) }}
                    </span>
                  </div>
                  <button
                    class="plain face-cell-check"
                    type="button"
                    :class="{ on: selectedFaceIds.has(face.id) }"
                    :title="$t('face.drawer.selectFace')"
                    :aria-pressed="selectedFaceIds.has(face.id) ? 'true' : 'false'"
                    @click.stop="toggleFace(face.id)"
                  >
                    <Icon name="check" :size="12" />
                  </button>
                  <span class="face-cell-zoom" aria-hidden="true">
                    <Icon name="zoom-in" :size="14" />
                  </span>
                </div>
              </div>
            </section>
          </div>
        </template>
      </aside>
    </div>
  </transition>
</template>

<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import Icon from "@/components/common/Icon.vue";
import type { FacePerson, FaceItem } from "@/api/intelligence";
import { intelligenceApi } from "@/api/intelligence";

const { t } = useI18n();

interface Props {
  visible: boolean;
  person: FacePerson | null;
  faces: FaceItem[];
  readonlyToken?: string;
}

const props = withDefaults(defineProps<Props>(), {
  visible: false,
  person: null,
  faces: () => [],
  readonlyToken: "",
});

const emit = defineEmits<{
  (e: "close"): void;
  (e: "rename", payload: { id: number; name: string }): void;
  (e: "delete", id: number): void;
  (e: "split", payload: { personId: number; faceIds: number[] }): void;
  (e: "merge-into", payload: { sourceId: number; targetId: number }): void;
  (e: "refresh"): void;
  (e: "preview-media", face: FaceItem): void;
}>();

const renameDraft = ref("");
const selectedFaceIds = ref<Set<number>>(new Set());

watch(
  () => [props.person?.id, props.person?.name],
  () => {
    renameDraft.value = props.person?.name || "";
    selectedFaceIds.value = new Set();
  },
);

const headerTitle = computed(() => {
  if (!props.person) return t("face.drawer.emptyTitle");
  return props.person.name || t("face.unnamedPerson", { id: props.person.id });
});

const renameDirty = computed(() => {
  if (!props.person) return false;
  return (renameDraft.value || "").trim() !== (props.person.name || "");
});

function thumbUrl(faceId: number): string {
  return intelligenceApi.faceThumbUrl(faceId, props.readonlyToken);
}

function scorePercent(score: number): string {
  if (!Number.isFinite(score)) return "-";
  return `${Math.round(score * 100)}%`;
}

function onThumbError(event: Event) {
  const img = event.target as HTMLImageElement;
  img.style.opacity = "0.2";
}

function commitRename() {
  if (!props.person) return;
  if (!renameDirty.value) return;
  emit("rename", { id: props.person.id, name: (renameDraft.value || "").trim() });
}

function toggleFace(faceId: number) {
  const next = new Set(selectedFaceIds.value);
  if (next.has(faceId)) next.delete(faceId);
  else next.add(faceId);
  selectedFaceIds.value = next;
}

function onCellClick(face: FaceItem) {
  if (selectedFaceIds.value.size > 0) {
    toggleFace(face.id);
    return;
  }
  if (!face.media || !face.media.filename) {
    toggleFace(face.id);
    return;
  }
  emit("preview-media", face);
}

function clearFaceSelection() {
  selectedFaceIds.value = new Set();
}

function commitSplit() {
  if (!props.person) return;
  if (!selectedFaceIds.value.size) return;
  emit("split", {
    personId: props.person.id,
    faceIds: [...selectedFaceIds.value],
  });
  selectedFaceIds.value = new Set();
}
</script>

<style scoped>
.face-drawer .drawer-content {
  display: flex;
  flex-direction: column;
  gap: 18px;
  padding: 14px 16px 22px;
  overflow: auto;
}
.face-summary {
  display: flex;
  gap: 12px;
  align-items: center;
}
.face-summary-thumb {
  width: 72px;
  height: 72px;
  border-radius: 8px;
  overflow: hidden;
  background: color-mix(in srgb, var(--muted) 8%, transparent);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}
.face-summary-thumb img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}
.face-thumb-placeholder {
  color: var(--muted);
}
.face-summary-meta {
  display: flex;
  flex-direction: column;
  gap: 6px;
  flex: 1;
  min-width: 0;
}
.face-rename-input {
  width: 100%;
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: 8px;
  padding: 6px 10px;
  font-size: 14px;
  color: var(--text);
}
.face-summary-row {
  display: flex;
  gap: 10px;
  font-size: 12px;
  flex-wrap: wrap;
}
.face-actions {
  display: flex;
  gap: 8px;
  margin-top: 10px;
  flex-wrap: wrap;
}

.face-batchbar {
  display: flex;
  gap: 8px;
  margin-bottom: 8px;
  flex-wrap: wrap;
}

.face-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(96px, 1fr));
  gap: 8px;
}
.face-cell {
  position: relative;
  border-radius: 8px;
  overflow: hidden;
  cursor: pointer;
  background: var(--surface);
  border: 1px solid var(--line);
  transition: border-color 0.12s ease, transform 0.12s ease,
    box-shadow 0.12s ease;
}
.face-cell:hover {
  border-color: color-mix(in srgb, var(--primary) 30%, var(--line));
  transform: translateY(-1px);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.06);
}
.face-cell.active {
  border-color: var(--primary);
  box-shadow: 0 0 0 2px color-mix(in srgb, var(--primary) 25%, transparent);
}
.face-cell img {
  width: 100%;
  aspect-ratio: 1;
  object-fit: cover;
  display: block;
  transition: transform 0.3s ease;
}
.face-cell:hover img {
  transform: scale(1.04);
}
.face-cell-meta {
  display: flex;
  flex-direction: column;
  padding: 4px 6px;
  font-size: 11px;
}
.face-cell-meta .ellipsis {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.face-cell-check {
  position: absolute;
  top: 6px;
  right: 6px;
  width: 22px;
  height: 22px;
  min-width: 22px;
  min-height: 22px;
  flex: none;
  border-radius: 50%;
  border: 1.5px solid rgba(255, 255, 255, 0.85);
  background: rgba(15, 23, 42, 0.5);
  color: #fff;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 0;
  margin: 0;
  cursor: pointer;
  box-sizing: border-box;
  backdrop-filter: blur(4px);
  -webkit-backdrop-filter: blur(4px);
  z-index: 2;
  opacity: 0;
  transition: opacity 0.15s ease, background 0.15s ease, transform 0.15s ease;
}
.face-cell:hover .face-cell-check,
.face-cell.active .face-cell-check,
.face-cell-check.on {
  opacity: 1;
}
.face-cell-check.on {
  background: var(--primary);
  border-color: var(--primary);
}
.face-cell-check:hover {
  transform: scale(1.08);
}
.face-cell-check :deep(svg) {
  flex: none;
  display: block;
}
.face-cell-zoom {
  position: absolute;
  bottom: 26px;
  right: 6px;
  width: 22px;
  height: 22px;
  border-radius: 50%;
  background: rgba(15, 23, 42, 0.55);
  color: #fff;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  pointer-events: none;
  opacity: 0;
  transition: opacity 0.15s ease;
  backdrop-filter: blur(4px);
  -webkit-backdrop-filter: blur(4px);
  z-index: 1;
}
.face-cell:hover .face-cell-zoom {
  opacity: 1;
}
</style>

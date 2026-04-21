<template>
  <section style="display: flex; flex-direction: column; gap: 14px">
    <div class="panel" style="display: flex; flex-direction: column; gap: 10px">
      <div class="dup-title">
        <Icon name="check-circle" :size="16" />
        <strong>{{ $t("duplicates.modeExact") }}</strong>
      </div>
    </div>

    <div v-if="loading" class="panel empty">
      <span>{{ $t("common.loading") }}</span>
    </div>

    <div v-else-if="!groups.length" class="panel empty">
      <div class="illus"><Icon name="circle-check" :size="32" /></div>
      <strong>{{ $t("duplicates.emptyTitle") }}</strong>
      <span>{{ $t("duplicates.emptyHint") }}</span>
    </div>

    <div v-else style="display: flex; flex-direction: column; gap: 10px">
      <article
        v-for="group in groups"
        :key="group.group_key"
        class="panel"
        style="display: flex; flex-direction: column; gap: 8px"
      >
        <div style="display: flex; align-items: center; justify-content: space-between; gap: 8px">
          <strong>{{ $t("duplicates.groupExact", { count: group.count }) }}</strong>
          <span class="mono muted">{{ group.reason }}</span>
        </div>
        <div
          v-for="item in group.items"
          :key="`${group.group_key}:${item.id}`"
          class="dup-row"
        >
          <button class="dup-preview" @click="layout.previewItem(item)">
            <img v-if="item.kind === 'image'" :src="previewUrl(item)" :alt="item.filename" />
            <video
              v-else-if="item.kind === 'video'"
              :src="previewUrl(item)"
              muted
              preload="metadata"
            ></video>
            <div v-else class="dup-preview-fallback">
              <Icon :name="item.kind === 'audio' ? 'music' : 'file'" :size="16" />
            </div>
          </button>
          <div class="dup-meta">
            <strong class="ellipsis" :title="item.filename">{{ item.filename }}</strong>
            <div class="dup-sub">
              <span>{{ item.category }}</span>
              <span class="dot"></span>
              <span class="mono">{{ item.size_human || formatSize(item.size || 0) }}</span>
              <template v-if="item.created_at">
                <span class="dot"></span>
                <span class="mono">{{ formatDateTimeShort(item.created_at) }}</span>
              </template>
            </div>
          </div>
          <div class="dup-actions">
            <button class="sm" @click="layout.previewItem(item)">
              <Icon name="eye" :size="13" />
              {{ $t("duplicates.preview") }}
            </button>
            <button class="sm" @click="layout.openDetail(item)">
              <Icon name="settings-2" :size="13" />
              {{ $t("duplicates.detail") }}
            </button>
            <button class="danger sm" @click="remove(item.id)">
              <Icon name="trash-2" :size="13" />
              {{ $t("duplicates.delete") }}
            </button>
          </div>
        </div>
      </article>
    </div>

    <footer v-if="totalPages > 0" class="pager">
      <button class="icon sm" :disabled="page <= 1" @click="reload(page - 1)">
        <Icon name="chevron-left" :size="15" />
      </button>
      <span>{{ $t("duplicates.pagerText", { page, total: totalPages, count: total }) }}</span>
      <button class="icon sm" :disabled="page >= totalPages" @click="reload(page + 1)">
        <Icon name="chevron-right" :size="15" />
      </button>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { inject, onMounted, ref } from "vue";
import { useI18n } from "vue-i18n";
import Icon from "@/components/common/Icon.vue";
import { mediaApi } from "@/api/media";
import type { DuplicateGroup } from "@/api/types";
import { useToastStore } from "@/stores/toast";
import { useConfirmStore } from "@/stores/confirm";
import { useAuthStore } from "@/stores/auth";
import { formatDateTimeShort, formatSize } from "@/utils/format";
import { buildMediaDirectUrl } from "@/utils/url";

interface LayoutActions {
  openDetail: (item: any) => void;
  previewItem: (item: any) => void;
}

const layout = inject<LayoutActions>("layoutActions")!;
const { t } = useI18n();
const toast = useToastStore();
const confirm = useConfirmStore();
const auth = useAuthStore();

const loading = ref(false);
const groups = ref<DuplicateGroup[]>([]);
const page = ref(1);
const total = ref(0);
const totalPages = ref(0);

async function reload(nextPage = 1) {
  loading.value = true;
  try {
    const data = await mediaApi.duplicates({
      mode: "exact",
      page: nextPage,
      page_size: 20,
    });
    groups.value = data.items || [];
    page.value = data.page || nextPage;
    total.value = data.total || 0;
    totalPages.value = data.total_pages || 0;
  } catch (error) {
    toast.push((error as Error).message, "error");
  } finally {
    loading.value = false;
  }
}

function previewUrl(item: any): string {
  if (item && item.public_url) return String(item.public_url);
  return buildMediaDirectUrl(
    String(item?.category || ""),
    String(item?.filename || ""),
    auth.readonlyToken,
  );
}

async function remove(id: string | number) {
  const ok = await confirm.confirm({
    title: t("duplicates.deleteTitle"),
    message: t("duplicates.deleteConfirm"),
    confirmText: t("duplicates.delete"),
    tone: "danger",
    icon: "trash-2",
  });
  if (!ok) return;
  try {
    await mediaApi.remove(id);
    toast.push(t("duplicates.deleteDone"), "success");
    await reload(page.value);
  } catch (error) {
    toast.push((error as Error).message, "error");
  }
}

onMounted(() => {
  reload(1).catch((error) => toast.push((error as Error).message, "error"));
});
</script>

<style scoped>
.dup-title {
  display: inline-flex;
  align-items: center;
  gap: 8px;
}

.dup-row {
  display: grid;
  grid-template-columns: 64px minmax(0, 1fr) auto;
  gap: 10px;
  align-items: center;
}

.dup-preview {
  width: 64px;
  height: 64px;
  border: 1px solid var(--line-soft);
  border-radius: 10px;
  overflow: hidden;
  background: var(--surface-soft);
  padding: 0;
}

.dup-preview img,
.dup-preview video {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}

.dup-preview-fallback {
  width: 100%;
  height: 100%;
  display: grid;
  place-items: center;
  color: var(--text-muted);
}

.dup-meta {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.dup-sub {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
  color: var(--text-muted);
  font-size: 12px;
}

.dup-sub .dot {
  width: 3px;
  height: 3px;
  border-radius: 999px;
  background: currentColor;
  opacity: 0.5;
}

.dup-actions {
  display: inline-flex;
  gap: 8px;
  flex-wrap: wrap;
  justify-content: flex-end;
}
</style>

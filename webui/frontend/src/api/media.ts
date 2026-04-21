import { buildQuery, request } from "./client";
import type {
  DuplicateGroupsResp,
  MediaItem,
  MediaListResp,
  MediaStats,
  PortalConfig,
  SaveUrlPayload,
  TrashListResp,
  TrashStatsResp,
} from "./types";

export interface MediaQuery {
  category?: string;
  kind?: string;
  query?: string;
  page?: number;
  page_size?: number;
}

export interface TrashQuery {
  category?: string;
  query?: string;
  page?: number;
  page_size?: number;
}

export interface DuplicateQuery {
  mode?: "exact" | string;
  page?: number;
  page_size?: number;
}

export const mediaApi = {
  config: () => request<PortalConfig>("/api/config"),
  stats: () => request<MediaStats>("/api/stats"),
  list: (q: MediaQuery) =>
    request<MediaListResp>(`/api/media${buildQuery(q as Record<string, string | number>)}`),
  detail: (id: string | number) => request<MediaItem>(`/api/media/${id}`),
  patch: (id: string | number, body: Partial<MediaItem> & Record<string, any>) =>
    request<MediaItem>(`/api/media/${id}`, { method: "PATCH", body }),
  remove: (id: string | number) =>
    request<{ deleted: boolean; soft_deleted?: boolean; trash_id?: number }>(
      `/api/media/${id}`,
      { method: "DELETE" },
    ),
  saveUrl: (payload: SaveUrlPayload) =>
    request<MediaItem>("/api/media/save-url", { method: "POST", body: payload }),
  duplicates: (q: DuplicateQuery) =>
    request<DuplicateGroupsResp>(`/api/media/duplicates${buildQuery(q as Record<string, string | number>)}`),
  listTrash: (q: TrashQuery) =>
    request<TrashListResp>(`/api/trash${buildQuery(q as Record<string, string | number>)}`),
  trashStats: () => request<TrashStatsResp>("/api/trash/stats"),
  restoreTrash: (trashId: string | number, body: { category?: string; filename?: string } = {}) =>
    request<MediaItem>(`/api/trash/${trashId}/restore`, { method: "POST", body }),
  purgeTrash: (trashId: string | number) =>
    request<{ deleted: boolean }>(`/api/trash/${trashId}`, { method: "DELETE" }),
  purgeExpiredTrash: () => request<{ purged: number }>("/api/trash/purge-expired", { method: "POST" }),
  getTrashSettings: () => request<{ trash_retention_days: number }>("/api/settings/trash"),
  setTrashSettings: (days: number) =>
    request<{ trash_retention_days: number }>("/api/settings/trash", {
      method: "PATCH",
      body: { trash_retention_days: days },
    }),
};

export interface BackupImportResult {
  restored: string[];
  replace_media: boolean;
  bytes: number;
}

export const backupApi = {
  exportUrl: (includeMedia = true) =>
    `/api/backup/export${buildQuery({ include_media: includeMedia ? 1 : 0 })}`,
  importArchive: async (
    file: File,
    opts: { replaceMedia?: boolean } = {},
  ): Promise<BackupImportResult> => {
    const form = new FormData();
    form.append("archive", file, file.name || "backup.tar.gz");
    form.append("replace_media", opts.replaceMedia ? "1" : "0");
    return request<BackupImportResult>("/api/backup/import", {
      method: "POST",
      form,
    });
  },
};

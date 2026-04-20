import { buildQuery, request } from "./client";
import type { MediaItem, MediaListResp, MediaStats, PortalConfig, SaveUrlPayload } from "./types";

export interface MediaQuery {
  category?: string;
  kind?: string;
  query?: string;
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
  remove: (id: string | number) => request<void>(`/api/media/${id}`, { method: "DELETE" }),
  saveUrl: (payload: SaveUrlPayload) =>
    request<unknown>("/api/media/save-url", { method: "POST", body: payload }),
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

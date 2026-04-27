import { request } from "./client";

export type ModelStatus =
  | "not_downloaded"
  | "partial"
  | "downloading"
  | "ready"
  | "failed"
  | "cancelled"
  | "corrupted";

export interface ModelSnapshot {
  key: string;
  capability: "clip" | "face";
  display_name: string;
  description: string;
  homepage: string;
  license: string;
  status: ModelStatus;
  files_total: number;
  files_complete: number;
  bytes_total: number | null;
  bytes_complete: number;
  extra_requirements: string[];
  last_error: string;
  current_file: string;
  progress_bytes: number;
  progress_total: number | null;
  files_done: number;
  last_event_at: number;
  target_dir: string;
}

export interface IntelligenceListResp {
  feature_enabled: boolean;
  clip_enabled: boolean;
  face_enabled: boolean;
  hf_mirror_url: string;
  models: ModelSnapshot[];
}

export interface ClipStatusResp {
  engine_ready: boolean;
  indexed_count: number;
  scanning: boolean;
  stats: {
    indexed?: number;
    skipped?: number;
    failed?: number;
    last_run_at?: number;
    last_error?: string;
  };
}

export interface ClipSearchResultItem {
  id: number;
  filename: string;
  category: string;
  kind: string;
  rel_path: string;
  abs_path: string;
  size: number;
  size_human?: string;
  description?: string;
  tags?: string[];
  score: number;
}

export interface ClipSearchResp {
  results: ClipSearchResultItem[];
  engine_ready: boolean;
  query?: string;
}

export interface FaceStatusResp {
  engine_ready: boolean;
  face_count: number;
  person_count: number;
  scanning: boolean;
  stats: {
    media_processed?: number;
    faces_indexed?: number;
    skipped?: number;
    failed?: number;
    last_run_at?: number;
    last_error?: string;
  };
}

export interface FacePerson {
  id: number;
  name: string;
  sample_face_id: number | null;
  face_count: number;
  created_at: number;
  updated_at: number;
}

export interface FaceMediaMeta {
  id?: number;
  filename?: string;
  category?: string;
  kind?: string;
  rel_path?: string;
  size?: number;
  size_human?: string;
  tags?: string[];
}

export interface FaceItem {
  id: number;
  media_id: number;
  sha256: string;
  person_id: number | null;
  bbox: number[];
  kps: number[][];
  det_score: number;
  thumb_path: string;
  model_version: string;
  created_at: number;
  media?: FaceMediaMeta;
}

export interface FacePersonDetailResp {
  person: FacePerson;
  faces: FaceItem[];
}

export interface FaceReclusterResp {
  persons_before: number;
  persons_after: number;
  merged: number;
  created: number;
  moved_faces: number;
}

export const intelligenceApi = {
  listModels: () => request<IntelligenceListResp>("/api/intelligence/models"),
  startDownload: (key: string) =>
    request<{ started: boolean; model: ModelSnapshot | null }>(
      `/api/intelligence/models/${encodeURIComponent(key)}/download`,
      { method: "POST" },
    ),
  cancelDownload: (key: string) =>
    request<{ cancelled: boolean; model: ModelSnapshot | null }>(
      `/api/intelligence/models/${encodeURIComponent(key)}/cancel`,
      { method: "POST" },
    ),
  removeModel: (key: string) =>
    request<{ removed: boolean; model: ModelSnapshot | null }>(
      `/api/intelligence/models/${encodeURIComponent(key)}`,
      { method: "DELETE" },
    ),
  patchSettings: (payload: {
    feature_enabled?: boolean;
    clip_enabled?: boolean;
    face_enabled?: boolean;
    hf_mirror_url?: string;
    max_concurrent_downloads?: number;
  }) =>
    request<{
      feature_enabled: boolean;
      clip_enabled: boolean;
      face_enabled: boolean;
      hf_mirror_url: string;
    }>("/api/intelligence/settings", { method: "PATCH", body: payload }),
  clipStatus: () => request<ClipStatusResp>("/api/intelligence/clip/status"),
  clipScan: () =>
    request<{ started: boolean }>("/api/intelligence/clip/scan", {
      method: "POST",
    }),
  clipSearch: (query: string, topK = 20) =>
    request<ClipSearchResp>(
      `/api/intelligence/clip/search?q=${encodeURIComponent(query)}&top_k=${topK}`,
    ),
  faceStatus: () => request<FaceStatusResp>("/api/intelligence/face/status"),
  faceScan: () =>
    request<{ started: boolean }>("/api/intelligence/face/scan", {
      method: "POST",
    }),
  faceRecluster: () =>
    request<FaceReclusterResp>("/api/intelligence/face/recluster", {
      method: "POST",
    }),
  faceListPersons: () =>
    request<{ persons: FacePerson[] }>("/api/intelligence/face/persons"),
  facePersonDetail: (personId: number, limit = 200, offset = 0) =>
    request<FacePersonDetailResp>(
      `/api/intelligence/face/persons/${personId}?limit=${limit}&offset=${offset}`,
    ),
  facePersonRename: (personId: number, name: string, sampleFaceId?: number) =>
    request<{ person: FacePerson | null }>(
      `/api/intelligence/face/persons/${personId}`,
      {
        method: "PATCH",
        body: { name, sample_face_id: sampleFaceId },
      },
    ),
  facePersonsMerge: (targetId: number, sourceIds: number[]) =>
    request<{ merged: boolean; moved_faces: number }>(
      `/api/intelligence/face/persons/merge`,
      {
        method: "POST",
        body: { target_id: targetId, source_ids: sourceIds },
      },
    ),
  facePersonSplit: (personId: number, faceIds: number[], name = "") =>
    request<{ new_person_id: number | null }>(
      `/api/intelligence/face/persons/${personId}/split`,
      {
        method: "POST",
        body: { face_ids: faceIds, name },
      },
    ),
  facePersonDelete: (personId: number) =>
    request<{ deleted: boolean }>(
      `/api/intelligence/face/persons/${personId}`,
      { method: "DELETE" },
    ),
  faceThumbUrl: (faceId: number, token?: string) => {
    const base = `/api/intelligence/face/${faceId}/thumb`;
    return token ? `${base}?token=${encodeURIComponent(token)}` : base;
  },
  faceCleanupOrphans: () =>
    request<{ removed: number }>("/api/intelligence/face/cleanup", {
      method: "POST",
    }),
  faceRebuildThumbs: () =>
    request<{ processed: number; failed: number }>(
      "/api/intelligence/face/thumbs/rebuild",
      { method: "POST" },
    ),
};

import { buildQuery, request } from "./client";
import type { DataTextResp, DataTreeResp } from "./types";

export const dataApi = {
  tree: (path: string) => request<DataTreeResp>(`/api/data-tree${buildQuery({ path })}`),
  text: (path: string) => request<DataTextResp>(`/api/data-text${buildQuery({ path })}`),
};

export function buildDataFileUrl(
  path: string,
  opts: { token?: string; download?: boolean } = {},
): string {
  const params = new URLSearchParams();
  params.set("path", path);
  if (opts.token) params.set("token", opts.token);
  if (opts.download) params.set("download", "1");
  return `/api/data-file?${params.toString()}`;
}

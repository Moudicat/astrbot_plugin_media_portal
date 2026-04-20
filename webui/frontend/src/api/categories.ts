import { request } from "./client";
import type { CategoryItem, CategoryListResp } from "./types";

export interface CreateCategoryPayload {
  category: string;
  description?: string;
}

export interface UpdateCategoryPayload {
  new_name?: string;
  description?: string;
}

export interface PruneCategoriesResp {
  removed: string[];
  removed_count: number;
}

export const categoriesApi = {
  list: () => request<CategoryListResp>("/api/categories"),
  create: (payload: CreateCategoryPayload) =>
    request<CategoryItem>("/api/categories", { method: "POST", body: payload }),
  update: (name: string, payload: UpdateCategoryPayload) =>
    request<CategoryItem>(`/api/categories/${encodeURIComponent(name)}`, {
      method: "PATCH",
      body: payload,
    }),
  remove: (name: string, removeFiles = true) =>
    request<{ deleted_rows?: number }>(
      `/api/categories/${encodeURIComponent(name)}${removeFiles ? "" : "?remove_files=false"}`,
      { method: "DELETE" },
    ),
  prune: () => request<PruneCategoriesResp>("/api/categories/prune", { method: "POST" }),
};

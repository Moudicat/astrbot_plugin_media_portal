import { defineStore } from "pinia";
import { mediaApi } from "@/api/media";
import { intelligenceApi } from "@/api/intelligence";
import type { MediaItem, MediaStats } from "@/api/types";
import { safeGet } from "@/utils/storage";

function initialPageSize(): number {
  const raw = safeGet<number>("media_portal_page_size", 40);
  const allowed = [20, 40, 60, 80, 120];
  return allowed.includes(raw) ? raw : 40;
}

export type SearchMode = "text" | "clip";

const CLIP_DEFAULT_TOP_K = 60;

export interface MediaFilters {
  category: string;
  query: string;
  kind: string;
  page: number;
  page_size: number;
  searchMode: SearchMode;
}

export const useMediaStore = defineStore("media", {
  state: () => ({
    items: [] as MediaItem[],
    stats: {} as MediaStats,
    selectedIds: [] as Array<string | number>,
    loading: false,
    filters: {
      category: "",
      query: "",
      kind: "",
      page: 1,
      page_size: initialPageSize(),
      searchMode: "text" as SearchMode,
    } as MediaFilters,
    pagination: {
      total: 0,
      totalPages: 0,
    },
  }),
  getters: {
    selectedCount: (state) => state.selectedIds.length,
  },
  actions: {
    async fetchList() {
      this.loading = true;
      try {
        if (this.filters.searchMode === "clip") {
          const text = (this.filters.query || "").trim();
          if (!text) {
            this.items = [];
            this.pagination.total = 0;
            this.pagination.totalPages = 0;
            return;
          }
          const data = await intelligenceApi.clipSearch(text, CLIP_DEFAULT_TOP_K);
          const results = (data.results || []).map((r) => ({
            id: r.id,
            filename: r.filename,
            category: r.category,
            kind: (r.kind || "image") as MediaItem["kind"],
            size: r.size,
            size_human: r.size_human,
            description: r.description,
            tags: r.tags,
            score: r.score,
          })) as MediaItem[];
          this.items = results;
          this.pagination.total = results.length;
          this.pagination.totalPages = results.length ? 1 : 0;
          this.filters.page = 1;
          const idSet = new Set(results.map((item) => item.id));
          this.selectedIds = this.selectedIds.filter((id) => idSet.has(id));
          return;
        }

        const data = await mediaApi.list({
          category: this.filters.category,
          kind: this.filters.kind,
          query: this.filters.query,
          page: this.filters.page,
          page_size: this.filters.page_size,
        });
        this.items = data.items || [];
        this.pagination.total = data.total || 0;
        this.pagination.totalPages = data.total_pages || 0;
        const idSet = new Set(this.items.map((item) => item.id));
        this.selectedIds = this.selectedIds.filter((id) => idSet.has(id));
      } finally {
        this.loading = false;
      }
    },
    async fetchStats() {
      try {
        this.stats = await mediaApi.stats();
      } catch (_e) {
        this.stats = {};
      }
    },
    selectCategory(category: string) {
      this.filters.category = category;
      this.filters.page = 1;
    },
    setSearch(query: string) {
      this.filters.query = query || "";
      this.filters.page = 1;
    },
    setSearchMode(mode: SearchMode) {
      const next: SearchMode = mode === "clip" ? "clip" : "text";
      if (this.filters.searchMode === next) return;
      this.filters.searchMode = next;
      this.filters.page = 1;
      this.selectedIds = [];
    },
    setKind(kind: string) {
      this.filters.kind = kind || "";
      this.filters.page = 1;
    },
    setPage(page: number) {
      this.filters.page = page;
    },
    toggleSelect(id: string | number) {
      if (this.selectedIds.includes(id)) {
        this.selectedIds = this.selectedIds.filter((x) => x !== id);
      } else {
        this.selectedIds.push(id);
      }
    },
    clearSelection() {
      this.selectedIds = [];
    },
    async detail(id: string | number) {
      return await mediaApi.detail(id);
    },
    async patch(id: string | number, payload: Partial<MediaItem> & Record<string, any>) {
      return await mediaApi.patch(id, payload);
    },
    async remove(id: string | number) {
      return await mediaApi.remove(id);
    },
  },
});

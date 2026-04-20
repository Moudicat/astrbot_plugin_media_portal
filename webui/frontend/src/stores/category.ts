import { defineStore } from "pinia";
import { categoriesApi } from "@/api/categories";
import type { CreateCategoryPayload, UpdateCategoryPayload } from "@/api/categories";
import type { CategoryItem } from "@/api/types";

export const useCategoryStore = defineStore("category", {
  state: () => ({
    items: [] as CategoryItem[],
  }),
  actions: {
    async fetch() {
      const data = await categoriesApi.list();
      this.items = data.items || [];
    },
    async create(payload: CreateCategoryPayload) {
      await categoriesApi.create(payload);
      await this.fetch();
    },
    async update(name: string, payload: UpdateCategoryPayload) {
      return await categoriesApi.update(name, payload);
    },
    async remove(name: string, removeFiles = true) {
      return await categoriesApi.remove(name, removeFiles);
    },
    async prune() {
      return await categoriesApi.prune();
    },
  },
});

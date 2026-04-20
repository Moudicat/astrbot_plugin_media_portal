import { defineStore } from "pinia";
import { mediaApi } from "@/api/media";
import { useAuthStore } from "./auth";
import type { PortalConfig } from "@/api/types";

function defaultConfig(): PortalConfig {
  return {
    access_urls: [],
    public_base_url: "",
    expose_astrbot_data: true,
    max_file_size_mb: 500,
    max_file_size_bytes: 500 * 1024 * 1024,
  };
}

export const useConfigStore = defineStore("config", {
  state: () => ({
    config: defaultConfig(),
  }),
  getters: {
    canDataBrowse: (state): boolean => !!state.config.expose_astrbot_data,
    maxMb: (state): number => state.config.max_file_size_mb || 500,
    maxBytes: (state): number =>
      state.config.max_file_size_bytes || (state.config.max_file_size_mb || 500) * 1024 * 1024,
    publicBaseUrl: (state): string => state.config.public_base_url || "",
  },
  actions: {
    async fetch() {
      const data = await mediaApi.config();
      const maxMb = Number(data.max_file_size_mb) > 0 ? Number(data.max_file_size_mb) : 500;
      const maxBytes =
        Number(data.max_file_size_bytes) > 0
          ? Number(data.max_file_size_bytes)
          : maxMb * 1024 * 1024;
      this.config = {
        ...this.config,
        ...data,
        max_file_size_mb: maxMb,
        max_file_size_bytes: maxBytes,
      };

      // /api/config 也会返回 readonly_token / data_token（供生成直链使用）
      const authStore = useAuthStore();
      if (data.readonly_token) authStore.readonlyToken = data.readonly_token;
      if (data.data_token) authStore.dataToken = data.data_token;
      authStore.persist();
    },
  },
});

import { defineStore } from "pinia";
import { authApi } from "@/api/auth";
import { safeGet, safeSet } from "@/utils/storage";

const AUTH_KEY = "media_portal_auth";

interface AuthRecord {
  token: string;
  readonlyToken: string;
  dataToken: string;
}

function loadInitial(): AuthRecord {
  const data = safeGet<Partial<AuthRecord>>(AUTH_KEY, {});
  return {
    token: typeof data.token === "string" ? data.token : "",
    readonlyToken: typeof data.readonlyToken === "string" ? data.readonlyToken : "",
    dataToken: typeof data.dataToken === "string" ? data.dataToken : "",
  };
}

export const useAuthStore = defineStore("auth", {
  state: () => ({
    ...loadInitial(),
    loginLoading: false,
    loginError: "",
  }),
  getters: {
    isAuthenticated: (state): boolean => !!state.token,
  },
  actions: {
    persist() {
      if (!this.token) {
        safeSet(AUTH_KEY, null);
        return;
      }
      safeSet(AUTH_KEY, {
        token: this.token,
        readonlyToken: this.readonlyToken,
        dataToken: this.dataToken,
      });
    },
    setTokens(payload: { token: string; readonly_token?: string; data_token?: string }) {
      this.token = payload.token || "";
      this.readonlyToken = payload.readonly_token || "";
      this.dataToken = payload.data_token || "";
      this.persist();
    },
    async login(password: string) {
      this.loginLoading = true;
      this.loginError = "";
      try {
        const result = await authApi.login(password);
        this.setTokens(result);
        return result;
      } catch (error) {
        this.loginError = (error as Error).message;
        throw error;
      } finally {
        this.loginLoading = false;
      }
    },
    async logout(callServer = true) {
      if (callServer && this.token) {
        try {
          await authApi.logout();
        } catch (_e) {
          // ignore
        }
      }
      this.token = "";
      this.readonlyToken = "";
      this.dataToken = "";
      this.persist();
    },
  },
});

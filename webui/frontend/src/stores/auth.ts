import { defineStore } from "pinia";
import { authApi } from "@/api/auth";
import type { LoginChallengeResp, LoginSessionResp } from "@/api/types";
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

interface PendingChallenge {
  token: string;
  issuer: string;
  account: string;
  expiresAt: number;
}

function isChallenge(payload: any): payload is LoginChallengeResp {
  return !!payload && payload.challenge === "totp" && typeof payload.challenge_token === "string";
}

export const useAuthStore = defineStore("auth", {
  state: () => ({
    ...loadInitial(),
    loginLoading: false,
    loginError: "",
    pendingChallenge: null as PendingChallenge | null,
  }),
  getters: {
    isAuthenticated: (state): boolean => !!state.token,
    hasTotpChallenge: (state): boolean => !!state.pendingChallenge,
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
    setTokens(payload: LoginSessionResp) {
      this.token = payload.token || "";
      this.readonlyToken = payload.readonly_token || "";
      this.dataToken = payload.data_token || "";
      this.pendingChallenge = null;
      this.persist();
    },
    clearChallenge() {
      this.pendingChallenge = null;
    },
    async login(password: string) {
      this.loginLoading = true;
      this.loginError = "";
      try {
        const result = await authApi.login(password);
        if (isChallenge(result)) {
          const expiresAt = Date.now() + Math.max(60, Number(result.expires_in || 300)) * 1000;
          this.pendingChallenge = {
            token: result.challenge_token,
            issuer: result.issuer || "",
            account: result.account || "",
            expiresAt,
          };
          return result;
        }
        this.setTokens(result as LoginSessionResp);
        return result;
      } catch (error) {
        this.loginError = (error as Error).message;
        throw error;
      } finally {
        this.loginLoading = false;
      }
    },
    async verifyTotp(payload: { code?: string; recoveryCode?: string }) {
      if (!this.pendingChallenge) {
        throw new Error("缺少 TOTP 登录会话，请重新输入密码。");
      }
      this.loginLoading = true;
      this.loginError = "";
      try {
        const session = await authApi.loginTotp({
          challengeToken: this.pendingChallenge.token,
          code: payload.code,
          recoveryCode: payload.recoveryCode,
        });
        this.setTokens(session);
        return session;
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
      this.pendingChallenge = null;
      this.persist();
    },
  },
});

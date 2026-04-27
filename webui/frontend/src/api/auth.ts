import { request } from "./client";
import type { LoginResp, LoginSessionResp } from "./types";

export const authApi = {
  login: (password: string) =>
    request<LoginResp>("/api/login", {
      method: "POST",
      body: { password },
      auth: false,
    }),
  loginTotp: (payload: {
    challengeToken: string;
    code?: string;
    recoveryCode?: string;
  }) =>
    request<LoginSessionResp>("/api/login/totp", {
      method: "POST",
      body: {
        challenge_token: payload.challengeToken,
        code: payload.code || "",
        recovery_code: payload.recoveryCode || "",
      },
      auth: false,
    }),
  logout: () => request<void>("/api/logout", { method: "POST" }),
};

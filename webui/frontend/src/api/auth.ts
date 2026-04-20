import { request } from "./client";
import type { LoginResp } from "./types";

export const authApi = {
  login: (password: string) =>
    request<LoginResp>("/api/login", {
      method: "POST",
      body: { password },
      auth: false,
    }),
  logout: () => request<void>("/api/logout", { method: "POST" }),
};

import { request } from "./client";
import type {
  TotpConfirmResp,
  TotpRegenerateResp,
  TotpSetupResp,
  TotpStatus,
} from "./types";

export const accountApi = {
  totpStatus: () => request<TotpStatus>("/api/account/totp/status"),
  totpSetup: () =>
    request<TotpSetupResp>("/api/account/totp/setup", { method: "POST" }),
  totpCancelSetup: () =>
    request<{ cancelled: boolean }>("/api/account/totp/cancel-setup", {
      method: "POST",
    }),
  totpConfirm: (code: string) =>
    request<TotpConfirmResp>("/api/account/totp/confirm", {
      method: "POST",
      body: { code },
    }),
  totpDisable: (payload: { code?: string; recoveryCode?: string }) =>
    request<{ enabled: boolean }>("/api/account/totp/disable", {
      method: "POST",
      body: {
        code: payload.code || "",
        recovery_code: payload.recoveryCode || "",
      },
    }),
  totpRegenerateRecovery: (code: string) =>
    request<TotpRegenerateResp>("/api/account/totp/regenerate-recovery", {
      method: "POST",
      body: { code },
    }),
};

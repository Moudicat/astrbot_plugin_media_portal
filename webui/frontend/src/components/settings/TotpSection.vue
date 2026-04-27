<template>
  <section class="settings-section totp-section">
    <h4>{{ $t("settings.totp.title") }}</h4>

    <div v-if="!featureEnabled" class="totp-banner muted">
      <Icon name="info" :size="14" />
      <span>{{ $t("settings.totp.featureDisabled") }}</span>
    </div>

    <template v-else>
      <div class="settings-row">
        <div class="label">
          <strong>{{ $t("settings.totp.statusLabel") }}</strong>
          <small>
            <template v-if="status?.enabled">
              {{
                $t("settings.totp.statusEnabledHint", {
                  account: status.account,
                  remaining: status.remaining_recovery_codes,
                })
              }}
            </template>
            <template v-else>
              {{ $t("settings.totp.statusDisabledHint") }}
            </template>
          </small>
        </div>
        <div class="settings-actions-row">
          <span
            class="totp-status-pill"
            :class="{ on: status?.enabled, off: !status?.enabled }"
          >
            <Icon
              :name="status?.enabled ? 'shield-check' : 'shield-off'"
              :size="13"
            />
            {{
              status?.enabled
                ? $t("settings.totp.statusEnabled")
                : $t("settings.totp.statusDisabled")
            }}
          </span>
          <button
            v-if="!status?.enabled"
            class="primary"
            :disabled="busy"
            @click="startSetup"
          >
            <Icon name="qr-code" :size="14" />
            <span>{{ $t("settings.totp.enable") }}</span>
          </button>
          <button
            v-else
            class="ghost danger"
            :disabled="busy"
            @click="openDisable"
          >
            <Icon name="shield-off" :size="14" />
            <span>{{ $t("settings.totp.disable") }}</span>
          </button>
        </div>
      </div>

      <div v-if="status?.enabled" class="settings-row">
        <div class="label">
          <strong>{{ $t("settings.totp.recoveryLabel") }}</strong>
          <small>{{ $t("settings.totp.recoveryHint") }}</small>
        </div>
        <div class="settings-actions-row">
          <button class="ghost" :disabled="busy" @click="openRegenerate">
            <Icon name="rotate-ccw" :size="14" />
            <span>{{ $t("settings.totp.recoveryRegen") }}</span>
          </button>
        </div>
      </div>

      <transition name="fade">
        <div v-if="setup" class="totp-setup">
          <div class="totp-setup-grid">
            <div class="totp-qr" v-html="setup.qrcode_svg"></div>
            <div class="totp-setup-meta">
              <p class="muted small">{{ $t("settings.totp.setupQrHint") }}</p>
              <p>
                <strong>{{ $t("settings.totp.setupAccount") }}</strong>
                <span class="mono">{{ setup.issuer }}:{{ setup.account }}</span>
              </p>
              <p>
                <strong>{{ $t("settings.totp.setupSecret") }}</strong>
                <code class="mono">{{ formatSecret(setup.secret) }}</code>
                <button
                  class="ghost xs"
                  type="button"
                  :title="$t('common.copy')"
                  @click="copy(setup.secret)"
                >
                  <Icon name="copy" :size="12" />
                </button>
              </p>
              <label class="totp-input-label" for="setup-code">
                {{ $t("settings.totp.setupVerifyLabel") }}
              </label>
              <div class="totp-code-row">
                <input
                  id="setup-code"
                  v-model="setupCode"
                  type="tel"
                  inputmode="numeric"
                  maxlength="8"
                  placeholder="000000"
                  :disabled="busy"
                  @keyup.enter="confirmSetup"
                />
                <button class="primary" :disabled="busy || !setupCode.trim()" @click="confirmSetup">
                  <Icon name="check" :size="14" />
                  <span>{{ $t("settings.totp.setupConfirm") }}</span>
                </button>
                <button class="ghost" :disabled="busy" @click="cancelSetup">
                  <Icon name="x" :size="14" />
                  <span>{{ $t("common.cancel") }}</span>
                </button>
              </div>
            </div>
          </div>
        </div>
      </transition>

      <transition name="fade">
        <div v-if="disablePrompt" class="totp-modal-section">
          <h5>{{ $t("settings.totp.disableTitle") }}</h5>
          <p class="muted small">{{ $t("settings.totp.disableHint") }}</p>
          <div class="totp-mode-tabs">
            <button
              type="button"
              :class="{ active: !disableUseRecovery }"
              @click="disableUseRecovery = false"
            >
              {{ $t("settings.totp.useCode") }}
            </button>
            <button
              type="button"
              :class="{ active: disableUseRecovery }"
              @click="disableUseRecovery = true"
            >
              {{ $t("settings.totp.useRecovery") }}
            </button>
          </div>
          <div class="totp-code-row">
            <input
              v-model="disableCode"
              :type="disableUseRecovery ? 'text' : 'tel'"
              inputmode="numeric"
              :maxlength="disableUseRecovery ? 16 : 8"
              :placeholder="disableUseRecovery ? $t('settings.totp.recoveryPlaceholder') : '000000'"
              :disabled="busy"
              @keyup.enter="confirmDisable"
            />
            <button class="ghost danger" :disabled="busy || !disableCode.trim()" @click="confirmDisable">
              <Icon name="shield-off" :size="14" />
              <span>{{ $t("settings.totp.disable") }}</span>
            </button>
            <button class="ghost" :disabled="busy" @click="closeDisable">
              <Icon name="x" :size="14" />
              <span>{{ $t("common.cancel") }}</span>
            </button>
          </div>
        </div>
      </transition>

      <transition name="fade">
        <div v-if="regeneratePrompt" class="totp-modal-section">
          <h5>{{ $t("settings.totp.recoveryRegen") }}</h5>
          <p class="muted small">{{ $t("settings.totp.recoveryRegenHint") }}</p>
          <div class="totp-code-row">
            <input
              v-model="regenerateCode"
              type="tel"
              inputmode="numeric"
              maxlength="8"
              placeholder="000000"
              :disabled="busy"
              @keyup.enter="confirmRegenerate"
            />
            <button class="primary" :disabled="busy || !regenerateCode.trim()" @click="confirmRegenerate">
              <Icon name="check" :size="14" />
              <span>{{ $t("settings.totp.recoveryRegen") }}</span>
            </button>
            <button class="ghost" :disabled="busy" @click="closeRegenerate">
              <Icon name="x" :size="14" />
              <span>{{ $t("common.cancel") }}</span>
            </button>
          </div>
        </div>
      </transition>

      <transition name="fade">
        <div v-if="recoveryCodes.length" class="totp-recovery-block">
          <h5>{{ $t("settings.totp.recoveryGenerated") }}</h5>
          <p class="muted small">{{ $t("settings.totp.recoveryWarn") }}</p>
          <ul class="totp-recovery-list">
            <li v-for="code in recoveryCodes" :key="code" class="mono">{{ code }}</li>
          </ul>
          <div class="settings-actions-row">
            <button class="ghost" type="button" @click="copy(recoveryCodes.join('\n'))">
              <Icon name="copy" :size="14" />
              <span>{{ $t("common.copy") }}</span>
            </button>
            <button class="ghost" type="button" @click="downloadRecovery">
              <Icon name="file-down" :size="14" />
              <span>{{ $t("settings.totp.recoveryDownload") }}</span>
            </button>
            <button class="primary" type="button" @click="recoveryCodes = []">
              <Icon name="check" :size="14" />
              <span>{{ $t("settings.totp.recoveryClose") }}</span>
            </button>
          </div>
        </div>
      </transition>
    </template>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { useI18n } from "vue-i18n";
import Icon from "@/components/common/Icon.vue";
import { accountApi } from "@/api/account";
import type { TotpSetupResp, TotpStatus } from "@/api/types";
import { useConfigStore } from "@/stores/config";
import { useToastStore } from "@/stores/toast";

const configStore = useConfigStore();
const toast = useToastStore();
const { t } = useI18n();

const status = ref<TotpStatus | null>(null);
const setup = ref<TotpSetupResp | null>(null);
const setupCode = ref("");

const disablePrompt = ref(false);
const disableCode = ref("");
const disableUseRecovery = ref(false);

const regeneratePrompt = ref(false);
const regenerateCode = ref("");

const recoveryCodes = ref<string[]>([]);
const busy = ref(false);

const featureEnabled = computed(() =>
  Boolean(status.value?.feature_enabled || configStore.config.totp_feature_enabled),
);

onMounted(() => {
  refresh();
});

async function refresh() {
  try {
    status.value = await accountApi.totpStatus();
  } catch (error) {
    toast.push((error as Error).message || t("settings.totp.statusFailed"), "error");
  }
}

async function startSetup() {
  busy.value = true;
  try {
    setup.value = await accountApi.totpSetup();
    setupCode.value = "";
  } catch (error) {
    toast.push((error as Error).message, "error");
  } finally {
    busy.value = false;
  }
}

async function cancelSetup() {
  busy.value = true;
  try {
    await accountApi.totpCancelSetup();
  } catch (_e) {
    // ignore
  } finally {
    setup.value = null;
    setupCode.value = "";
    busy.value = false;
  }
}

async function confirmSetup() {
  const code = setupCode.value.replace(/\D+/g, "").trim();
  if (!code) return;
  busy.value = true;
  try {
    const result = await accountApi.totpConfirm(code);
    recoveryCodes.value = result.recovery_codes || [];
    setup.value = null;
    setupCode.value = "";
    toast.push(t("settings.totp.enableDone"), "success");
    await refresh();
    await configStore.fetch();
  } catch (error) {
    toast.push((error as Error).message, "error");
  } finally {
    busy.value = false;
  }
}

function openDisable() {
  disablePrompt.value = true;
  disableCode.value = "";
  disableUseRecovery.value = false;
}

function closeDisable() {
  disablePrompt.value = false;
  disableCode.value = "";
}

async function confirmDisable() {
  const value = disableCode.value.trim();
  if (!value) return;
  busy.value = true;
  try {
    if (disableUseRecovery.value) {
      await accountApi.totpDisable({ recoveryCode: value });
    } else {
      await accountApi.totpDisable({ code: value.replace(/\D+/g, "") });
    }
    closeDisable();
    toast.push(t("settings.totp.disableDone"), "success");
    await refresh();
    await configStore.fetch();
  } catch (error) {
    toast.push((error as Error).message, "error");
  } finally {
    busy.value = false;
  }
}

function openRegenerate() {
  regeneratePrompt.value = true;
  regenerateCode.value = "";
}

function closeRegenerate() {
  regeneratePrompt.value = false;
  regenerateCode.value = "";
}

async function confirmRegenerate() {
  const code = regenerateCode.value.replace(/\D+/g, "").trim();
  if (!code) return;
  busy.value = true;
  try {
    const result = await accountApi.totpRegenerateRecovery(code);
    recoveryCodes.value = result.recovery_codes || [];
    closeRegenerate();
    toast.push(t("settings.totp.recoveryDone"), "success");
    await refresh();
  } catch (error) {
    toast.push((error as Error).message, "error");
  } finally {
    busy.value = false;
  }
}

function formatSecret(secret: string) {
  return secret.replace(/(.{4})/g, "$1 ").trim();
}

async function copy(text: string) {
  try {
    await navigator.clipboard.writeText(text);
    toast.push(t("common.copied"), "success");
  } catch (error) {
    toast.push((error as Error).message || "copy failed", "error");
  }
}

function downloadRecovery() {
  if (!recoveryCodes.value.length) return;
  const blob = new Blob([recoveryCodes.value.join("\n")], { type: "text/plain;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `media-portal-recovery-codes-${Date.now()}.txt`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  setTimeout(() => URL.revokeObjectURL(url), 1500);
}
</script>

<style scoped>
.totp-section {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.totp-banner {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 12.5px;
  color: var(--text-muted);
}

.totp-status-pill {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 3px 8px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 500;
  border: 1px solid var(--border, rgba(127, 127, 127, 0.18));
}
.totp-status-pill.on {
  color: #16a34a;
  background: rgba(34, 197, 94, 0.08);
  border-color: rgba(34, 197, 94, 0.3);
}
.totp-status-pill.off {
  color: var(--text-muted);
}

.totp-setup,
.totp-modal-section,
.totp-recovery-block {
  margin-top: 10px;
  padding: 14px;
  border-radius: 10px;
  border: 1px solid var(--border, rgba(127, 127, 127, 0.18));
  background: rgba(99, 102, 241, 0.04);
}

.totp-setup-grid {
  display: grid;
  grid-template-columns: 180px 1fr;
  gap: 18px;
  align-items: center;
}

@media (max-width: 600px) {
  .totp-setup-grid {
    grid-template-columns: 1fr;
  }
}

.totp-qr :deep(svg) {
  width: 168px;
  height: 168px;
  border-radius: 8px;
  background: white;
  padding: 8px;
}

.totp-setup-meta {
  display: flex;
  flex-direction: column;
  gap: 6px;
  font-size: 13px;
}

.totp-setup-meta strong {
  margin-right: 6px;
}

.totp-input-label {
  margin-top: 6px;
  font-size: 12.5px;
  color: var(--text-muted);
}

.totp-code-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
}

.totp-code-row input {
  flex: 1 1 160px;
  min-width: 160px;
}

.totp-mode-tabs {
  display: inline-flex;
  border-radius: 8px;
  background: rgba(99, 102, 241, 0.06);
  padding: 2px;
  margin-bottom: 8px;
}

.totp-mode-tabs button {
  border: none;
  background: transparent;
  padding: 4px 10px;
  font-size: 12.5px;
  border-radius: 6px;
  cursor: pointer;
  color: var(--text-muted);
}

.totp-mode-tabs button.active {
  background: var(--surface, white);
  color: var(--text);
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.06);
}

.mono {
  font-family: var(--font-mono, ui-monospace, SFMono-Regular, "SF Mono", monospace);
  font-size: 12.5px;
}

.small {
  font-size: 12px;
}

.totp-recovery-list {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 4px 14px;
  margin: 8px 0 12px;
  padding: 0;
  list-style: none;
}

.totp-recovery-list li {
  font-size: 13px;
  letter-spacing: 0.04em;
}

.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.2s ease;
}
.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}

.danger {
  color: #dc2626;
  border-color: rgba(220, 38, 38, 0.2);
}
.danger:hover {
  background: rgba(220, 38, 38, 0.08);
}
</style>

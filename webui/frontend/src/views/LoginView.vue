<template>
  <section class="login-page">
    <div class="login-card">
      <div class="login-brand">
        <div class="brand-logo brand-logo-img">
          <img :src="logoUrl" alt="Media Portal" />
        </div>
        <div>
          <h1>Media Portal</h1>
          <p>{{ $t("app.subtitle") }}</p>
        </div>
      </div>

      <form v-if="!authStore.hasTotpChallenge" class="login-form" @submit.prevent="submit">
        <label for="password">{{ $t("login.passwordLabel") }}</label>
        <div class="input-wrap">
          <span class="icon-slot"><Icon name="lock" :size="16" /></span>
          <input
            id="password"
            v-model="password"
            :type="showPassword ? 'text' : 'password'"
            autocomplete="current-password"
            :placeholder="$t('login.passwordPlaceholder')"
            :disabled="authStore.loginLoading"
          />
          <button
            type="button"
            class="trailing"
            :title="showPassword ? $t('login.hide') : $t('login.show')"
            @click="showPassword = !showPassword"
          >
            <Icon :name="showPassword ? 'eye-off' : 'eye'" :size="16" />
          </button>
        </div>

        <button
          type="submit"
          class="primary lg block"
          :disabled="authStore.loginLoading || !password.trim()"
        >
          <Icon v-if="!authStore.loginLoading" name="log-in" :size="16" :stroke-width="2" />
          <Icon v-else name="loader" :size="16" :stroke-width="2" />
          {{ authStore.loginLoading ? $t("login.loading") : $t("login.submit") }}
        </button>

        <p v-if="authStore.loginError" class="error">
          <Icon name="circle-alert" :size="15" />
          <span>{{ authStore.loginError }}</span>
        </p>

        <div class="login-meta">
          <LanguageSwitcher />
          <button type="button" class="ghost sm" @click="uiStore.toggleTheme">
            <Icon :name="uiStore.theme === 'dark' ? 'sun' : 'moon'" :size="14" />
            {{ uiStore.theme === "dark" ? $t("topbar.themeLight") : $t("topbar.themeDark") }}
          </button>
        </div>
      </form>

      <form v-else class="login-form" @submit.prevent="verifyTotp">
        <p class="totp-hint">
          <Icon name="shield-check" :size="15" />
          <span>
            {{ useRecovery ? $t("login.totpRecoveryHint") : $t("login.totpHint") }}
          </span>
        </p>

        <label for="otpcode">
          {{ useRecovery ? $t("login.totpRecoveryLabel") : $t("login.totpCodeLabel") }}
        </label>
        <div class="input-wrap">
          <span class="icon-slot"><Icon :name="useRecovery ? 'key-round' : 'shield'" :size="16" /></span>
          <input
            id="otpcode"
            ref="otpInput"
            v-model="otpCode"
            :type="useRecovery ? 'text' : 'tel'"
            inputmode="numeric"
            autocomplete="one-time-code"
            :maxlength="useRecovery ? 16 : 8"
            :placeholder="useRecovery ? $t('login.totpRecoveryPlaceholder') : '000000'"
            :disabled="authStore.loginLoading"
          />
        </div>

        <button
          type="submit"
          class="primary lg block"
          :disabled="authStore.loginLoading || !otpCode.trim()"
        >
          <Icon v-if="!authStore.loginLoading" name="log-in" :size="16" :stroke-width="2" />
          <Icon v-else name="loader" :size="16" :stroke-width="2" />
          {{ authStore.loginLoading ? $t("login.loading") : $t("login.totpSubmit") }}
        </button>

        <p v-if="authStore.loginError" class="error">
          <Icon name="circle-alert" :size="15" />
          <span>{{ authStore.loginError }}</span>
        </p>

        <div class="login-meta">
          <button type="button" class="ghost sm" @click="toggleRecovery">
            <Icon :name="useRecovery ? 'shield' : 'key-round'" :size="14" />
            {{ useRecovery ? $t("login.totpUseCode") : $t("login.totpUseRecovery") }}
          </button>
          <button type="button" class="ghost sm" @click="restart">
            <Icon name="rotate-ccw" :size="14" />
            {{ $t("login.totpRestart") }}
          </button>
        </div>
      </form>
    </div>
  </section>
</template>

<script setup lang="ts">
import { nextTick, ref, watch } from "vue";
import { useRouter } from "vue-router";
import Icon from "@/components/common/Icon.vue";
import LanguageSwitcher from "@/components/common/LanguageSwitcher.vue";
import { useAuthStore } from "@/stores/auth";
import { useUiStore } from "@/stores/ui";

const authStore = useAuthStore();
const uiStore = useUiStore();
const router = useRouter();

const password = ref("");
const showPassword = ref(false);
const otpCode = ref("");
const useRecovery = ref(false);
const otpInput = ref<HTMLInputElement | null>(null);
const logoUrl = `${import.meta.env.BASE_URL}logo.svg`;

watch(
  () => authStore.hasTotpChallenge,
  async (value) => {
    if (value) {
      otpCode.value = "";
      useRecovery.value = false;
      await nextTick();
      otpInput.value?.focus();
    }
  },
);

async function submit() {
  if (!password.value.trim() || authStore.loginLoading) return;
  try {
    const result = await authStore.login(password.value.trim());
    if ((result as any)?.challenge === "totp") {
      return;
    }
    const redirect = (router.currentRoute.value.query.redirect as string) || "/";
    router.replace(redirect);
  } catch (_e) {
    // error captured in store
  }
}

async function verifyTotp() {
  const value = otpCode.value.trim();
  if (!value || authStore.loginLoading) return;
  try {
    if (useRecovery.value) {
      await authStore.verifyTotp({ recoveryCode: value });
    } else {
      const digits = value.replace(/\D+/g, "");
      await authStore.verifyTotp({ code: digits });
    }
    const redirect = (router.currentRoute.value.query.redirect as string) || "/";
    router.replace(redirect);
  } catch (_e) {
    // error captured in store
  }
}

function toggleRecovery() {
  useRecovery.value = !useRecovery.value;
  otpCode.value = "";
  nextTick(() => otpInput.value?.focus());
}

function restart() {
  authStore.clearChallenge();
  password.value = "";
  otpCode.value = "";
  useRecovery.value = false;
}
</script>

<style scoped>
.totp-hint {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  color: var(--text-muted);
  margin-bottom: 8px;
}
</style>

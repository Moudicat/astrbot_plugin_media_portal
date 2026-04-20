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

      <form class="login-form" @submit.prevent="submit">
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
    </div>
  </section>
</template>

<script setup lang="ts">
import { ref } from "vue";
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
const logoUrl = `${import.meta.env.BASE_URL}logo.svg`;

async function submit() {
  if (!password.value.trim() || authStore.loginLoading) return;
  try {
    await authStore.login(password.value.trim());
    const redirect = (router.currentRoute.value.query.redirect as string) || "/";
    router.replace(redirect);
  } catch (_e) {
    // error already captured in authStore.loginError
  }
}
</script>

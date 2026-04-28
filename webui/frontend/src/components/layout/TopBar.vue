<template>
  <header class="topbar" :class="{ 'has-pinned': selectedCount > 0 }">
    <div class="topbar-left">
      <button
        class="icon topbar-sidebar-toggle"
        :title="
          sidebarVisible
            ? $t('topbar.collapseSidebar')
            : $t('topbar.expandSidebar')
        "
        :aria-pressed="sidebarVisible ? 'true' : 'false'"
        @click="$emit('toggle-sidebar')"
      >
        <Icon
          :name="sidebarVisible ? 'panel-left-close' : 'panel-left-open'"
          :size="16"
        />
      </button>
      <div class="brand">
        <div class="brand-logo brand-logo-img">
          <img :src="logoUrl" alt="Media Portal" />
        </div>
        <div class="brand-text">
          <strong>{{ $t("app.title") }}</strong>
          <small>{{ $t("app.subtitle") }}</small>
        </div>
      </div>
      <span v-if="selectedCount" class="topbar-selection">
        <Icon name="check-check" :size="12" />
        {{ selectedCount }}
      </span>
      <div id="topbar-pinned-slot" class="topbar-pinned-slot"></div>
    </div>
    <div class="topbar-actions">
      <ProgressHub class="topbar-progress-hub" />
      <button
        class="icon"
        :title="theme === 'dark' ? $t('topbar.themeDark') : $t('topbar.themeLight')"
        @click="$emit('toggle-theme')"
      >
        <Icon :name="theme === 'dark' ? 'sun' : 'moon'" :size="16" />
      </button>
      <button class="icon" :title="$t('topbar.refresh')" @click="$emit('refresh')">
        <Icon name="refresh-cw" :size="16" />
      </button>
      <button
        class="icon topbar-intelligence-toggle"
        :title="$t('topbar.intelligence')"
        @click="$emit('intelligence')"
      >
        <Icon name="brain-circuit" :size="16" />
      </button>
      <button class="icon" :title="$t('topbar.settings')" @click="$emit('settings')">
        <Icon name="settings" :size="16" />
      </button>
      <button class="ghost" :title="$t('topbar.logout')" @click="$emit('logout')">
        <Icon name="log-out" :size="15" />
        <span class="hide-mobile">{{ $t("topbar.logout") }}</span>
      </button>
    </div>
  </header>
</template>

<script setup lang="ts">
import Icon from "@/components/common/Icon.vue";
import ProgressHub from "@/components/layout/ProgressHub.vue";

interface Props {
  theme?: string;
  selectedCount?: number;
  sidebarVisible?: boolean;
}
withDefaults(defineProps<Props>(), {
  theme: "dark",
  selectedCount: 0,
  sidebarVisible: true,
});

const logoUrl = `${import.meta.env.BASE_URL}logo.svg`;

defineEmits<{
  (e: "toggle-sidebar"): void;
  (e: "toggle-theme"): void;
  (e: "refresh"): void;
  (e: "intelligence"): void;
  (e: "settings"): void;
  (e: "logout"): void;
}>();
</script>

<style scoped>
.topbar-progress-hub {
  margin-right: 4px;
}
</style>

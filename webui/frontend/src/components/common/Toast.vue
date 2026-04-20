<template>
  <div class="toast-wrap">
    <div
      v-for="item in messages"
      :key="item.id"
      class="toast"
      :class="item.type || 'info'"
    >
      <div class="avatar">
        <Icon :name="iconName(item.type)" :size="14" />
      </div>
      <div class="body">
        <strong v-if="item.title">{{ item.title }}</strong>
        <small>{{ item.text }}</small>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import Icon from "./Icon.vue";
import type { ToastMessage } from "@/api/types";

defineProps<{ messages: ToastMessage[] }>();

const TYPE_ICON: Record<string, string> = {
  success: "circle-check",
  error: "circle-x",
  info: "info",
  warning: "triangle-alert",
};

function iconName(type?: string): string {
  return TYPE_ICON[type || "info"] || TYPE_ICON.info;
}
</script>

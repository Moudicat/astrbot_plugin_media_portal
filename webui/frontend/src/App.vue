<template>
  <div class="app-root">
    <router-view />
    <ConfirmDialog
      :visible="confirm.visible"
      :title="confirm.title"
      :message="confirm.message"
      :detail="confirm.detail"
      :confirm-text="confirm.confirmText"
      :cancel-text="confirm.cancelText"
      :tone="confirm.tone"
      :icon="confirm.icon"
      @confirm="confirm.resolve(true)"
      @cancel="confirm.resolve(false)"
    />
    <Toast :messages="toast.messages" />
    <ContextMenu
      :visible="ui.contextMenu.visible"
      :x="ui.contextMenu.x"
      :y="ui.contextMenu.y"
      :items="ui.contextMenu.items"
      @close="ui.closeContextMenu()"
      @select="onContextSelect"
    />
  </div>
</template>

<script setup lang="ts">
import { useConfirmStore } from "@/stores/confirm";
import { useToastStore } from "@/stores/toast";
import { useUiStore } from "@/stores/ui";
import ConfirmDialog from "@/components/common/ConfirmDialog.vue";
import Toast from "@/components/common/Toast.vue";
import ContextMenu from "@/components/common/ContextMenu.vue";

const confirm = useConfirmStore();
const toast = useToastStore();
const ui = useUiStore();

function onContextSelect(key: string) {
  const payload = ui.contextMenu.payload;
  if (payload && typeof payload.onSelect === "function") {
    try {
      payload.onSelect(key, payload.item);
    } catch (_e) {
      // ignore
    }
  }
}
</script>

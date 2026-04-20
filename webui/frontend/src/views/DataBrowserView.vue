<template>
  <DataBrowser
    v-if="config.canDataBrowse"
    :path="dataBrowser.path"
    :parent="dataBrowser.parent"
    :items="dataBrowser.items"
    :loading="dataBrowser.loading"
    @open-dir="openDir"
    @open-file="openFile"
    @go-parent="goParent"
    @navigate="openDir"
  />
  <section v-else class="panel empty">
    <div class="illus"><Icon name="shield-off" :size="32" /></div>
    <strong>{{ $t("dataBrowser.notEnabledTitle") }}</strong>
    <span>{{ $t("dataBrowser.notEnabledHint") }}</span>
  </section>
</template>

<script setup lang="ts">
import { inject, onMounted } from "vue";
import DataBrowser from "@/components/data/DataBrowser.vue";
import Icon from "@/components/common/Icon.vue";
import { useConfigStore } from "@/stores/config";
import { useDataBrowserStore } from "@/stores/dataBrowser";
import { useToastStore } from "@/stores/toast";
import type { DataTreeItem } from "@/api/types";

const config = useConfigStore();
const dataBrowser = useDataBrowserStore();
const toast = useToastStore();
const handleDataFile = inject<(item: DataTreeItem) => void>("handleDataFile");

onMounted(() => {
  if (config.canDataBrowse) {
    dataBrowser
      .fetchTree(dataBrowser.path || "")
      .catch((error) => toast.push((error as Error).message, "error"));
  }
});

function openDir(path: string) {
  dataBrowser.fetchTree(path).catch((error) => toast.push((error as Error).message, "error"));
}
function goParent() {
  dataBrowser
    .fetchTree(dataBrowser.parent || "")
    .catch((error) => toast.push((error as Error).message, "error"));
}
function openFile(item: DataTreeItem) {
  handleDataFile?.(item);
}
</script>

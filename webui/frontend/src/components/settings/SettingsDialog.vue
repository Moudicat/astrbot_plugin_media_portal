<template>
  <transition name="modal">
    <div v-if="visible" class="modal-mask" @click.self="$emit('close')">
      <div class="modal settings-modal">
        <header>
          <h3>
            <Icon name="settings" :size="17" style="vertical-align: -3px" />
            {{ $t("settings.title") }}
          </h3>
          <button class="icon" :title="$t('common.closeEsc')" @click="$emit('close')">
            <Icon name="x" :size="16" />
          </button>
        </header>

        <div class="modal-body settings-body">
          <section class="settings-section">
            <div class="settings-section-head">
              <div>
                <strong>{{ $t("settings.statsTitle") }}</strong>
                <small class="muted">{{ $t("settings.statsHint") }}</small>
              </div>
              <div class="settings-toolbar">
                <button
                  class="ghost sm"
                  :disabled="allOn"
                  :title="$t('settings.showAll')"
                  @click="setAll(true)"
                >
                  <Icon name="eye" :size="13" />
                  <span>{{ $t("settings.showAll") }}</span>
                </button>
                <button
                  class="ghost sm"
                  :disabled="allOff"
                  :title="$t('settings.hideAll')"
                  @click="setAll(false)"
                >
                  <Icon name="eye-off" :size="13" />
                  <span>{{ $t("settings.hideAll") }}</span>
                </button>
              </div>
            </div>
            <ul class="settings-toggle-list">
              <li
                v-for="opt in statOptions"
                :key="opt.key"
                class="settings-toggle"
                :class="{ disabled: !isOn(opt.key) }"
                @click="toggleStat(opt.key)"
              >
                <div class="settings-toggle-icon">
                  <Icon :name="opt.icon" :size="14" />
                </div>
                <div class="settings-toggle-body">
                  <span class="settings-toggle-title">{{ $t(opt.labelKey) }}</span>
                  <span class="settings-toggle-desc">{{ $t(opt.descKey) }}</span>
                </div>
                <span
                  class="switch"
                  :class="{ on: isOn(opt.key) }"
                  role="switch"
                  :aria-checked="isOn(opt.key) ? 'true' : 'false'"
                ></span>
              </li>
            </ul>
          </section>

          <section class="settings-section">
            <div class="settings-section-head">
              <div>
                <strong>{{ $t("settings.pruneTitle") }}</strong>
                <small class="muted">{{ $t("settings.pruneHint") }}</small>
              </div>
              <button class="ghost" :disabled="pruneBusy" @click="onPrune">
                <Icon name="eraser" :size="14" />
                <span>{{ pruneBusy ? $t("settings.pruneBusy") : $t("settings.pruneNow") }}</span>
              </button>
            </div>
          </section>

          <section class="settings-section">
            <div class="settings-section-head">
              <div>
                <strong>{{ $t("settings.languageTitle") }}</strong>
                <small class="muted">{{ $t("settings.languageHint") }}</small>
              </div>
              <LanguageSwitcher />
            </div>
          </section>
        </div>

        <div class="modal-footer">
          <button class="primary" @click="$emit('close')">{{ $t("common.done") }}</button>
        </div>
      </div>
    </div>
  </transition>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from "vue";
import Icon from "@/components/common/Icon.vue";
import LanguageSwitcher from "@/components/common/LanguageSwitcher.vue";
import type { StatVisibility } from "@/stores/ui";

const STAT_CARD_OPTIONS = [
  { key: "total", labelKey: "settings.stat.total", icon: "library", descKey: "settings.stat.totalDesc" },
  { key: "image", labelKey: "settings.stat.image", icon: "image", descKey: "settings.stat.imageDesc" },
  { key: "video", labelKey: "settings.stat.video", icon: "film", descKey: "settings.stat.videoDesc" },
  { key: "audio", labelKey: "settings.stat.audio", icon: "music", descKey: "settings.stat.audioDesc" },
  { key: "cat", labelKey: "settings.stat.cat", icon: "folder", descKey: "settings.stat.catDesc" },
  { key: "size", labelKey: "settings.stat.size", icon: "database", descKey: "settings.stat.sizeDesc" },
] as const;

interface Props {
  visible?: boolean;
  statVisibility?: StatVisibility;
}

const props = withDefaults(defineProps<Props>(), {
  visible: false,
  statVisibility: () => ({
    total: true,
    image: true,
    video: true,
    audio: true,
    cat: true,
    size: true,
  }),
});

const emit = defineEmits<{
  (e: "close"): void;
  (e: "prune-categories"): void;
  (e: "update-stat-visibility", payload: Partial<StatVisibility>): void;
}>();

const pruneBusy = ref(false);
const statOptions = STAT_CARD_OPTIONS;

const allOn = computed(() =>
  STAT_CARD_OPTIONS.every((opt) => (props.statVisibility as any)[opt.key] !== false),
);
const allOff = computed(() =>
  STAT_CARD_OPTIONS.every((opt) => (props.statVisibility as any)[opt.key] === false),
);

function onKey(event: KeyboardEvent) {
  if (!props.visible) return;
  if (event.key === "Escape") emit("close");
}

watch(
  () => props.visible,
  (value) => {
    if (value) {
      pruneBusy.value = false;
      window.addEventListener("keydown", onKey);
    } else {
      window.removeEventListener("keydown", onKey);
    }
  },
);

onBeforeUnmount(() => {
  window.removeEventListener("keydown", onKey);
});

function onPrune() {
  pruneBusy.value = true;
  emit("prune-categories");
  setTimeout(() => {
    pruneBusy.value = false;
  }, 1200);
}

function isOn(key: string) {
  return (props.statVisibility as any)[key] !== false;
}

function toggleStat(key: string) {
  emit("update-stat-visibility", { [key]: !isOn(key) } as Partial<StatVisibility>);
}

function setAll(value: boolean) {
  const payload: Record<string, boolean> = {};
  for (const opt of STAT_CARD_OPTIONS) payload[opt.key] = value;
  emit("update-stat-visibility", payload as Partial<StatVisibility>);
}
</script>

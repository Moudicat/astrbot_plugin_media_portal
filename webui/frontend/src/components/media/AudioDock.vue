<template>
  <transition name="audio-dock">
    <div
      v-if="item"
      class="audio-dock"
      :class="{ 'is-mini': minimized }"
      role="region"
      :aria-label="$t('audioDock.aria')"
    >
      <div class="avatar" @click="minimized && toggleMinimized()">
        <Icon name="music" :size="18" />
      </div>
      <div class="audio-dock-meta">
        <strong :title="title">{{ title }}</strong>
        <small>{{ item.category || "data" }}</small>
      </div>
      <div class="audio-dock-controls">
        <button
          class="icon"
          :title="minimized ? $t('audioDock.expand') : $t('audioDock.minimize')"
          @click="toggleMinimized"
        >
          <Icon :name="minimized ? 'chevron-up' : 'chevron-down'" :size="16" />
        </button>
        <button class="icon" :title="$t('audioDock.close')" @click="$emit('close')">
          <Icon name="x" :size="16" />
        </button>
      </div>
      <div v-show="!minimized" class="audio-dock-player">
        <audio
          ref="audioRef"
          :src="sourceUrl"
          autoplay
          preload="metadata"
          @loadedmetadata="syncProgress"
          @durationchange="syncProgress"
          @timeupdate="syncProgress"
          @play="onPlay"
          @pause="onPause"
          @ended="onPause"
        ></audio>
        <div class="audio-dock-main">
          <button
            class="icon sm"
            :title="isPlaying ? $t('audioDock.pause') : $t('audioDock.play')"
            @click="togglePlay"
          >
            <Icon :name="isPlaying ? 'pause' : 'play'" :size="14" />
          </button>
          <span class="audio-time-inline mono">{{ currentTimeLabel }}/{{ durationLabel }}</span>
          <input
            class="audio-progress"
            type="range"
            min="0"
            :max="duration || 0"
            step="0.1"
            :value="currentTime"
            :style="audioProgressStyle"
            :title="$t('audioDock.play')"
            @input="onProgressInput"
          />
          <div class="audio-volume-wrap">
            <button
              class="icon sm"
              :title="muted ? $t('audioDock.unmute') : $t('audioDock.mute')"
              @click="toggleMuted"
            >
              <Icon :name="muted ? 'volume-x' : 'volume-2'" :size="14" />
            </button>
            <div class="audio-volume-pop" :aria-label="$t('audioDock.volume')">
              <input
                class="audio-volume"
                type="range"
                min="0"
                max="1"
                step="0.01"
                :value="muted ? 0 : volume"
                :title="$t('audioDock.volume')"
                @input="onVolumeInput"
              />
            </div>
          </div>
        </div>
      </div>
    </div>
  </transition>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, watch } from "vue";
import Icon from "@/components/common/Icon.vue";
import type { MediaItem } from "@/api/types";

interface AudioItem extends Partial<MediaItem> {
  directUrl?: string;
  name?: string;
}

interface Props {
  item?: AudioItem | null;
  readonlyToken?: string;
}

const props = withDefaults(defineProps<Props>(), {
  item: null,
  readonlyToken: "",
});

defineEmits<{
  (e: "close"): void;
}>();

const minimized = ref(false);
const audioRef = ref<HTMLAudioElement | null>(null);
const isPlaying = ref(false);
const currentTime = ref(0);
const duration = ref(0);
const muted = ref(false);
const volume = ref(1);
const lastNonZeroVolume = ref(1);

watch(
  () => props.item,
  async (value) => {
    if (value) minimized.value = false;
    if (typeof document !== "undefined") {
      document.body.classList.toggle("audio-dock-active", !!value);
    }
    resetPlaybackState();
    await nextTick();
    applyRuntimeState();
    if (value) {
      void audioRef.value?.play().catch(() => undefined);
    }
  },
  { immediate: true },
);

watch(minimized, (value) => {
  if (typeof document !== "undefined") {
    document.body.classList.toggle("audio-dock-mini", !!value);
  }
});

onBeforeUnmount(() => {
  if (typeof document !== "undefined") {
    document.body.classList.remove("audio-dock-active");
    document.body.classList.remove("audio-dock-mini");
  }
});

const sourceUrl = computed(() => {
  const it = props.item;
  if (!it) return "";
  if (it.directUrl) return it.directUrl;
  if (!it.category || !it.filename) return "";
  const token = props.readonlyToken ? `?token=${encodeURIComponent(props.readonlyToken)}` : "";
  return `/files/${encodeURIComponent(it.category)}/${encodeURIComponent(it.filename)}${token}`;
});

watch(sourceUrl, async () => {
  resetPlaybackState();
  await nextTick();
  applyRuntimeState();
  if (props.item) {
    void audioRef.value?.play().catch(() => undefined);
  }
});

const title = computed(() => {
  if (!props.item) return "";
  return props.item.filename || props.item.name || "";
});

const currentTimeLabel = computed(() => formatTime(currentTime.value));
const durationLabel = computed(() => formatTime(duration.value));
const progressPercent = computed(() => {
  if (!duration.value || duration.value <= 0) return 0;
  return clamp((currentTime.value / duration.value) * 100, 0, 100);
});
const audioProgressStyle = computed(() => ({
  "--audio-progress": `${progressPercent.value}%`,
}));

function toggleMinimized() {
  minimized.value = !minimized.value;
}

function resetPlaybackState() {
  isPlaying.value = false;
  currentTime.value = 0;
  duration.value = 0;
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

function formatTime(raw: number): string {
  if (!Number.isFinite(raw) || raw <= 0) return "0:00";
  const total = Math.floor(raw);
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const seconds = total % 60;
  const pad = (num: number) => String(num).padStart(2, "0");
  if (hours > 0) return `${hours}:${pad(minutes)}:${pad(seconds)}`;
  return `${minutes}:${pad(seconds)}`;
}

function syncProgress() {
  const el = audioRef.value;
  if (!el) return;
  currentTime.value = clamp(Number(el.currentTime) || 0, 0, Number(el.duration) || 0);
  duration.value = Number.isFinite(el.duration) && el.duration > 0 ? Number(el.duration) : 0;
  muted.value = !!el.muted;
  volume.value = clamp(Number(el.volume) || 0, 0, 1);
  if (volume.value > 0) {
    lastNonZeroVolume.value = volume.value;
  }
  isPlaying.value = !el.paused && !el.ended;
}

function applyRuntimeState() {
  const el = audioRef.value;
  if (!el) return;
  el.muted = muted.value;
  el.volume = clamp(volume.value, 0, 1);
}

function onPlay() {
  isPlaying.value = true;
}

function onPause() {
  isPlaying.value = false;
}

function togglePlay() {
  const el = audioRef.value;
  if (!el) return;
  if (el.paused) {
    void el.play().catch(() => undefined);
    return;
  }
  el.pause();
}

function onProgressInput(event: Event) {
  const input = event.target as HTMLInputElement | null;
  if (!input) return;
  const next = Number(input.value);
  if (!Number.isFinite(next)) return;
  const el = audioRef.value;
  if (!el) return;
  el.currentTime = next;
  currentTime.value = next;
}

function toggleMuted() {
  const el = audioRef.value;
  if (muted.value) {
    muted.value = false;
    if (volume.value <= 0) {
      volume.value = clamp(lastNonZeroVolume.value || 0.7, 0.05, 1);
    }
  } else {
    muted.value = true;
  }
  if (!el) return;
  el.muted = muted.value;
  el.volume = clamp(volume.value, 0, 1);
}

function onVolumeInput(event: Event) {
  const input = event.target as HTMLInputElement | null;
  if (!input) return;
  const next = clamp(Number(input.value) || 0, 0, 1);
  volume.value = next;
  if (next > 0) {
    lastNonZeroVolume.value = next;
  }
  muted.value = next === 0;
  const el = audioRef.value;
  if (!el) return;
  el.volume = next;
  el.muted = muted.value;
}
</script>

<template>
  <div class="plyr-shell" :class="`is-${kind}`">
    <component
      :is="tagName"
      ref="mediaRef"
      :src="src"
      :autoplay="autoplay"
      :muted="muted"
      :playsinline="kind === 'video'"
      controls
      preload="metadata"
    ></component>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import Plyr from "plyr";
import "plyr/dist/plyr.css";

type MediaKind = "video" | "audio";

interface Props {
  src: string;
  kind?: MediaKind;
  autoplay?: boolean;
  muted?: boolean;
}

const props = withDefaults(defineProps<Props>(), {
  kind: "video",
  autoplay: true,
  muted: false,
});

const mediaRef = ref<HTMLVideoElement | HTMLAudioElement | null>(null);
const playerRef = ref<Plyr | null>(null);

const tagName = computed(() => (props.kind === "audio" ? "audio" : "video"));

function playerControls(kind: MediaKind): Plyr.Options["controls"] {
  if (kind === "audio") {
    return ["play", "progress", "current-time", "duration", "mute", "volume", "settings"];
  }
  return [
    "play-large",
    "play",
    "progress",
    "current-time",
    "duration",
    "mute",
    "volume",
    "settings",
    "fullscreen",
  ];
}

function destroyPlayer() {
  const player = playerRef.value;
  if (!player) return;
  player.destroy();
  playerRef.value = null;
}

function tryPlay() {
  const result = playerRef.value?.play();
  if (result instanceof Promise) {
    void result.catch(() => undefined);
  }
}

function initPlayer() {
  const media = mediaRef.value;
  if (!media) return;
  destroyPlayer();
  playerRef.value = new Plyr(media, {
    controls: playerControls(props.kind),
    settings: ["speed", "loop"],
    speed: {
      selected: 1,
      options: [0.75, 1, 1.25, 1.5, 2],
    },
    keyboard: {
      focused: true,
      global: false,
    },
    tooltips: {
      controls: true,
      seek: true,
    },
    fullscreen: {
      enabled: props.kind === "video",
      iosNative: true,
    },
  });
  if (props.autoplay) {
    tryPlay();
  }
}

watch(
  () => props.src,
  async () => {
    await nextTick();
    if (props.autoplay) {
      tryPlay();
    }
  },
);

watch(
  () => props.muted,
  (value) => {
    if (!playerRef.value) return;
    playerRef.value.muted = !!value;
  },
);

onMounted(() => {
  initPlayer();
});

onBeforeUnmount(() => {
  destroyPlayer();
});
</script>

<style scoped>
.plyr-shell {
  width: min(1100px, 100%);
}

.plyr-shell.is-audio {
  width: min(760px, 90%);
}

.plyr-shell :deep(.plyr) {
  --plyr-color-main: var(--primary);
  --plyr-video-control-color: #fff;
  --plyr-video-controls-background: linear-gradient(
    180deg,
    rgba(15, 23, 42, 0) 0%,
    rgba(15, 23, 42, 0.88) 100%
  );
  --plyr-audio-controls-background: rgba(15, 23, 42, 0.76);
  --plyr-audio-control-color: #fff;
  --plyr-menu-background: color-mix(in srgb, var(--surface-0) 92%, #0f172a 8%);
  --plyr-menu-color: var(--text);
  --plyr-tooltip-background: #0f172a;
  --plyr-tooltip-color: #fff;
  border-radius: var(--radius-lg);
  overflow: hidden;
}

.plyr-shell.is-video :deep(.plyr) {
  box-shadow: var(--shadow-lg);
}

.plyr-shell.is-video :deep(.plyr--video .plyr__controls .plyr__control) {
  background: rgba(15, 23, 42, 0.42);
  color: #fff;
  border-radius: 10px;
}

.plyr-shell.is-video :deep(.plyr--video .plyr__controls .plyr__control:hover),
.plyr-shell.is-video :deep(.plyr--video .plyr__controls .plyr__control:focus-visible),
.plyr-shell.is-video :deep(.plyr--video .plyr__controls .plyr__control[aria-expanded="true"]) {
  background: rgba(15, 23, 42, 0.76);
  color: #fff;
}

.plyr-shell.is-video :deep(video) {
  max-height: calc(100vh - 170px);
  object-fit: contain;
}

.plyr-shell.is-audio :deep(.plyr) {
  border: 1px solid rgba(148, 163, 184, 0.24);
}

@media (max-width: 640px) {
  .plyr-shell {
    width: 100%;
  }

  .plyr-shell.is-audio {
    width: 100%;
  }
}
</style>

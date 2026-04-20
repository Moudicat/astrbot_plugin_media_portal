<template>
  <div ref="rootEl" class="lang-switcher" :class="{ open }">
    <button
      ref="triggerEl"
      type="button"
      class="lang-trigger"
      :title="$t('topbar.language')"
      :aria-expanded="open ? 'true' : 'false'"
      aria-haspopup="listbox"
      @click.stop="toggle"
      @keydown="onTriggerKey"
    >
      <Icon v-if="showIcon" name="languages" :size="15" class="lang-icon" />
      <span class="lang-current">{{ currentLabel }}</span>
      <Icon name="chevron-down" :size="13" class="lang-caret" aria-hidden="true" />
    </button>

    <Teleport to="body">
      <transition name="lang-menu">
        <ul
          v-if="open"
          ref="menuEl"
          class="lang-menu"
          role="listbox"
          tabindex="-1"
          :aria-label="$t('topbar.language')"
          :style="menuStyle"
        >
          <li
            v-for="(item, idx) in SUPPORTED_LOCALES"
            :key="item"
            role="option"
            class="lang-option"
            :class="{
              active: item === locale,
              focused: idx === focusIndex,
            }"
            :aria-selected="item === locale ? 'true' : 'false'"
            @click="choose(item)"
            @mouseenter="focusIndex = idx"
          >
            <span class="lang-option-check">
              <Icon v-if="item === locale" name="check" :size="13" />
            </span>
            <span class="lang-option-label">{{ LOCALE_LABELS[item] }}</span>
            <span class="lang-option-code">{{ item }}</span>
          </li>
        </ul>
      </transition>
    </Teleport>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, reactive, ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import Icon from "./Icon.vue";
import { LOCALE_LABELS, SUPPORTED_LOCALES, setLocale, type Locale } from "@/i18n";

interface Props {
  showIcon?: boolean;
  /** 菜单距离触发按钮的垂直间距，像素 */
  offset?: number;
  /** 菜单最小宽度，像素；默认与触发按钮同宽并不少于 200 */
  minWidth?: number;
}
const props = withDefaults(defineProps<Props>(), {
  showIcon: true,
  offset: 8,
  minWidth: 200,
});

const { locale } = useI18n();

const rootEl = ref<HTMLDivElement | null>(null);
const triggerEl = ref<HTMLButtonElement | null>(null);
const menuEl = ref<HTMLUListElement | null>(null);
const open = ref(false);
const focusIndex = ref(-1);

const currentLabel = computed(() => LOCALE_LABELS[locale.value as Locale] || locale.value);

// 菜单在 body 下使用 fixed 定位，坐标由 trigger 的 boundingRect 计算
const menuPos = reactive({ top: 0, left: 0, minWidth: props.minWidth });
const menuStyle = computed(() => ({
  top: `${menuPos.top}px`,
  left: `${menuPos.left}px`,
  minWidth: `${menuPos.minWidth}px`,
}));

function updateMenuPosition() {
  const btn = triggerEl.value;
  if (!btn) return;
  const rect = btn.getBoundingClientRect();
  const width = Math.max(props.minWidth, rect.width);
  // 默认贴右对齐；若越出视口右边界则左对齐
  let left = rect.right - width;
  if (left < 8) left = 8;
  if (left + width > window.innerWidth - 8) {
    left = window.innerWidth - width - 8;
  }
  let top = rect.bottom + props.offset;
  // 若下方空间不足，显示到上方
  const estimatedHeight = SUPPORTED_LOCALES.length * 40 + 20;
  if (top + estimatedHeight > window.innerHeight - 8) {
    top = Math.max(8, rect.top - props.offset - estimatedHeight);
  }
  menuPos.top = top;
  menuPos.left = left;
  menuPos.minWidth = width;
}

function toggle() {
  open.value ? close() : openMenu();
}

function openMenu() {
  focusIndex.value = SUPPORTED_LOCALES.indexOf(locale.value as Locale);
  updateMenuPosition();
  open.value = true;
  nextTick(() => {
    updateMenuPosition();
    menuEl.value?.focus();
  });
}

function close() {
  open.value = false;
  focusIndex.value = -1;
}

async function choose(target: Locale) {
  close();
  if (target === locale.value) return;
  try {
    await setLocale(target);
  } catch (_e) {
    // ignore
  }
}

function onDocClick(event: MouseEvent) {
  if (!open.value) return;
  const root = rootEl.value;
  const menu = menuEl.value;
  const target = event.target as Node | null;
  if (!target) return;
  // 点击触发区或菜单内部不关闭
  if (root && root.contains(target)) return;
  if (menu && menu.contains(target)) return;
  close();
}

function onDocKey(event: KeyboardEvent) {
  if (!open.value) return;
  switch (event.key) {
    case "Escape":
      event.preventDefault();
      close();
      break;
    case "ArrowDown":
      event.preventDefault();
      focusIndex.value = (focusIndex.value + 1) % SUPPORTED_LOCALES.length;
      break;
    case "ArrowUp":
      event.preventDefault();
      focusIndex.value =
        (focusIndex.value - 1 + SUPPORTED_LOCALES.length) % SUPPORTED_LOCALES.length;
      break;
    case "Enter":
    case " ":
      event.preventDefault();
      if (focusIndex.value >= 0) choose(SUPPORTED_LOCALES[focusIndex.value]);
      break;
  }
}

function onTriggerKey(event: KeyboardEvent) {
  if (event.key === "ArrowDown" || event.key === "Enter" || event.key === " ") {
    event.preventDefault();
    openMenu();
  }
}

function onScrollOrResize() {
  if (!open.value) return;
  updateMenuPosition();
}

watch(open, (value) => {
  if (value) {
    document.addEventListener("click", onDocClick);
    document.addEventListener("keydown", onDocKey);
    window.addEventListener("scroll", onScrollOrResize, true);
    window.addEventListener("resize", onScrollOrResize);
  } else {
    document.removeEventListener("click", onDocClick);
    document.removeEventListener("keydown", onDocKey);
    window.removeEventListener("scroll", onScrollOrResize, true);
    window.removeEventListener("resize", onScrollOrResize);
  }
});

onBeforeUnmount(() => {
  document.removeEventListener("click", onDocClick);
  document.removeEventListener("keydown", onDocKey);
  window.removeEventListener("scroll", onScrollOrResize, true);
  window.removeEventListener("resize", onScrollOrResize);
});
</script>

<style scoped>
.lang-switcher {
  position: relative;
  display: inline-flex;
  flex-shrink: 0;
}

/* ---- 触发按钮：玻璃拟态胶囊 ---- */
.lang-trigger {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 6px 12px;
  min-height: 34px;
  border-radius: 999px;
  background: var(--surface-1, rgba(148, 163, 184, 0.08));
  border: 1px solid var(--border, rgba(148, 163, 184, 0.2));
  color: var(--text, inherit);
  font-family: inherit;
  font-size: 13px;
  font-weight: 500;
  line-height: 1;
  cursor: pointer;
  backdrop-filter: var(--blur, blur(8px));
  -webkit-backdrop-filter: var(--blur, blur(8px));
  transition:
    background 180ms ease,
    border-color 180ms ease,
    transform 120ms ease;
}
.lang-trigger:hover {
  background: var(--surface-2, rgba(148, 163, 184, 0.12));
  border-color: var(--border-strong, rgba(148, 163, 184, 0.32));
}
.lang-trigger:active {
  transform: translateY(1px);
}
.lang-switcher.open .lang-trigger {
  background: var(--primary-soft, rgba(99, 102, 241, 0.15));
  border-color: var(--primary, #6366f1);
}
.lang-trigger:focus-visible {
  outline: 2px solid var(--primary, #6366f1);
  outline-offset: 2px;
  border-color: var(--primary, #6366f1);
}
.lang-icon {
  opacity: 0.8;
  flex-shrink: 0;
}
.lang-current {
  white-space: nowrap;
  display: inline-block;
  min-width: 66px;
  text-align: left;
  overflow: hidden;
  text-overflow: ellipsis;
}
.lang-caret {
  opacity: 0.6;
  transition: transform 180ms ease;
}
.lang-switcher.open .lang-caret {
  transform: rotate(180deg);
}
</style>

<!-- 菜单通过 Teleport 送到 <body>，不能使用 scoped 样式，
     改用全局样式并加 `.mp-lang-menu` 前缀避免冲突。 -->
<style>
.lang-menu {
  position: fixed;
  z-index: 9999;
  list-style: none;
  margin: 0;
  padding: 6px;
  background: var(--surface-strong, rgba(15, 23, 42, 0.92));
  border: 1px solid var(--border, rgba(148, 163, 184, 0.18));
  border-radius: 14px;
  box-shadow: var(--shadow-lg, 0 24px 56px rgba(2, 6, 23, 0.55));
  backdrop-filter: var(--blur, blur(10px));
  -webkit-backdrop-filter: var(--blur, blur(10px));
  color: var(--text, inherit);
  font-family: var(--font-sans);
}
.lang-menu:focus {
  outline: none;
}

.lang-menu .lang-option {
  display: grid;
  grid-template-columns: 18px 1fr auto;
  align-items: center;
  gap: 10px;
  padding: 9px 12px 9px 10px;
  border-radius: 8px;
  cursor: pointer;
  font-size: 13px;
  color: var(--text, inherit);
  transition:
    background 140ms ease,
    color 140ms ease;
}
.lang-menu .lang-option.focused,
.lang-menu .lang-option:hover {
  background: var(--surface-hover, rgba(99, 102, 241, 0.12));
}
.lang-menu .lang-option.active {
  color: var(--primary, #6366f1);
  font-weight: 600;
}
.lang-menu .lang-option.active.focused,
.lang-menu .lang-option.active:hover {
  background: var(--primary-soft, rgba(99, 102, 241, 0.18));
}
.lang-menu .lang-option-check {
  display: inline-flex;
  width: 18px;
  height: 18px;
  align-items: center;
  justify-content: center;
  color: var(--primary, #6366f1);
}
.lang-menu .lang-option-label {
  white-space: nowrap;
}
.lang-menu .lang-option-code {
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--text-subtle, #64748b);
  letter-spacing: 0.5px;
}

/* 过渡动画 */
.lang-menu-enter-active,
.lang-menu-leave-active {
  transition:
    opacity 160ms ease,
    transform 180ms cubic-bezier(0.2, 0.9, 0.3, 1.2);
  transform-origin: top right;
}
.lang-menu-enter-from,
.lang-menu-leave-to {
  opacity: 0;
  transform: translateY(-4px) scale(0.96);
}
</style>

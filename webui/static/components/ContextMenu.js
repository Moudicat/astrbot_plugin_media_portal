import { Icon } from "./Icon.js";

export const ContextMenu = {
  name: "ContextMenu",
  components: { Icon },
  props: {
    visible: { type: Boolean, default: false },
    x: { type: Number, default: 0 },
    y: { type: Number, default: 0 },
    items: { type: Array, default: () => [] },
  },
  emits: ["close", "select"],
  data() {
    return {
      pos: { left: 0, top: 0 },
      ready: false,
    };
  },
  watch: {
    visible: {
      immediate: true,
      handler(value) {
        if (value) {
          this.ready = false;
          this.pos = { left: this.x, top: this.y };
          this.$nextTick(() => this.adjustPosition());
          window.addEventListener("keydown", this.onKey);
          window.addEventListener("resize", this.onWinChange);
          window.addEventListener("scroll", this.onWinChange, true);
        } else {
          window.removeEventListener("keydown", this.onKey);
          window.removeEventListener("resize", this.onWinChange);
          window.removeEventListener("scroll", this.onWinChange, true);
        }
      },
    },
    x() {
      if (this.visible) {
        this.ready = false;
        this.pos = { left: this.x, top: this.y };
        this.$nextTick(() => this.adjustPosition());
      }
    },
    y() {
      if (this.visible) {
        this.ready = false;
        this.pos = { left: this.x, top: this.y };
        this.$nextTick(() => this.adjustPosition());
      }
    },
  },
  beforeUnmount() {
    window.removeEventListener("keydown", this.onKey);
    window.removeEventListener("resize", this.onWinChange);
    window.removeEventListener("scroll", this.onWinChange, true);
  },
  methods: {
    onKey(event) {
      if (!this.visible) return;
      if (event.key === "Escape") {
        event.preventDefault();
        this.$emit("close");
      }
    },
    onWinChange() {
      this.$emit("close");
    },
    adjustPosition() {
      const el = this.$refs.menu;
      if (!el) return;
      const margin = 8;
      const rect = el.getBoundingClientRect();
      const vw = window.innerWidth || document.documentElement.clientWidth;
      const vh = window.innerHeight || document.documentElement.clientHeight;
      let left = this.x;
      let top = this.y;
      if (left + rect.width + margin > vw) {
        left = Math.max(margin, vw - rect.width - margin);
      }
      if (top + rect.height + margin > vh) {
        top = Math.max(margin, vh - rect.height - margin);
      }
      if (left < margin) left = margin;
      if (top < margin) top = margin;
      this.pos = { left, top };
      this.ready = true;
    },
    pick(item) {
      if (!item || item.disabled || item.divider) return;
      this.$emit("select", item.key);
      this.$emit("close");
    },
  },
  template: `
    <teleport to="body">
      <transition name="context-menu">
        <div
          v-if="visible"
          class="context-menu-mask"
          @mousedown.self="$emit('close')"
          @contextmenu.prevent="$emit('close')"
        >
          <ul
            ref="menu"
            class="context-menu"
            :class="{ ready }"
            :style="{ left: pos.left + 'px', top: pos.top + 'px' }"
            role="menu"
          >
            <template v-for="(item, idx) in items" :key="item.key || ('d_' + idx)">
              <li v-if="item.divider" class="context-menu-divider" role="separator"></li>
              <li
                v-else
                class="context-menu-item"
                :class="['tone-' + (item.tone || 'default'), { disabled: item.disabled }]"
                role="menuitem"
                @click="pick(item)"
              >
                <span class="context-menu-icon">
                  <Icon v-if="item.icon" :name="item.icon" :size="14" />
                </span>
                <span class="context-menu-label">{{ item.label }}</span>
                <span v-if="item.shortcut" class="context-menu-shortcut">{{ item.shortcut }}</span>
              </li>
            </template>
          </ul>
        </div>
      </transition>
    </teleport>
  `,
};

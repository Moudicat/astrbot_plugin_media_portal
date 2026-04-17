import { Icon } from "./Icon.js";

const TYPE_ICON = {
  success: "circle-check",
  error: "circle-x",
  info: "info",
  warning: "triangle-alert",
};

export const Toast = {
  name: "Toast",
  components: { Icon },
  props: {
    messages: { type: Array, default: () => [] },
  },
  methods: {
    iconName(type) {
      return TYPE_ICON[type] || TYPE_ICON.info;
    },
  },
  template: `
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
  `,
};

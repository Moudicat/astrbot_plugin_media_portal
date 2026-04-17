export const Toast = {
  name: "Toast",
  props: {
    messages: { type: Array, default: () => [] },
  },
  template: `
    <div class="toast-wrap">
      <div
        v-for="item in messages"
        :key="item.id"
        class="toast"
        :class="item.type || 'info'"
      >
        {{ item.text }}
      </div>
    </div>
  `,
};

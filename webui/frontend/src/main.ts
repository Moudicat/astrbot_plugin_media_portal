import { createApp } from "vue";
import { createPinia } from "pinia";
import App from "./App.vue";
import { router } from "./router";
import { i18n, bootstrapLocale } from "./i18n";
import { useUiStore } from "./stores/ui";
import "./styles/index.css";

async function bootstrap() {
  const app = createApp(App);
  const pinia = createPinia();

  app.use(pinia);
  app.use(router);
  app.use(i18n);

  await bootstrapLocale();

  // 初始化主题（localStorage 中已有就会生效）
  const ui = useUiStore();
  ui.applyTheme();

  app.mount("#app");
}

bootstrap();

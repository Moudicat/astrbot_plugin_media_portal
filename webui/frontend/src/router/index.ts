import { createRouter, createWebHashHistory, type RouteRecordRaw } from "vue-router";
import { useAuthStore } from "@/stores/auth";
import { useConfigStore } from "@/stores/config";
import AppLayout from "@/layouts/AppLayout.vue";

const routes: RouteRecordRaw[] = [
  {
    path: "/login",
    name: "login",
    component: () => import("@/views/LoginView.vue"),
    meta: { public: true, layout: "login" },
  },
  {
    path: "/",
    component: AppLayout,
    redirect: "/media",
    children: [
      {
        path: "/media",
        name: "media",
        component: () => import("@/views/MediaLibraryView.vue"),
      },
      {
        path: "/data",
        name: "data",
        component: () => import("@/views/DataBrowserView.vue"),
        meta: { requireData: true },
      },
    ],
  },
  { path: "/:pathMatch(.*)*", redirect: "/media" },
];

export const router = createRouter({
  history: createWebHashHistory(),
  routes,
});

router.beforeEach((to) => {
  const auth = useAuthStore();
  if (!to.meta.public && !auth.isAuthenticated) {
    return {
      name: "login",
      query: to.fullPath !== "/" ? { redirect: to.fullPath } : undefined,
    };
  }
  if (to.name === "login" && auth.isAuthenticated) {
    return { name: "media" };
  }
  if (to.meta.requireData) {
    const config = useConfigStore();
    if (config.config && config.config.expose_astrbot_data === false) {
      return { name: "media" };
    }
  }
  return true;
});

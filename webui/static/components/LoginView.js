export const LoginView = {
  name: "LoginView",
  props: {
    loading: { type: Boolean, default: false },
    error: { type: String, default: "" },
  },
  emits: ["login"],
  data() {
    return {
      password: "",
    };
  },
  methods: {
    submit() {
      if (!this.password.trim() || this.loading) {
        return;
      }
      this.$emit("login", this.password.trim());
    },
  },
  template: `
    <section class="login-page">
      <div class="login-card">
        <h1>Media Portal</h1>
        <p class="muted">多媒体管理控制台</p>
        <form @submit.prevent="submit" class="login-form">
          <label>访问密码</label>
          <input
            type="password"
            v-model="password"
            autocomplete="current-password"
            placeholder="请输入访问密码"
            :disabled="loading"
          />
          <button type="submit" :disabled="loading">
            {{ loading ? "登录中..." : "登录" }}
          </button>
          <p v-if="error" class="error">{{ error }}</p>
        </form>
      </div>
    </section>
  `,
};

import { Icon } from "./Icon.js";

export const LoginView = {
  name: "LoginView",
  components: { Icon },
  props: {
    loading: { type: Boolean, default: false },
    error: { type: String, default: "" },
    theme: { type: String, default: "dark" },
  },
  emits: ["login", "toggle-theme"],
  data() {
    return {
      password: "",
      showPassword: false,
    };
  },
  methods: {
    submit() {
      if (!this.password.trim() || this.loading) return;
      this.$emit("login", this.password.trim());
    },
  },
  template: `
    <section class="login-page">
      <div class="login-card">
        <div class="login-brand">
          <div class="brand-logo brand-logo-img">
            <img src="/static/logo.svg" alt="Media Portal" />
          </div>
          <div>
            <h1>Media Portal</h1>
            <p>多媒体管理控制台</p>
          </div>
        </div>

        <form @submit.prevent="submit" class="login-form">
          <label for="password">访问密码</label>
          <div class="input-wrap">
            <span class="icon-slot"><Icon name="lock" :size="16" /></span>
            <input
              id="password"
              :type="showPassword ? 'text' : 'password'"
              v-model="password"
              autocomplete="current-password"
              placeholder="请输入访问密码"
              :disabled="loading"
            />
            <button
              type="button"
              class="trailing"
              @click="showPassword = !showPassword"
              :title="showPassword ? '隐藏' : '显示'"
            >
              <Icon :name="showPassword ? 'eye-off' : 'eye'" :size="16" />
            </button>
          </div>

          <button type="submit" class="primary lg block" :disabled="loading || !password.trim()">
            <Icon v-if="!loading" name="log-in" :size="16" :stroke-width="2" />
            <Icon v-else name="loader" :size="16" :stroke-width="2" />
            {{ loading ? "登录中..." : "登录控制台" }}
          </button>

          <p v-if="error" class="error">
            <Icon name="circle-alert" :size="15" />
            <span>{{ error }}</span>
          </p>

          <div class="login-hint">
            <Icon name="info" :size="13" />
            若未设置密码，随机密码会在 AstrBot 控制台日志中打印。首次使用可通过指令
            <code class="mono">/media password set &lt;密码&gt;</code> 修改。
          </div>

          <div class="login-meta">
            <button type="button" class="ghost sm" @click="$emit('toggle-theme')">
              <Icon :name="theme === 'dark' ? 'sun' : 'moon'" :size="14" />
              切换{{ theme === 'dark' ? '浅色' : '深色' }}
            </button>
          </div>
        </form>
      </div>
    </section>
  `,
};

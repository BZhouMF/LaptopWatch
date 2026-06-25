import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { useAuth } from "../contexts/AuthContext";

export default function LoginPage() {
  const [account, set_account] = useState("");
  const [password, set_password] = useState("");
  const { login, is_loading, error, clear_error } = useAuth();

  const handle_submit = (event: FormEvent) => {
    event.preventDefault();
    login(account, password);
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-bg-primary p-5">
      <div className="w-full max-w-sm animate-slide-up">
        {/* Logo */}
        <div className="mb-8 text-center">
          <div className="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-2xl bg-accent">
            <svg className="h-8 w-8 text-white" fill="currentColor" viewBox="0 0 24 24">
              <path d="M17.813 4.653h.854c1.51.054 2.769.578 3.773 1.574 1.004.995 1.524 2.249 1.56 3.76v7.36c-.036 1.51-.556 2.769-1.56 3.773s-2.262 1.524-3.773 1.56H5.333c-1.51-.036-2.769-.556-3.773-1.56S.036 19.858 0 18.347v-7.36c.036-1.511.556-2.765 1.56-3.76 1.004-.996 2.262-1.52 3.773-1.574h.774l-1.174-1.12a1.234 1.234 0 01-.373-.906c0-.356.124-.658.373-.907l.027-.027c.267-.249.573-.373.92-.373.347 0 .653.124.92.373L9.653 4.44c.071.071.134.142.187.213h4.267a.836.836 0 01.16-.213l2.853-2.747c.267-.249.573-.373.92-.373.347 0 .662.151.929.4.267.249.391.551.391.907 0 .355-.124.657-.373.906zM5.333 7.24c-.746.018-1.373.276-1.88.773-.506.498-.769 1.13-.786 1.894v7.52c.017.764.28 1.395.786 1.893.507.498 1.134.756 1.88.773h13.334c.746-.017 1.373-.275 1.88-.773.506-.498.769-1.129.786-1.893v-7.52c-.017-.765-.28-1.396-.786-1.894-.507-.497-1.134-.755-1.88-.773zM8 11.107c.373 0 .684.124.933.373.25.249.383.569.4.96v1.173c-.017.391-.15.711-.4.96-.249.25-.56.374-.933.374s-.684-.125-.933-.374c-.25-.249-.383-.569-.4-.96V12.44c0-.373.129-.689.386-.947.258-.257.574-.386.947-.386zm8 0c.373 0 .684.124.933.373.25.249.383.569.4.96v1.173c-.017.391-.15.711-.4.96-.249.25-.56.374-.933.374s-.684-.125-.933-.374c-.25-.249-.383-.569-.4-.96V12.44c.017-.391.15-.711.4-.96.249-.249.56-.373.933-.373z" />
            </svg>
          </div>
          <h1 className="text-2xl font-semibold text-text-primary tracking-tight">
            LaptopWatch
          </h1>
          <p className="mt-1.5 text-sm text-text-muted">登录以继续使用</p>
        </div>

        {/* Card */}
        <div className="card rounded-xl p-8">
          <form onSubmit={handle_submit} className="flex flex-col gap-4">
            <div>
              <label htmlFor="account" className="block mb-1.5 text-sm font-medium text-text-secondary">
                账号
              </label>
              <input
                type="text"
                id="account"
                name="account"
                required
                autoComplete="off"
                value={account}
                onChange={(event) => { set_account(event.target.value); clear_error(); }}
                className="w-full h-11 rounded-lg border border-border-primary bg-bg-primary px-3.5 text-sm text-text-primary placeholder:text-text-muted outline-none transition focus:border-accent focus:ring-2 focus:ring-accent/15"
                placeholder="请输入账号"
              />
            </div>

            <div>
              <label htmlFor="password" className="block mb-1.5 text-sm font-medium text-text-secondary">
                密码
              </label>
              <input
                type="password"
                id="password"
                name="password"
                required
                value={password}
                onChange={(event) => { set_password(event.target.value); clear_error(); }}
                className="w-full h-11 rounded-lg border border-border-primary bg-bg-primary px-3.5 text-sm text-text-primary placeholder:text-text-muted outline-none transition focus:border-accent focus:ring-2 focus:ring-accent/15"
                placeholder="请输入密码"
              />
            </div>

            {error && (
              <p className="text-sm text-danger text-center">{error}</p>
            )}

            <button
              type="submit"
              disabled={is_loading}
              className="w-full h-11 rounded-lg bg-accent text-sm font-medium text-white transition-all hover:bg-accent-hover hover:shadow-md disabled:opacity-50 disabled:hover:shadow-none active:scale-[0.98]"
            >
              {is_loading ? "登录中..." : "登 录"}
            </button>
          </form>

          <p className="mt-6 text-center text-sm text-text-muted">
            没有账户？{" "}
            <Link to="/register" className="font-medium text-accent hover:text-accent-hover transition">
              立即注册
            </Link>
          </p>
        </div>
      </div>
    </div>
  );
}

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
    <div className="relative flex min-h-screen items-center justify-center bg-bg-primary p-5 overflow-hidden">
      {/* Background decoration */}
      <div className="absolute inset-0 overflow-hidden pointer-events-none">
        <div className="absolute -top-40 -right-40 w-80 h-80 rounded-full bg-accent/10 blur-3xl" />
        <div className="absolute -bottom-40 -left-40 w-80 h-80 rounded-full bg-accent/5 blur-3xl" />
      </div>

      <div className="w-full max-w-sm animate-slide-up relative">
        {/* Logo area */}
        <div className="mb-8 text-center">
          <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-2xl bg-accent-subtle border border-accent-border">
            <svg className="h-7 w-7 text-accent" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
                d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
            </svg>
          </div>
          <h1 className="text-xl font-semibold text-text-primary tracking-tight">LaptopWatch</h1>
          <p className="mt-1 text-sm text-text-muted">登录以继续</p>
        </div>

        {/* Card */}
        <div className="glass-card rounded-2xl p-6 shadow-lg">
          <form onSubmit={handle_submit} className="flex flex-col gap-4">
            <div>
              <label htmlFor="account" className="block mb-1.5 text-xs font-medium text-text-secondary">
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
                className="w-full h-11 rounded-lg border border-border-primary bg-bg-secondary px-3.5 text-sm text-text-primary placeholder:text-text-muted outline-none transition focus:border-accent focus:ring-1 focus:ring-accent/30"
                placeholder="请输入账号"
              />
            </div>

            <div>
              <label htmlFor="password" className="block mb-1.5 text-xs font-medium text-text-secondary">
                密码
              </label>
              <input
                type="password"
                id="password"
                name="password"
                required
                value={password}
                onChange={(event) => { set_password(event.target.value); clear_error(); }}
                className="w-full h-11 rounded-lg border border-border-primary bg-bg-secondary px-3.5 text-sm text-text-primary placeholder:text-text-muted outline-none transition focus:border-accent focus:ring-1 focus:ring-accent/30"
                placeholder="请输入密码"
              />
            </div>

            {error && (
              <p className="text-sm text-danger text-center">{error}</p>
            )}

            <button
              type="submit"
              disabled={is_loading}
              className="w-full h-11 rounded-lg bg-accent text-sm font-medium text-white transition-all hover:bg-accent-hover hover:shadow-lg hover:shadow-accent/20 disabled:opacity-50 disabled:hover:shadow-none active:scale-[0.98]"
            >
              {is_loading ? "登录中..." : "登 录"}
            </button>
          </form>

          <p className="mt-5 text-center text-xs text-text-muted">
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

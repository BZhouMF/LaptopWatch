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
    <div className="flex min-h-screen items-center justify-center bg-gradient-to-br from-purple-600 to-blue-500 p-4">
      <div className="w-full max-w-sm rounded-xl bg-white p-8 shadow-2xl dark:bg-zinc-900">
        <h1 className="mb-6 text-center text-2xl font-bold text-zinc-800 dark:text-zinc-100">
          LaptopWatch
        </h1>
        <form onSubmit={handle_submit} className="flex flex-col gap-4">
          <input
            type="text"
            placeholder="账号"
            value={account}
            onChange={(event) => { set_account(event.target.value); clear_error(); }}
            className="rounded-lg border border-zinc-300 px-4 py-3 text-sm outline-none transition focus:border-purple-500 dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-100"
            autoComplete="username"
          />
          <input
            type="password"
            placeholder="密码"
            value={password}
            onChange={(event) => { set_password(event.target.value); clear_error(); }}
            className="rounded-lg border border-zinc-300 px-4 py-3 text-sm outline-none transition focus:border-purple-500 dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-100"
            autoComplete="current-password"
          />
          {error && (
            <p className="text-sm text-red-500">{error}</p>
          )}
          <button
            type="submit"
            disabled={is_loading}
            className="rounded-lg bg-purple-600 py-3 text-sm font-medium text-white transition hover:bg-purple-700 disabled:opacity-50"
          >
            {is_loading ? "登录中..." : "登 录"}
          </button>
        </form>
        <p className="mt-4 text-center text-sm text-zinc-500">
          没有账号？{" "}
          <Link to="/register" className="text-purple-600 hover:underline">
            注册
          </Link>
        </p>
      </div>
    </div>
  );
}

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
    <div className="flex min-h-screen items-center justify-center bg-gradient-to-br from-indigo-500 to-purple-600 p-5">
      <div className="w-full max-w-sm rounded-2xl bg-white p-10 shadow-2xl dark:bg-zinc-900">
        <h2 className="mb-8 text-center text-2xl font-semibold text-zinc-800 dark:text-zinc-100">
          密码快速登录
        </h2>
        <form onSubmit={handle_submit} className="flex flex-col gap-5">
          <div className="relative">
            <input
              type="text"
              id="account"
              name="account"
              placeholder=" "
              required
              value={account}
              onChange={(event) => { set_account(event.target.value); clear_error(); }}
              className="peer w-full h-12 rounded-lg border border-zinc-300 px-4 pt-2 text-base outline-none transition focus:border-indigo-500 focus:ring-2 focus:ring-indigo-500/10 dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-100"
            />
            <label
              htmlFor="account"
              className="pointer-events-none absolute left-4 top-1/2 -translate-y-1/2 text-zinc-400 transition-all peer-focus:top-0 peer-focus:text-xs peer-focus:text-indigo-500 peer-[:not(:placeholder-shown)]:top-0 peer-[:not(:placeholder-shown)]:text-xs bg-white px-1 peer-focus:bg-white dark:bg-zinc-800 dark:peer-focus:bg-zinc-800"
            >
              账号
            </label>
          </div>
          <div className="relative">
            <input
              type="password"
              id="password"
              name="password"
              placeholder=" "
              required
              value={password}
              onChange={(event) => { set_password(event.target.value); clear_error(); }}
              className="peer w-full h-12 rounded-lg border border-zinc-300 px-4 pt-2 text-base outline-none transition focus:border-indigo-500 focus:ring-2 focus:ring-indigo-500/10 dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-100"
            />
            <label
              htmlFor="password"
              className="pointer-events-none absolute left-4 top-1/2 -translate-y-1/2 text-zinc-400 transition-all peer-focus:top-0 peer-focus:text-xs peer-focus:text-indigo-500 peer-[:not(:placeholder-shown)]:top-0 peer-[:not(:placeholder-shown)]:text-xs bg-white px-1 peer-focus:bg-white dark:bg-zinc-800 dark:peer-focus:bg-zinc-800"
            >
              密码
            </label>
          </div>

          {error && (
            <p className="text-center text-sm text-red-500">{error}</p>
          )}

          <button
            type="submit"
            disabled={is_loading}
            className="w-full h-12 rounded-lg bg-gradient-to-r from-indigo-500 to-purple-600 text-base font-medium text-white transition hover:translate-y-[-2px] hover:shadow-lg disabled:opacity-50 disabled:hover:translate-y-0"
          >
            {is_loading ? "登录中..." : "登录"}
          </button>
        </form>

        <p className="mt-5 text-center text-sm text-zinc-400">
          没有账户？{" "}
          <Link to="/register" className="font-medium text-indigo-500 hover:underline">
            立即注册
          </Link>
        </p>
      </div>
    </div>
  );
}

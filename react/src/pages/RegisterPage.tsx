import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import api_client from "../api/client";

const ALLOWED_CHARS = /^[a-zA-Z0-9@._\-!#$%&*+]+$/;

interface FieldErrors {
  account: string | null;
  password: string | null;
  confirm: string | null;
}

export default function RegisterPage() {
  const [account, set_account] = useState("");
  const [password, set_password] = useState("");
  const [confirm_password, set_confirm_password] = useState("");
  const [is_loading, set_is_loading] = useState(false);
  const [server_error, set_server_error] = useState<string | null>(null);
  const [field_errors, set_field_errors] = useState<FieldErrors>({
    account: null,
    password: null,
    confirm: null,
  });
  const navigate = useNavigate();

  const validate = (): boolean => {
    const errors: FieldErrors = { account: null, password: null, confirm: null };
    let valid = true;

    if (!ALLOWED_CHARS.test(account)) {
      errors.account = "账号包含不允许的字符";
      valid = false;
    }
    if (!ALLOWED_CHARS.test(password)) {
      errors.password = "密码包含不允许的字符";
      valid = false;
    }
    if (password !== confirm_password) {
      errors.confirm = "两次输入的密码不一致";
      valid = false;
    }
    set_field_errors(errors);
    return valid;
  };

  const clear_field_error = (field: keyof FieldErrors) => {
    set_field_errors((prev) => ({ ...prev, [field]: null }));
    set_server_error(null);
  };

  const handle_submit = async (event: FormEvent) => {
    event.preventDefault();
    set_server_error(null);
    if (!validate()) return;

    set_is_loading(true);
    try {
      const form_data = new URLSearchParams();
      form_data.append("account", account);
      form_data.append("password", password);
      form_data.append("confirm_password", confirm_password);
      const resp = await api_client.post("/register", form_data, {
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
      });
      if (resp.data?.code !== 0) {
        set_server_error(resp.data?.msg || "注册失败");
        return;
      }
      navigate("/login", { replace: true });
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { msg?: string } } })?.response?.data?.msg;
      set_server_error(msg || "注册失败");
    } finally {
      set_is_loading(false);
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-gradient-to-br from-indigo-500 to-purple-600 p-5">
      <div className="w-full max-w-sm rounded-2xl bg-white p-10 shadow-2xl dark:bg-zinc-900">
        <h2 className="mb-8 text-center text-2xl font-semibold text-zinc-800 dark:text-zinc-100">
          注册账号
        </h2>

        <form onSubmit={handle_submit} className="flex flex-col gap-4">
          <div>
            <div className="relative">
              <input
                type="text"
                placeholder=" "
                required
                maxLength={32}
                autoComplete="off"
                value={account}
                onChange={(event) => { set_account(event.target.value); clear_field_error("account"); }}
                className={`peer w-full h-12 rounded-lg border px-4 pt-2 text-base outline-none transition focus:ring-2 focus:ring-indigo-500/10 dark:bg-zinc-800 dark:text-zinc-100 ${
                  field_errors.account
                    ? "border-red-400 focus:border-red-400"
                    : "border-zinc-300 focus:border-indigo-500 dark:border-zinc-700"
                }`}
              />
              <label className="pointer-events-none absolute left-4 top-1/2 -translate-y-1/2 text-zinc-400 transition-all peer-focus:top-0 peer-focus:text-xs peer-focus:text-indigo-500 peer-[:not(:placeholder-shown)]:top-0 peer-[:not(:placeholder-shown)]:text-xs bg-white px-1 peer-focus:bg-white dark:bg-zinc-800 dark:peer-focus:bg-zinc-800">
                请输入账号
              </label>
            </div>
            <p className="mt-1 text-xs text-zinc-400">
              仅限数字、英文字母及 @ . _ - ! # $ % &amp; * +
            </p>
            {field_errors.account && (
              <p className="mt-1 text-sm text-red-500">{field_errors.account}</p>
            )}
          </div>

          <div>
            <div className="relative">
              <input
                type="password"
                placeholder=" "
                required
                maxLength={64}
                value={password}
                onChange={(event) => { set_password(event.target.value); clear_field_error("password"); }}
                className={`peer w-full h-12 rounded-lg border px-4 pt-2 text-base outline-none transition focus:ring-2 focus:ring-indigo-500/10 dark:bg-zinc-800 dark:text-zinc-100 ${
                  field_errors.password
                    ? "border-red-400 focus:border-red-400"
                    : "border-zinc-300 focus:border-indigo-500 dark:border-zinc-700"
                }`}
              />
              <label className="pointer-events-none absolute left-4 top-1/2 -translate-y-1/2 text-zinc-400 transition-all peer-focus:top-0 peer-focus:text-xs peer-focus:text-indigo-500 peer-[:not(:placeholder-shown)]:top-0 peer-[:not(:placeholder-shown)]:text-xs bg-white px-1 peer-focus:bg-white dark:bg-zinc-800 dark:peer-focus:bg-zinc-800">
                请输入密码
              </label>
            </div>
            <p className="mt-1 text-xs text-zinc-400">
              仅限数字、英文字母及 @ . _ - ! # $ % &amp; * +
            </p>
            {field_errors.password && (
              <p className="mt-1 text-sm text-red-500">{field_errors.password}</p>
            )}
          </div>

          <div>
            <div className="relative">
              <input
                type="password"
                placeholder=" "
                required
                maxLength={64}
                value={confirm_password}
                onChange={(event) => { set_confirm_password(event.target.value); clear_field_error("confirm"); }}
                className={`peer w-full h-12 rounded-lg border px-4 pt-2 text-base outline-none transition focus:ring-2 focus:ring-indigo-500/10 dark:bg-zinc-800 dark:text-zinc-100 ${
                  field_errors.confirm
                    ? "border-red-400 focus:border-red-400"
                    : "border-zinc-300 focus:border-indigo-500 dark:border-zinc-700"
                }`}
              />
              <label className="pointer-events-none absolute left-4 top-1/2 -translate-y-1/2 text-zinc-400 transition-all peer-focus:top-0 peer-focus:text-xs peer-focus:text-indigo-500 peer-[:not(:placeholder-shown)]:top-0 peer-[:not(:placeholder-shown)]:text-xs bg-white px-1 peer-focus:bg-white dark:bg-zinc-800 dark:peer-focus:bg-zinc-800">
                请再次输入密码
              </label>
            </div>
            {field_errors.confirm && (
              <p className="mt-1 text-sm text-red-500">{field_errors.confirm}</p>
            )}
          </div>

          {server_error && (
            <p className="text-center text-sm text-red-500">{server_error}</p>
          )}

          <div className="flex gap-3 mt-2">
            <button
              type="submit"
              disabled={is_loading}
              className="flex-1 h-12 rounded-lg bg-gradient-to-r from-indigo-500 to-purple-600 text-base font-medium text-white transition hover:translate-y-[-2px] hover:shadow-lg disabled:opacity-50"
            >
              {is_loading ? "注册中..." : "注册"}
            </button>
            <button
              type="button"
              onClick={() => navigate("/login")}
              className="w-24 h-12 rounded-lg border border-zinc-300 bg-zinc-100 text-base text-zinc-600 transition hover:bg-zinc-200 dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-400 dark:hover:bg-zinc-700"
            >
              返回
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

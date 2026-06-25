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

  const input_class = (has_error: boolean) =>
    `w-full h-11 rounded-lg border bg-bg-secondary px-3.5 text-sm text-text-primary placeholder:text-text-muted outline-none transition focus:ring-1 focus:ring-accent/30 ${
      has_error
        ? "border-danger focus:border-danger"
        : "border-border-primary focus:border-accent"
    }`;

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
          <p className="mt-1 text-sm text-text-muted">创建新账户</p>
        </div>

        {/* Card */}
        <div className="glass-card rounded-2xl p-6 shadow-lg">
          <form onSubmit={handle_submit} className="flex flex-col gap-4">
            <div>
              <label className="block mb-1.5 text-xs font-medium text-text-secondary">账号</label>
              <input
                type="text"
                placeholder="请输入账号"
                required
                maxLength={32}
                autoComplete="off"
                value={account}
                onChange={(event) => { set_account(event.target.value); clear_field_error("account"); }}
                className={input_class(!!field_errors.account)}
              />
              <p className="mt-1 text-[11px] text-text-muted">
                仅限数字、英文字母及 @ . _ - ! # $ % &amp; * +
              </p>
              {field_errors.account && (
                <p className="mt-1 text-xs text-danger">{field_errors.account}</p>
              )}
            </div>

            <div>
              <label className="block mb-1.5 text-xs font-medium text-text-secondary">密码</label>
              <input
                type="password"
                placeholder="请输入密码"
                required
                maxLength={64}
                value={password}
                onChange={(event) => { set_password(event.target.value); clear_field_error("password"); }}
                className={input_class(!!field_errors.password)}
              />
              <p className="mt-1 text-[11px] text-text-muted">
                仅限数字、英文字母及 @ . _ - ! # $ % &amp; * +
              </p>
              {field_errors.password && (
                <p className="mt-1 text-xs text-danger">{field_errors.password}</p>
              )}
            </div>

            <div>
              <label className="block mb-1.5 text-xs font-medium text-text-secondary">确认密码</label>
              <input
                type="password"
                placeholder="请再次输入密码"
                required
                maxLength={64}
                value={confirm_password}
                onChange={(event) => { set_confirm_password(event.target.value); clear_field_error("confirm"); }}
                className={input_class(!!field_errors.confirm)}
              />
              {field_errors.confirm && (
                <p className="mt-1 text-xs text-danger">{field_errors.confirm}</p>
              )}
            </div>

            {server_error && (
              <p className="text-sm text-danger text-center">{server_error}</p>
            )}

            <div className="flex gap-3 mt-1">
              <button
                type="submit"
                disabled={is_loading}
                className="flex-1 h-11 rounded-lg bg-accent text-sm font-medium text-white transition-all hover:bg-accent-hover hover:shadow-lg hover:shadow-accent/20 disabled:opacity-50 disabled:hover:shadow-none active:scale-[0.98]"
              >
                {is_loading ? "注册中..." : "注 册"}
              </button>
              <button
                type="button"
                onClick={() => navigate("/login")}
                className="w-24 h-11 rounded-lg border border-border-primary bg-bg-secondary text-sm text-text-secondary transition hover:bg-bg-card-hover hover:text-text-primary"
              >
                返回
              </button>
            </div>
          </form>
        </div>
      </div>
    </div>
  );
}

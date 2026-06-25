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
    `w-full h-11 rounded-lg border bg-bg-primary px-3.5 text-sm text-text-primary placeholder:text-text-muted outline-none transition focus:ring-2 focus:ring-accent/15 ${
      has_error
        ? "border-danger focus:border-danger"
        : "border-border-primary focus:border-accent"
    }`;

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
          <h1 className="text-2xl font-semibold text-text-primary tracking-tight">LaptopWatch</h1>
          <p className="mt-1.5 text-sm text-text-muted">创建新账户</p>
        </div>

        {/* Card */}
        <div className="card rounded-xl p-8">
          <form onSubmit={handle_submit} className="flex flex-col gap-4">
            <div>
              <label className="block mb-1.5 text-sm font-medium text-text-secondary">账号</label>
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
              <p className="mt-1 text-xs text-text-muted">
                仅限数字、英文字母及 @ . _ - ! # $ % &amp; * +
              </p>
              {field_errors.account && (
                <p className="mt-1 text-xs text-danger">{field_errors.account}</p>
              )}
            </div>

            <div>
              <label className="block mb-1.5 text-sm font-medium text-text-secondary">密码</label>
              <input
                type="password"
                placeholder="请输入密码"
                required
                maxLength={64}
                value={password}
                onChange={(event) => { set_password(event.target.value); clear_field_error("password"); }}
                className={input_class(!!field_errors.password)}
              />
              <p className="mt-1 text-xs text-text-muted">
                仅限数字、英文字母及 @ . _ - ! # $ % &amp; * +
              </p>
              {field_errors.password && (
                <p className="mt-1 text-xs text-danger">{field_errors.password}</p>
              )}
            </div>

            <div>
              <label className="block mb-1.5 text-sm font-medium text-text-secondary">确认密码</label>
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
                className="flex-1 h-11 rounded-lg bg-accent text-sm font-medium text-white transition-all hover:bg-accent-hover hover:shadow-md disabled:opacity-50 disabled:hover:shadow-none active:scale-[0.98]"
              >
                {is_loading ? "注册中..." : "注 册"}
              </button>
              <button
                type="button"
                onClick={() => navigate("/login")}
                className="w-24 h-11 rounded-lg border border-border-primary bg-bg-primary text-sm text-text-secondary transition hover:bg-bg-card-hover hover:text-text-primary"
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

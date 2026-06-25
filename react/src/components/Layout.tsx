import { Outlet, useNavigate } from "react-router-dom";
import { useAuth } from "../contexts/AuthContext";

export default function Layout() {
  const { logout } = useAuth();
  const navigate = useNavigate();

  return (
    <div className="flex min-h-screen flex-col bg-bg-primary text-text-primary">
      <header className="flex items-center justify-between border-b border-zinc-700/50 bg-bg-secondary px-6 py-3">
        <button
          onClick={() => navigate("/")}
          className="text-lg font-semibold tracking-wide text-text-primary hover:text-accent-hover transition"
        >
          LaptopWatch
        </button>
        <button
          onClick={logout}
          className="rounded-lg px-3 py-1.5 text-sm text-text-secondary hover:bg-bg-card hover:text-text-primary transition"
        >
          登出
        </button>
      </header>
      <main className="flex-1">
        <Outlet />
      </main>
    </div>
  );
}

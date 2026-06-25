import { Outlet } from "react-router-dom";

export default function Layout() {
  return (
    <div className="flex min-h-screen flex-col bg-bg-primary text-text-primary">
      <Outlet />
    </div>
  );
}

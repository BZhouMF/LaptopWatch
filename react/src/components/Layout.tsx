import { Outlet, useLocation } from "react-router-dom";

export default function Layout() {
  const location = useLocation();

  return (
    <div className="flex min-h-screen flex-col bg-bg-primary text-text-primary">
      <div key={location.pathname} className="animate-fade-in flex flex-1 flex-col">
        <Outlet />
      </div>
    </div>
  );
}

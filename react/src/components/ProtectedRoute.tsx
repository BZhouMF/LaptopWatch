import { useState, useEffect } from "react";
import { Navigate, Outlet } from "react-router-dom";
import api_client from "../api/client";

export default function ProtectedRoute() {
  const [is_checking, set_is_checking] = useState(true);
  const [is_authenticated, set_is_authenticated] = useState(false);

  useEffect(() => {
    let cancelled = false;
    api_client
      .get("/api/check_path?path=")
      .then(() => {
        if (!cancelled) set_is_authenticated(true);
      })
      .catch(() => {
        if (!cancelled) set_is_authenticated(false);
      })
      .finally(() => {
        if (!cancelled) set_is_checking(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  if (is_checking) {
    return (
      <div className="flex h-screen items-center justify-center bg-bg-primary">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-accent/20 border-t-accent" />
      </div>
    );
  }

  if (!is_authenticated) {
    const redirect = window.location.pathname + window.location.search;
    return <Navigate to={`/login?redirect=${encodeURIComponent(redirect)}`} replace />;
  }

  return <Outlet />;
}

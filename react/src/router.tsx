import type { JSX } from "react";
import { Routes, Route } from "react-router-dom";
import ProtectedRoute from "./components/ProtectedRoute";
import Layout from "./components/Layout";
import LoginPage from "./pages/LoginPage";
import RegisterPage from "./pages/RegisterPage";
import HomePage from "./pages/HomePage";
import BrowsePage from "./pages/BrowsePage";
import CategoryBrowsePage from "./pages/CategoryBrowsePage";
import MediaPlayerPage from "./pages/MediaPlayerPage";
import TextViewerPage from "./pages/TextViewerPage";
import NotFoundPage from "./pages/NotFoundPage";

export default function AppRouter(): JSX.Element {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/register" element={<RegisterPage />} />
      <Route element={<ProtectedRoute />}>
        <Route element={<Layout />}>
          <Route path="/" element={<HomePage />} />
          <Route path="/browse/*" element={<BrowsePage />} />
          <Route path="/category/*" element={<CategoryBrowsePage />} />
          <Route path="/media/player" element={<MediaPlayerPage />} />
          <Route path="/file/text/*" element={<TextViewerPage />} />
        </Route>
      </Route>
      <Route path="*" element={<NotFoundPage />} />
    </Routes>
  );
}

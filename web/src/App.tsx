import { lazy, Suspense } from "react";
import { Route, Routes } from "react-router-dom";
import { Layout } from "./components/Layout";
import HomePage from "./pages/HomePage";

// La home est dans le bundle principal ; les autres routes sont chargées à la demande.
const PlayPage = lazy(() => import("./pages/PlayPage"));
const HowItWorksPage = lazy(() => import("./pages/HowItWorksPage"));
const LoginPage = lazy(() => import("./pages/LoginPage"));
// Backoffice : hors de la mise en page publique, aucun lien depuis le site.
const AdminLayout = lazy(() => import("./pages/admin/AdminLayout"));
const AdminHomePage = lazy(() => import("./pages/admin/AdminPages").then((m) => ({ default: m.AdminHomePage })));
const AdminSourcesPage = lazy(() => import("./pages/admin/AdminPages").then((m) => ({ default: m.AdminSourcesPage })));
const AdminArticlesPage = lazy(() => import("./pages/admin/AdminPages").then((m) => ({ default: m.AdminArticlesPage })));
const AdminTopicsPage = lazy(() => import("./pages/admin/AdminPages").then((m) => ({ default: m.AdminTopicsPage })));
const NotFoundPage = lazy(() => import("./pages/NotFoundPage"));

export function AppRoutes() {
  return (
    <Suspense fallback={<p role="status">Chargement…</p>}>
      <Routes>
        <Route path="admin" element={<AdminLayout />}>
          <Route index element={<AdminHomePage />} />
          <Route path="sources" element={<AdminSourcesPage />} />
          <Route path="articles" element={<AdminArticlesPage />} />
          <Route path="sujets" element={<AdminTopicsPage />} />
          <Route path="*" element={<AdminHomePage />} />
        </Route>
        <Route element={<Layout />}>
          <Route index element={<HomePage />} />
          <Route path="jouer" element={<PlayPage />} />
          <Route path="comment-ca-marche" element={<HowItWorksPage />} />
          <Route path="connexion" element={<LoginPage />} />
          <Route path="*" element={<NotFoundPage />} />
        </Route>
      </Routes>
    </Suspense>
  );
}

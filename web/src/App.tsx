import { lazy, Suspense } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import { Layout } from "./components/Layout";
import HomePage from "./pages/HomePage";

// La home est dans le bundle principal ; les autres routes sont chargées à la demande.
const ComposerPage = lazy(() => import("./pages/ComposerPage"));
const EditionPage = lazy(() => import("./pages/EditionPage"));
const ArchivesPage = lazy(() => import("./pages/ArchivesPage"));
const HowItWorksPage = lazy(() => import("./pages/HowItWorksPage"));
const LoginPage = lazy(() => import("./pages/LoginPage"));
// Backoffice : hors de la mise en page publique, aucun lien depuis le site.
const AdminLayout = lazy(() => import("./pages/admin/AdminLayout"));
const AdminHomePage = lazy(() => import("./pages/admin/AdminPages").then((m) => ({ default: m.AdminHomePage })));
const AdminSourcesPage = lazy(() => import("./pages/admin/AdminSourcesPage"));
const AdminArticlesPage = lazy(() => import("./pages/admin/AdminArticlesPage"));
const AdminTopicsPage = lazy(() => import("./pages/admin/AdminTopicsPage"));
const AdminTopicDetailPage = lazy(() => import("./pages/admin/AdminTopicDetailPage"));
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
          <Route path="sujets/:id" element={<AdminTopicDetailPage />} />
          <Route path="*" element={<AdminHomePage />} />
        </Route>
        <Route element={<Layout />}>
          <Route index element={<HomePage />} />
          <Route path="composer" element={<ComposerPage />} />
          <Route path="jouer" element={<Navigate to="/composer" replace />} />
          <Route path="une/:date" element={<EditionPage />} />
          <Route path="archives" element={<ArchivesPage />} />
          <Route path="comment-ca-marche" element={<HowItWorksPage />} />
          <Route path="connexion" element={<LoginPage />} />
          <Route path="*" element={<NotFoundPage />} />
        </Route>
      </Routes>
    </Suspense>
  );
}

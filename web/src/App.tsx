import { lazy, Suspense } from "react";
import { Route, Routes } from "react-router-dom";
import { Layout } from "./components/Layout";
import HomePage from "./pages/HomePage";

// La home est dans le bundle principal ; les autres routes sont chargées à la demande.
const PlayPage = lazy(() => import("./pages/PlayPage"));
const HowItWorksPage = lazy(() => import("./pages/HowItWorksPage"));
const LoginPage = lazy(() => import("./pages/LoginPage"));
const NotFoundPage = lazy(() => import("./pages/NotFoundPage"));

export function AppRoutes() {
  return (
    <Suspense fallback={<p role="status">Chargement…</p>}>
      <Routes>
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

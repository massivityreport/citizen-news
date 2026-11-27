import { afterEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { AppRoutes } from "../../App";
import type { AdminFeedbackDetail, AdminFeedbackItem } from "../../api/types";
import { formatClock, formatFull } from "../../lib/format";
import { renderWithProviders } from "../../test/utils";
import { bodiesOf, res, stubFetch, type Handler } from "../../test/api-stub";

afterEach(() => vi.unstubAllGlobals());

const ME: Record<string, Handler> = { "GET /api/admin/me": () => res(200, { authenticated: true }) };
const open = (route: string) => renderWithProviders(<AppRoutes />, route);

const item = (over: Partial<AdminFeedbackItem> = {}): AdminFeedbackItem => ({
  id: 7,
  created_at: "2026-11-26T10:00:00Z",
  kind: "problem",
  email: "visiteur@example.org",
  page_name: "Accueil",
  page_url: "/",
  excerpt: "Le bouton ne répond pas",
  is_read: false,
  answered: false,
  ...over,
});
const page = (items: AdminFeedbackItem[], unread = 1) => ({ items, total: items.length, unread_count: unread, page: 1, page_size: 50 });
const detail = (over: Partial<AdminFeedbackDetail> = {}): AdminFeedbackDetail => ({
  id: 7,
  created_at: "2026-11-26T10:00:00Z",
  kind: "problem",
  email: "visiteur@example.org",
  message: "Le bouton ne répond pas du tout\nsur mon téléphone.",
  page_name: "Accueil",
  page_url: "/une/2026-11-26?x=1",
  screen: "390x844",
  browser: "TestBrowser/1.0",
  recent_actions: [
    { type: "page", at: "2026-11-26T09:58:00Z", page: "/composer" },
    { type: "topic_added", at: "2026-11-26T09:59:00Z", topic_id: 12 },
    { type: "login", at: "2026-11-26T09:59:30Z" },
  ],
  is_read: false,
  answered: false,
  replies: [],
  ...over,
});

describe("onglet Avis : menu et liste", () => {
  it("l'onglet affiche le nombre de non lus ; rien à 0", async () => {
    stubFetch({ ...ME, "GET /api/admin/feedback/unread-count": () => res(200, { unread_count: 3 }), "GET /api/admin/feedback": () => res(200, page([item()], 3)) });
    const { unmount } = open("/admin/avis");
    const nav = within(await screen.findByRole("navigation", { name: /administration/i }));
    const link = await nav.findByRole("link", { name: /Avis.*3 non lus/ });
    expect(link).toHaveAttribute("href", "/admin/avis");
    unmount();
    stubFetch({ ...ME, "GET /api/admin/feedback/unread-count": () => res(200, { unread_count: 0 }), "GET /api/admin/feedback": () => res(200, page([], 0)) });
    open("/admin/avis");
    expect(await within(await screen.findByRole("navigation", { name: /administration/i })).findByRole("link", { name: "Avis" })).toBeInTheDocument();
  });

  it("liste : date, type, e-mail, page, début du message, marque non lu ; pas de marque répondu tant qu'il n'y en a pas", async () => {
    stubFetch({
      ...ME,
      "GET /api/admin/feedback/unread-count": () => res(200, { unread_count: 1 }),
      "GET /api/admin/feedback": () => res(200, page([item(), item({ id: 6, is_read: true, kind: "idea", email: "b@example.org", excerpt: "Une idée" })], 1)),
    });
    open("/admin/avis");
    const table = await screen.findByRole("table", { name: /Avis : 2/ });
    const [, first, second] = within(table).getAllByRole("row");
    expect(within(first).getByRole("link", { name: /Le bouton ne répond pas/ })).toHaveAttribute("href", "/admin/avis/7");
    expect(first).toHaveTextContent("Problème");
    expect(first).toHaveTextContent("visiteur@example.org");
    expect(first).toHaveTextContent("Accueil");
    expect(first).toHaveTextContent("Non lu");
    expect(second).toHaveTextContent("Idée");
    expect(second).not.toHaveTextContent("Non lu");
    expect(table).not.toHaveTextContent("Répondu");
  });

  it("marque « répondu » quand l'API le dit", async () => {
    stubFetch({ ...ME, "GET /api/admin/feedback/unread-count": () => res(200, { unread_count: 0 }), "GET /api/admin/feedback": () => res(200, page([item({ is_read: true, answered: true })], 0)) });
    open("/admin/avis");
    expect(await screen.findByText("Répondu")).toBeInTheDocument();
  });

  it("filtre « non lus seulement » : unread_only dans l'appel", async () => {
    const calls: string[] = [];
    stubFetch({
      ...ME,
      "GET /api/admin/feedback/unread-count": () => res(200, { unread_count: 1 }),
      "GET /api/admin/feedback": (_i, url) => {
        calls.push(url);
        return res(200, page([item()], 1));
      },
    });
    open("/admin/avis");
    await screen.findByRole("table");
    expect(calls[0]).not.toContain("unread_only");
    await userEvent.click(screen.getByRole("checkbox", { name: "Non lus seulement" }));
    await waitFor(() => expect(calls.at(-1)).toContain("unread_only=true"));
  });

  it("liste vide, vide filtrée et erreur", async () => {
    stubFetch({ ...ME, "GET /api/admin/feedback/unread-count": () => res(200, { unread_count: 0 }), "GET /api/admin/feedback": () => res(200, page([], 0)) });
    const { unmount } = open("/admin/avis");
    expect(await screen.findByText("Aucun avis pour le moment.")).toBeInTheDocument();
    unmount();
    stubFetch({ ...ME, "GET /api/admin/feedback/unread-count": () => res(200, { unread_count: 0 }), "GET /api/admin/feedback": () => res(200, page([], 0)) });
    open("/admin/avis?unread_only=true");
    expect(await screen.findByText("Aucun avis non lu.")).toBeInTheDocument();
    stubFetch({ ...ME, "GET /api/admin/feedback/unread-count": () => res(200, { unread_count: 0 }), "GET /api/admin/feedback": () => res(500, {}) });
    open("/admin/avis");
    expect((await screen.findAllByRole("alert"))[0]).toHaveTextContent("Impossible de charger les avis");
  });
});

describe("détail d'un avis", () => {
  const routes = (over: Record<string, Handler> = {}) => ({
    ...ME,
    "GET /api/admin/feedback/unread-count": () => res(200, { unread_count: 1 }),
    "GET /api/admin/feedback/7": () => res(200, detail()),
    "GET /api/admin/feedback": () => res(200, page([item()], 1)),
    "POST /api/admin/feedback/7/read": () => res(200, detail({ is_read: true })),
    "POST /api/admin/feedback/7/unread": () => res(200, detail({ is_read: false })),
    ...over,
  });

  it("affiche tout : message complet, e-mail, page (nom et adresse), écran, navigateur, parcours avec l'heure", async () => {
    stubFetch(routes());
    open("/admin/avis/7");
    expect(await screen.findByRole("heading", { level: 1, name: /Avis/ })).toBeInTheDocument();
    expect(await screen.findByText(/Le bouton ne répond pas du tout/)).toHaveTextContent("sur mon téléphone.");
    expect(screen.getByText("visiteur@example.org")).toBeInTheDocument();
    expect(screen.getByText("Accueil", { selector: "dd" })).toBeInTheDocument();
    expect(screen.getByText("/une/2026-11-26?x=1")).toBeInTheDocument();
    expect(screen.getByText("390x844")).toBeInTheDocument();
    expect(screen.getByText("TestBrowser/1.0")).toBeInTheDocument();
    const journey = screen.getByRole("list", { name: "Parcours récent" });
    const lines = within(journey).getAllByRole("listitem");
    expect(lines).toHaveLength(3);
    expect(lines[0]).toHaveTextContent(formatClock("2026-11-26T09:58:00Z"));
    expect(lines[0]).toHaveTextContent("/composer");
    expect(lines[1]).toHaveTextContent("Sujet 12 ajouté");
    expect(lines[2]).toHaveTextContent("Connexion");
  });

  it("sans parcours joint : le dit", async () => {
    stubFetch(routes({ "GET /api/admin/feedback/7": () => res(200, detail({ recent_actions: null })) }));
    open("/admin/avis/7");
    expect(await screen.findByText("Parcours non joint par le visiteur.")).toBeInTheDocument();
    expect(screen.queryByRole("list", { name: "Parcours récent" })).toBeNull();
  });

  it("l'ouvrir le passe en lu ; le bouton le remet en non lu", async () => {
    let read = false; // l'état que garde le serveur
    const fn = stubFetch(
      routes({
        "GET /api/admin/feedback/7": () => res(200, detail({ is_read: read })),
        "POST /api/admin/feedback/7/read": () => ((read = true), res(200, detail({ is_read: true }))),
        "POST /api/admin/feedback/7/unread": () => ((read = false), res(200, detail({ is_read: false }))),
      }),
    );
    open("/admin/avis/7");
    await waitFor(() => expect(bodiesOf(fn, "POST /api/admin/feedback/7/read")).toHaveLength(1));
    await userEvent.click(await screen.findByRole("button", { name: "Marquer comme non lu" }));
    await waitFor(() => expect(bodiesOf(fn, "POST /api/admin/feedback/7/unread")).toHaveLength(1));
    // remis non lu : la page ne le repasse pas en lu toute seule
    expect(bodiesOf(fn, "POST /api/admin/feedback/7/read")).toHaveLength(1);
  });

  it("supprimer : confirmation d'abord, annuler ne supprime rien, confirmer supprime et revient à la liste", async () => {
    const fn = stubFetch(routes({ "DELETE /api/admin/feedback/7": () => res(204) }));
    open("/admin/avis/7");
    await userEvent.click(await screen.findByRole("button", { name: "Supprimer" }));
    const dialog = screen.getByRole("dialog");
    expect(dialog).toHaveTextContent("définitivement");
    await userEvent.click(within(dialog).getByRole("button", { name: "Annuler" }));
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(bodiesOf(fn, "DELETE /api/admin/feedback/7")).toHaveLength(0);
    await userEvent.click(screen.getByRole("button", { name: "Supprimer" }));
    await userEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Supprimer définitivement" }));
    await waitFor(() => expect(bodiesOf(fn, "DELETE /api/admin/feedback/7")).toHaveLength(1));
    expect(await screen.findByRole("table", { name: /Avis/ })).toBeInTheDocument();
  });

  describe("réponses par e-mail", () => {
    const reply = (id: number, message: string, created_at: string) => ({ id, message, created_at });

    it("historique des réponses avec leur date, sous l'avis", async () => {
      stubFetch(
        routes({
          "GET /api/admin/feedback/7": () =>
            res(200, detail({ answered: true, replies: [reply(1, "Première réponse", "2026-11-26T11:00:00Z"), reply(2, "Seconde réponse", "2026-11-27T08:30:00Z")] })),
        }),
      );
      open("/admin/avis/7");
      const history = await screen.findByRole("list", { name: "Réponses envoyées" });
      const items = within(history).getAllByRole("listitem");
      expect(items).toHaveLength(2);
      expect(items[0]).toHaveTextContent("Première réponse");
      expect(items[0]).toHaveTextContent(formatFull("2026-11-26T11:00:00Z"));
      expect(items[1]).toHaveTextContent("Seconde réponse");
    });

    it("sans réponse : le dit", async () => {
      stubFetch(routes());
      open("/admin/avis/7");
      expect(await screen.findByText("Aucune réponse envoyée.")).toBeInTheDocument();
    });

    it("envoyer : le texte part à l'API, le champ se vide et la réponse apparaît", async () => {
      let replies: ReturnType<typeof reply>[] = [];
      const fn = stubFetch(
        routes({
          "GET /api/admin/feedback/7": () => res(200, detail({ replies, answered: replies.length > 0 })),
          "POST /api/admin/feedback/7/replies": () => ((replies = [reply(1, "Merci !", "2026-11-27T09:00:00Z")]), res(201, detail({ replies, answered: true }))),
        }),
      );
      open("/admin/avis/7");
      const box = await screen.findByRole("textbox", { name: /Votre réponse/ });
      await userEvent.type(box, "  Merci !  ");
      await userEvent.click(screen.getByRole("button", { name: "Envoyer la réponse" }));
      await waitFor(() => expect(bodiesOf(fn, "POST /api/admin/feedback/7/replies")).toEqual([{ message: "Merci !" }]));
      expect(await screen.findByRole("list", { name: "Réponses envoyées" })).toHaveTextContent("Merci !");
      expect(box).toHaveValue("");
    });

    it("réponse vide : bouton inactif, rien n'est envoyé", async () => {
      const fn = stubFetch(routes());
      open("/admin/avis/7");
      const button = await screen.findByRole("button", { name: "Envoyer la réponse" });
      expect(button).toBeDisabled();
      await userEvent.type(screen.getByRole("textbox", { name: /Votre réponse/ }), "   ");
      expect(button).toBeDisabled();
      expect(bodiesOf(fn, "POST /api/admin/feedback/7/replies")).toHaveLength(0);
    });

    it("échec d'envoi : message d'erreur, texte conservé pour réessayer, rien dans l'historique", async () => {
      let fail = true;
      const fn = stubFetch(
        routes({
          "POST /api/admin/feedback/7/replies": () =>
            fail ? res(502, { detail: "L'e-mail n'a pas pu être envoyé : la réponse n'est pas enregistrée, réessayez." }) : res(201, detail({ answered: true, replies: [reply(1, "Merci !", "2026-11-27T09:00:00Z")] })),
        }),
      );
      open("/admin/avis/7");
      const box = await screen.findByRole("textbox", { name: /Votre réponse/ });
      await userEvent.type(box, "Merci !");
      await userEvent.click(screen.getByRole("button", { name: "Envoyer la réponse" }));
      expect(await screen.findByRole("alert")).toHaveTextContent("L'e-mail n'a pas pu être envoyé");
      expect(box).toHaveValue("Merci !");
      expect(screen.queryByRole("list", { name: "Réponses envoyées" })).toBeNull();
      fail = false;
      await userEvent.click(screen.getByRole("button", { name: "Envoyer la réponse" }));
      await waitFor(() => expect(bodiesOf(fn, "POST /api/admin/feedback/7/replies")).toHaveLength(2));
      await waitFor(() => expect(screen.queryByRole("alert")).toBeNull());
    });
  });

  it("avis introuvable", async () => {
    stubFetch(routes({ "GET /api/admin/feedback/7": () => res(404, { detail: "Avis introuvable." }) }));
    open("/admin/avis/7");
    expect(await screen.findByText("Cet avis n’existe pas (ou plus).")).toBeInTheDocument();
  });
});

describe("site public", () => {
  it("aucun onglet Avis ni appel admin sur le site public", async () => {
    const fn = stubFetch({ "GET /api/me": () => res(401, { detail: "x" }) });
    open("/comment-ca-marche");
    await screen.findByRole("heading", { level: 1 });
    expect(screen.queryByRole("link", { name: /^Avis/ })).toBeNull();
    expect(fn.mock.calls.some(([u]) => String(u).includes("/api/admin"))).toBe(false);
  });
});

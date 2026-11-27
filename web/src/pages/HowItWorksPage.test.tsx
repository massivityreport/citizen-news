import { afterEach, describe, expect, it, vi } from "vitest";
import { screen, within } from "@testing-library/react";
import { renderApp } from "../test/utils";
import { res, stubFetch } from "../test/api-stub";

afterEach(() => vi.unstubAllGlobals());

describe("Comment ça marche (provisoire)", () => {
  it("résume le principe et renvoie vers la composition", async () => {
    stubFetch({ "GET /api/me": () => res(401, {}) });
    renderApp("/comment-ca-marche");
    expect(await screen.findByRole("heading", { level: 1, name: "Comment ça marche" })).toBeInTheDocument();
    expect(screen.getByText(/jusqu’à 17 h/)).toBeInTheDocument();
    expect(within(screen.getByRole("main")).getByRole("link", { name: "Composer ma une" })).toHaveAttribute("href", "/composer");
  });
});

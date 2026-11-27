import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { SourceList } from "./SourceList";

describe("SourceList", () => {
  it("tolère une source sans date : lien affiché, aucune date", () => {
    const { container } = render(
      <SourceList sources={[{ name: "Le Monde", url: "https://example.org/a", title: "A", published_at: null }]} />,
    );
    expect(screen.getByRole("link")).toHaveTextContent("Le Monde");
    expect(container.textContent).not.toMatch(/Invalid Date|NaN|null|undefined|·/);
  });

  it("affiche la date des sources datées seulement", () => {
    const { container } = render(
      <SourceList
        sources={[
          { name: "Le Monde", url: "https://example.org/a", title: "A", published_at: null },
          { name: "Libération", url: "https://example.org/b", title: "B", published_at: "2020-01-02T08:00:00Z" },
        ]}
      />,
    );
    const items = container.querySelectorAll("li");
    expect(items[0].textContent).not.toContain("·");
    expect(items[1].textContent).toContain("2 janvier 2020");
  });
});

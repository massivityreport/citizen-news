import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { card } from "../test/topics";
import { Gauge } from "./Gauge";
import { Preview } from "./Preview";
import { TopicCardView } from "./TopicCardView";

describe("Gauge", () => {
  it("expose n/10 sujets en texte et en progressbar", () => {
    render(<Gauge count={4} />);
    expect(screen.getByText("4/10 sujets")).toBeInTheDocument();
    const bar = screen.getByRole("progressbar", { name: "4/10 sujets" });
    expect(bar).toHaveAttribute("aria-valuenow", "4");
    expect(bar).toHaveAttribute("aria-valuemax", "10");
    expect(bar).toHaveAttribute("aria-valuetext", "4 sujets sur 10");
  });
});

describe("Preview", () => {
  it("montre dix places : titre ou « Place libre »", () => {
    render(<Preview titles={["Budget", "Santé"]} />);
    const places = screen.getAllByRole("listitem");
    expect(places).toHaveLength(10);
    expect(places[0]).toHaveTextContent("Budget");
    expect(places[2]).toHaveTextContent("Place libre");
    expect(screen.getAllByText("Place libre")).toHaveLength(8);
  });
});

describe("TopicCardView", () => {
  const show = (inUne: boolean, over = {}) =>
    render(
      <MemoryRouter>
        <TopicCardView topic={card(7, { image_url: "https://img.example.org/a.jpg", ...over })} inUne={inUne} position={3} total={42} />
      </MemoryRouter>,
    );

  it("affiche titre, résumé, nombres, heure, position, image et sources en lien", () => {
    show(false);
    expect(screen.getByRole("heading", { level: 3, name: "Sujet 7" })).toBeInTheDocument();
    expect(screen.getByText("Résumé du sujet 7.")).toBeInTheDocument();
    expect(screen.getByText(/9 articles · 5 médias/)).toBeInTheDocument();
    expect(screen.getByText(/Mis à jour/)).toBeInTheDocument();
    expect(screen.getByTestId("position")).toHaveTextContent("3/42");
    expect(screen.getByRole("img", { name: "Illustration : Sujet 7" })).toHaveAttribute("src", "https://img.example.org/a.jpg");
    expect(screen.getByRole("link", { name: /Le Monde/ })).toHaveAttribute("href", "https://example.org/7");
    expect(screen.queryByText("Dans ma une")).not.toBeInTheDocument();
  });

  it("n'accepte pas une image http", () => {
    show(false, { image_url: "http://img.example.org/a.jpg" });
    expect(screen.queryByRole("img")).not.toBeInTheDocument();
  });

  it("un sujet dans la une est marqué par un texte et un attribut de style, pas par la couleur seule", () => {
    const { container } = show(true);
    expect(screen.getByText("Dans ma une")).toBeInTheDocument();
    expect(container.querySelector("[data-in-une='true']")).not.toBeNull();
  });

  it("ne montre aucun compteur d'approbation ni de popularité", () => {
    const { container } = show(true, { approvals: 80, support: "high", proportion: 0.4 } as never);
    const text = container.textContent ?? "";
    expect(text).not.toMatch(/approbation|populaire|popularité|soutien|vote|80|40 %/i);
  });

  it("tolère une source sans date (published_at null)", () => {
    const { container } = show(false, {
      sources: [{ name: "Le Monde", url: "https://example.org/7", title: "Article 7", published_at: null }],
    });
    expect(screen.getByText("Le Monde", { exact: false })).toBeInTheDocument();
    expect(container.textContent ?? "").not.toMatch(/Invalid Date|NaN|null/);
  });
});

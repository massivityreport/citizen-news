import { describe, expect, it, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";
import { LineChart, niceStep } from "./LineChart";

// jsdom ne calcule pas le nom accessible d’un <svg role="img"> : on vérifie le câblage (aria-labelledby → title, desc).
function chart(name: string): SVGSVGElement {
  const svg = screen.getAllByRole("img", { hidden: true }).find((el) => el.tagName.toLowerCase() === "svg" && el.querySelector("title")?.textContent === name);
  if (!svg) throw new Error(`Graphique introuvable : ${name}`);
  const ids = svg.getAttribute("aria-labelledby")!.split(" ");
  expect(ids).toEqual([svg.querySelector("title")!.id, svg.querySelector("desc")!.id]);
  return svg as unknown as SVGSVGElement;
}
const descOf = (svg: Element) => svg.querySelector("desc")!.textContent ?? "";

const pts = (...v: number[]) => v.map((value, i) => ({ date: `2026-11-0${i + 1}`, value }));

describe("LineChart", () => {
  it("série vide : message et description pour lecteurs d’écran, pas de légende", () => {
    render(<LineChart title="Votes" series={[{ id: "a", label: "A", points: [] }]} emptyText="Aucun vote." />);
    const svg = chart("Votes");
    expect(descOf(svg)).toBe("Aucun vote.");
    expect(within(svg as unknown as HTMLElement).getByText("Aucun vote.", { selector: "text" })).toBeInTheDocument();
    expect(svg.querySelector("polyline")).toBeNull();
  });

  it("aucune série : même rendu vide", () => {
    render(<LineChart title="Rien" series={[]} />);
    expect(descOf(chart("Rien"))).toBe("Aucune donnée à afficher.");
  });

  it("un seul point : un marqueur, pas de ligne, une graduation de date", () => {
    render(<LineChart title="Un point" series={[{ id: "a", label: "A", points: [{ date: "2026-11-03", value: 4 }] }]} />);
    const svg = chart("Un point");
    expect(svg.querySelector("polyline")).toBeNull();
    expect(svg.querySelectorAll("circle")).toHaveLength(1);
    expect(within(svg as unknown as HTMLElement).getByText("3 nov.")).toBeInTheDocument();
    expect(descOf(svg)).toMatch(/A : 1 point, total 4, maximum 4/);
  });

  it("plusieurs séries : une ligne par série, formes différentes, légende avec les libellés", () => {
    render(
      <LineChart
        title="Trois séries"
        yLabel="Votes par jour"
        series={[
          { id: "a", label: "Alpha", points: pts(1, 5, 2) },
          { id: "b", label: "Beta", points: pts(0, 1, 0) },
          { id: "c", label: "Gamma", points: pts(3, 3, 3) },
        ]}
      />,
    );
    const svg = chart("Trois séries");
    expect(svg.querySelectorAll("polyline")).toHaveLength(3);
    expect(svg.querySelectorAll("circle, rect, polygon")).toHaveLength(9 + 0 * 1); // 3 formes × 3 points (la légende est hors du <svg role=img>)
    expect(svg.querySelector("[data-series=b] rect")).not.toBeNull();
    expect(svg.querySelector("[data-series=c] polygon")).not.toBeNull();
    const legend = screen.getByRole("list", { name: "Légende" });
    expect(within(legend).getAllByRole("listitem").map((li) => li.textContent)).toEqual(["Alpha", "Beta", "Gamma"]);
    // axes : graduations de dates (1er et dernier jour) et valeurs entières (pas de 2, jusqu’à 6)
    expect(within(svg as unknown as HTMLElement).getByText("1 nov.")).toBeInTheDocument();
    expect(within(svg as unknown as HTMLElement).getByText("3 nov.")).toBeInTheDocument();
    expect(within(svg as unknown as HTMLElement).getByText("6")).toBeInTheDocument();
    expect(within(svg as unknown as HTMLElement).getByText("Votes par jour")).toBeInTheDocument();
    expect(descOf(svg)).toMatch(/Alpha : 3 points, total 8, maximum 5.*Du 1 novembre 2026 au 3 novembre 2026/);
  });

  it("30 jours : au plus 6 dates sur l’axe", () => {
    const points = Array.from({ length: 30 }, (_, i) => ({ date: `2026-11-${String(i + 1).padStart(2, "0")}`, value: i % 3 }));
    render(<LineChart title="Mois" series={[{ id: "a", label: "A", points }]} />);
    const svg = chart("Mois");
    const dates = Array.from(svg.querySelectorAll("text")).filter((t) => /nov\.$/.test(t.textContent ?? ""));
    expect(dates.length).toBeLessThanOrEqual(6);
    expect(dates[0].textContent).toBe("1 nov.");
    expect(dates[dates.length - 1].textContent).toBe("30 nov.");
  });

  it("ignore les points invalides", () => {
    render(<LineChart title="Bruit" series={[{ id: "a", label: "A", points: [{ date: "n’importe quoi", value: 1 }, { date: "2026-11-01", value: NaN }] }]} />);
    expect(descOf(chart("Bruit"))).toBe("Aucune donnée à afficher.");
  });

  it("niceStep : pas ronds", () => {
    expect([niceStep(1), niceStep(4), niceStep(9), niceStep(23), niceStep(1000)]).toEqual([1, 1, 5, 10, 500]);
  });
});

describe("LineChart : lisibilité avec plusieurs séries et beaucoup de points", () => {
  const days = (n: number) => Array.from({ length: n }, (_, i) => new Date(Date.UTC(2026, 10, 1 + i)).toISOString().slice(0, 10));
  const three = (n: number) => [
    { id: "a", label: "A", points: days(n).map((date, i) => ({ date, value: i % 7 })) },
    { id: "b", label: "B", points: days(n).map((date, i) => ({ date, value: (i * 2) % 5 })) },
    { id: "c", label: "C", points: days(n).map((date, i) => ({ date, value: i % 3 })) },
  ];

  it("30 jours × 3 séries : 90 marqueurs, trois traits (continu, tirets, pointillés) et trois formes", () => {
    render(<LineChart title="Trois mois" series={three(30)} />);
    const svg = chart("Trois mois");
    expect(svg.querySelectorAll("circle, rect, polygon")).toHaveLength(90);
    const dashes = ["a", "b", "c"].map((id) => svg.querySelector(`[data-series=${id}] polyline`)!.getAttribute("stroke-dasharray"));
    expect(new Set(dashes).size).toBe(3);
    expect(svg.querySelectorAll("[data-series=a] circle")).toHaveLength(30);
    expect(svg.querySelectorAll("[data-series=b] rect")).toHaveLength(30);
    expect(svg.querySelectorAll("[data-series=c] polygon")).toHaveLength(30);
  });

  it("plus de 31 points : quelques marqueurs par série restent, avec leur forme", () => {
    render(<LineChart title="Long" series={three(90)} />);
    const svg = chart("Long");
    for (const [id, tag] of [["a", "circle"], ["b", "rect"], ["c", "polygon"]]) {
      const n = svg.querySelectorAll(`[data-series=${id}] ${tag}`).length;
      expect(n).toBeGreaterThanOrEqual(8);
      expect(n).toBeLessThanOrEqual(12);
    }
  });

  it("deux points à la même date : pas d’avertissement de clé dupliquée", () => {
    const errors: unknown[][] = [];
    const spy = vi.spyOn(console, "error").mockImplementation((...a) => void errors.push(a));
    render(<LineChart title="Doublons" series={[{ id: "a", label: "A", points: [{ date: "2026-11-01", value: 1 }, { date: "2026-11-01", value: 2 }] }]} />);
    spy.mockRestore();
    expect(errors).toEqual([]);
    expect(chart("Doublons").querySelectorAll("circle")).toHaveLength(2);
  });

  it("étiquettes des bords alignées vers l’intérieur (start / end), celles du milieu centrées", () => {
    render(<LineChart title="Bords" series={three(10)} />);
    const labels = Array.from(chart("Bords").querySelectorAll("text")).filter((t) => /nov\.$/.test(t.textContent ?? ""));
    const anchors = labels.map((t) => t.getAttribute("text-anchor"));
    expect(anchors[0]).toBe("start");
    expect(anchors[anchors.length - 1]).toBe("end");
    expect(anchors.slice(1, -1).every((a) => a === "middle")).toBe(true);
  });
});

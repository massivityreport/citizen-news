import { describe, expect, it } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { TopicImage } from "./TopicImage";

const URL = "https://img.example.org/a.jpg";

function Card({ url }: { url: string | null }) {
  return (
    <article>
      <TopicImage url={url} title="Pénurie de médecins" />
      <h2>Pénurie de médecins</h2>
      <p>Résumé</p>
    </article>
  );
}

describe("TopicImage", () => {
  it("rend l'image avec les bons attributs", () => {
    render(<Card url={URL} />);
    const img = screen.getByRole("img", { name: "Illustration : Pénurie de médecins" });
    expect(img).toHaveAttribute("src", URL);
    expect(img).toHaveAttribute("loading", "lazy");
    expect(img).toHaveAttribute("decoding", "async");
    expect(img).toHaveAttribute("referrerpolicy", "no-referrer");
    expect(img).not.toHaveAttribute("crossorigin");
  });

  it.each(["http://img.example.org/a.jpg", "data:image/png;base64,AAAA", "javascript:alert(1)"])(
    "ne rend rien pour %s (repli sans image)",
    (url) => {
      render(<Card url={url} />);
      expect(screen.queryByRole("img")).toBeNull();
      expect(screen.getByRole("heading", { name: "Pénurie de médecins" })).toBeInTheDocument();
    },
  );

  it("ne rend rien sans image_url", () => {
    const { container } = render(<TopicImage url={null} title="x" />);
    expect(container).toBeEmptyDOMElement();
  });

  it("retire l'image en erreur et garde le reste de la carte", () => {
    render(<Card url={URL} />);
    fireEvent.error(screen.getByRole("img"));
    expect(screen.queryByRole("img")).toBeNull();
    expect(screen.getByRole("heading", { name: "Pénurie de médecins" })).toBeInTheDocument();
    expect(screen.getByText("Résumé")).toBeInTheDocument();
  });
});

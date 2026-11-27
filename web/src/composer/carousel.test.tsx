import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { card } from "../test/topics";
import { ActionBar, Carousel, type CarouselActions } from "./Carousel";

const actions = (): CarouselActions => ({ onPrev: vi.fn(), onNext: vi.fn(), onAdd: vi.fn(), onRemove: vi.fn() });

function setup(inUne = false, disabled = false) {
  const a = actions();
  const view = render(
    <MemoryRouter>
      <Carousel topic={card(1)} inUne={inUne} position={1} total={3} actions={a} disabled={disabled} />
    </MemoryRouter>,
  );
  return { a, surface: screen.getByRole("group", { name: /Sujets à explorer/ }), ...view };
}

/** Glissement simulé par événements pointeur. */
function swipe(el: HTMLElement, dx: number, dy: number, steps = 4) {
  fireEvent.pointerDown(el, { pointerId: 1, clientX: 200, clientY: 300, button: 0, isPrimary: true, pointerType: "touch" });
  for (let i = 1; i <= steps; i++)
    fireEvent.pointerMove(el, { pointerId: 1, clientX: 200 + (dx * i) / steps, clientY: 300 + (dy * i) / steps, pointerType: "touch" });
  fireEvent.pointerUp(el, { pointerId: 1, clientX: 200 + dx, clientY: 300 + dy, pointerType: "touch" });
}

describe("Carousel : gestes", () => {
  it("gauche = suivant, droite = précédent, haut = ajouter, bas = retirer", () => {
    const { a, surface } = setup();
    swipe(surface, -120, 5);
    expect(a.onNext).toHaveBeenCalledTimes(1);
    swipe(surface, 120, -5);
    expect(a.onPrev).toHaveBeenCalledTimes(1);
    swipe(surface, 4, -120);
    expect(a.onAdd).toHaveBeenCalledTimes(1);
    swipe(surface, -4, 120);
    expect(a.onRemove).toHaveBeenCalledTimes(1);
  });

  it("ignore un glissement trop court, un simple toucher et une diagonale", () => {
    const { a, surface } = setup();
    swipe(surface, -30, 0);
    swipe(surface, 0, 0, 1);
    swipe(surface, -90, -90);
    swipe(surface, -100, 80); // l'axe vertical n'est pas assez net
    expect(a.onNext).not.toHaveBeenCalled();
    expect(a.onAdd).not.toHaveBeenCalled();
    expect(a.onRemove).not.toHaveBeenCalled();
  });

  it("un défilement repris par le navigateur (pointercancel) n'agit pas", () => {
    const { a, surface } = setup();
    fireEvent.pointerDown(surface, { pointerId: 1, clientX: 200, clientY: 300, isPrimary: true, pointerType: "touch" });
    fireEvent.pointerMove(surface, { pointerId: 1, clientX: 200, clientY: 200, pointerType: "touch" });
    fireEvent.pointerCancel(surface, { pointerId: 1 });
    fireEvent.pointerUp(surface, { pointerId: 1, clientX: 200, clientY: 100, pointerType: "touch" });
    expect(a.onAdd).not.toHaveBeenCalled();
  });

  it("donne un retour visuel pendant le geste, puis le retire", () => {
    const { surface } = setup();
    fireEvent.pointerDown(surface, { pointerId: 1, clientX: 200, clientY: 300, isPrimary: true, pointerType: "touch" });
    fireEvent.pointerMove(surface, { pointerId: 1, clientX: 200, clientY: 230, pointerType: "touch" });
    expect(surface).toHaveAttribute("data-gesture", "up");
    expect(surface).toHaveAttribute("data-armed", "true");
    expect(screen.getByText(/Ajouter à ma une/, { selector: "p" })).toBeInTheDocument();
    fireEvent.pointerUp(surface, { pointerId: 1, clientX: 200, clientY: 230, pointerType: "touch" });
    expect(surface).not.toHaveAttribute("data-gesture");
  });

  it("lecture seule : haut et bas n'agissent plus, gauche et droite oui", () => {
    const { a, surface } = setup(false, true);
    swipe(surface, 0, -120);
    swipe(surface, 0, 120);
    expect(a.onAdd).not.toHaveBeenCalled();
    expect(a.onRemove).not.toHaveBeenCalled();
    swipe(surface, -120, 0);
    expect(a.onNext).toHaveBeenCalled();
  });

  it("mouvement réduit : la carte ne suit pas le doigt, le retour reste visible", () => {
    vi.stubGlobal("matchMedia", (q: string) => ({ matches: q.includes("reduce"), media: q, addEventListener() {}, removeEventListener() {} }));
    const { surface } = setup();
    fireEvent.pointerDown(surface, { pointerId: 1, clientX: 200, clientY: 300, isPrimary: true, pointerType: "touch" });
    fireEvent.pointerMove(surface, { pointerId: 1, clientX: 100, clientY: 300, pointerType: "touch" });
    expect(surface.firstElementChild).not.toHaveAttribute("style");
    expect(screen.getByText(/Suivant ›/, { selector: "p" })).toBeInTheDocument();
    vi.unstubAllGlobals();
  });

  it("flèches aussi quand le focus est sur un lien de la carte, mais pas dans un champ", async () => {
    const user = userEvent.setup();
    const { a } = setup();
    screen.getByRole("link", { name: /Le Monde/ }).focus();
    await user.keyboard("{ArrowRight}");
    expect(a.onNext).toHaveBeenCalledTimes(1);
    const input = document.createElement("input");
    screen.getByRole("group", { name: /Sujets à explorer/ }).appendChild(input);
    input.focus();
    await user.keyboard("{ArrowRight}");
    expect(a.onNext).toHaveBeenCalledTimes(1);
  });

  it("équivalents clavier : flèches", async () => {
    const user = userEvent.setup();
    const { a, surface } = setup();
    surface.focus();
    await user.keyboard("{ArrowRight}{ArrowLeft}{ArrowUp}{ArrowDown}");
    expect(a.onNext).toHaveBeenCalledTimes(1);
    expect(a.onPrev).toHaveBeenCalledTimes(1);
    expect(a.onAdd).toHaveBeenCalledTimes(1);
    expect(a.onRemove).toHaveBeenCalledTimes(1);
  });
});

describe("ActionBar", () => {
  const bar = (over: Partial<Parameters<typeof ActionBar>[0]> = {}) => {
    const a = actions();
    render(<ActionBar actions={a} canPrev canNext inUne={false} readOnly={false} addLabel="Ajouter à ma une" {...over} />);
    return a;
  };

  it("Précédent, Suivant et Ajouter appellent les actions", async () => {
    const a = bar();
    await userEvent.click(screen.getByRole("button", { name: /Précédent/ }));
    await userEvent.click(screen.getByRole("button", { name: /Suivant/ }));
    await userEvent.click(screen.getByRole("button", { name: "Ajouter à ma une" }));
    expect(a.onPrev).toHaveBeenCalled();
    expect(a.onNext).toHaveBeenCalled();
    expect(a.onAdd).toHaveBeenCalled();
  });

  it("dans la une : Retirer remplace Ajouter ; lecture seule les désactive", async () => {
    const a = bar({ inUne: true });
    await userEvent.click(screen.getByRole("button", { name: "Retirer de ma une" }));
    expect(a.onRemove).toHaveBeenCalled();
    expect(screen.queryByRole("button", { name: "Ajouter à ma une" })).not.toBeInTheDocument();
  });

  it("lecture seule : ajouter/retirer désactivés, navigation active", () => {
    bar({ readOnly: true });
    expect(screen.getByRole("button", { name: "Ajouter à ma une" })).toBeDisabled();
    expect(screen.getByRole("button", { name: /Suivant/ })).toBeEnabled();
  });
});

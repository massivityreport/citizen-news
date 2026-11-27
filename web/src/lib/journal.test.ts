import { beforeEach, describe, expect, it, vi } from "vitest";
import { journal, MAX_ACTIONS } from "./journal";

beforeEach(() => journal.reset());

describe("journal du parcours", () => {
  it("garde chaque action avec son heure", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-11-27T10:00:00.000Z"));
    journal.record({ type: "page", page: "/archives" });
    journal.record({ type: "topic_added", topic_id: 4 });
    journal.record({ type: "login" });
    vi.useRealTimers();
    expect(journal.get()).toEqual([
      { type: "page", page: "/archives", at: "2026-11-27T10:00:00.000Z" },
      { type: "topic_added", topic_id: 4, at: "2026-11-27T10:00:00.000Z" },
      { type: "login", at: "2026-11-27T10:00:00.000Z" },
    ]);
  });

  it("ne garde que les 20 dernières actions", () => {
    for (let i = 0; i < 25; i++) journal.record({ type: "page", page: `/p${i}` });
    const list = journal.get();
    expect(MAX_ACTIONS).toBe(20);
    expect(list).toHaveLength(20);
    expect(list[0]).toMatchObject({ page: "/p5" });
    expect(list[19]).toMatchObject({ page: "/p24" });
  });

  it("dure la visite : sessionStorage, jamais localStorage, et se relit après rechargement", () => {
    journal.record({ type: "login" });
    expect(window.localStorage.length).toBe(0);
    expect(JSON.parse(window.sessionStorage.getItem("cn.journey")!)).toHaveLength(1);
    journal.reload();
    expect(journal.get()).toHaveLength(1);
  });

  it("ignore un stockage corrompu et fonctionne sans stockage", () => {
    window.sessionStorage.setItem("cn.journey", "{pas du json");
    journal.reload();
    expect(journal.get()).toEqual([]);
    window.sessionStorage.setItem("cn.journey", JSON.stringify([{ type: "x" }, { type: "login", at: "2026-11-27T10:00:00.000Z" }]));
    journal.reload();
    expect(journal.get()).toHaveLength(1);
    const spy = vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("plein");
    });
    journal.record({ type: "login" });
    spy.mockRestore();
    expect(journal.get()).toHaveLength(2);
  });

  it("n'émet aucune requête réseau", () => {
    const f = vi.fn();
    vi.stubGlobal("fetch", f);
    journal.record({ type: "page", page: "/" });
    journal.get();
    expect(f).not.toHaveBeenCalled();
    vi.unstubAllGlobals();
  });
});

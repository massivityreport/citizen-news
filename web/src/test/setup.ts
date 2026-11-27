import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach, beforeEach } from "vitest";
import { resetBrowse } from "../lib/browse";
import { draftStore } from "../lib/draftStore";
import { journal } from "../lib/journal";

// Chaque test repart d'un navigateur neuf : stockages vides, graine et brouillon oubliés.
beforeEach(() => {
  window.localStorage.clear();
  window.sessionStorage.clear();
  resetBrowse();
  draftStore.reload();
  journal.reload();
});

afterEach(() => cleanup());

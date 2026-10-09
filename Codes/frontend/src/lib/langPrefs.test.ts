import { describe, expect, it } from "vitest";
import { act } from "@testing-library/react";
import { LANGS } from "@/api/types";
import { LANG_LABELS } from "@/i18n";
import { loadPrefs, useApp } from "@/store/app";
import { isEnglish, normalizeLang } from "./langPrefs";

describe("languages", () => {
  it("offers exactly the six Nemotron Nano languages with native selector labels", () => {
    expect(LANGS).toEqual(["en-US", "es-ES", "fr-FR", "de-DE", "it-IT", "ja-JP"]);
    expect(LANGS.map((l) => LANG_LABELS[l].native)).toEqual(["English", "Español", "Français", "Deutsch", "Italiano", "日本語"]);
  });
  it("falls back to English for a stored or unknown code outside the six", () => {
    expect(normalizeLang("fr-FR")).toBe("fr-FR");
    for (const bad of ["pt-BR", "xx", "", 42, null, undefined]) expect(normalizeLang(bad)).toBe("en-US");
  });
  it("keeps every other stored preference when the stored language is unsupported", () => {
    const p = loadPrefs({ lang: "pt-BR", ladder: "4", patientId: "p1", theme: "dark" });
    expect(p).toMatchObject({ lang: "en-US", ladder: "4", patientId: "p1", theme: "dark", fish: true });
    expect(loadPrefs({ lang: "de-DE", fish: false })).toMatchObject({ lang: "de-DE", fish: false });
  });
  it("changing language does not change the persona, ladder, meal or scenario", () => {
    const dinner = { meal: { carbs: 60 }, source: "usual" as const, title: "Dinner" };
    act(() => {
      useApp.getState().setPatient("persona-a");
      useApp.getState().setLadder("1");
      useApp.getState().setStageDinner(dinner);
    });
    const before = useApp.getState();
    act(() => useApp.getState().setLang("ja-JP"));
    const after = useApp.getState();
    expect(after.lang).toBe("ja-JP");
    expect({ p: after.patientId, l: after.ladder, d: after.stageDinner, c: after.stageChange, h: after.highlight }).toEqual({
      p: before.patientId,
      l: before.ladder,
      d: before.stageDinner,
      c: before.stageChange,
      h: before.highlight,
    });
  });
  it("isEnglish", () => {
    expect(isEnglish("en-US")).toBe(true);
    expect(isEnglish("es-ES")).toBe(false);
  });
});

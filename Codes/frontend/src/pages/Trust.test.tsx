import { describe, expect, it, vi } from "vitest";
import { render, within } from "@testing-library/react";
import i18n from "i18next";
import { I18nextProvider, initReactI18next } from "react-i18next";
import { LazyMotion, domAnimation } from "framer-motion";
import { allLocales } from "@/i18n/testLocales";

// A small held-out report in the agent_multilingual shape; every other report is absent.
const REPORT = {
  generated_at: "2026-10-08T14:10:28+00:00",
  split: "heldout",
  mode: "live",
  repeats: 1,
  languages: ["en-US", "es-ES", "fr-FR", "de-DE", "it-IT", "ja-JP"],
  models: { chat: "nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B", provider: "nebius_tokenfactory", guardrails: true },
  n_runs: 174,
  n_cases: 29,
  metrics: {
    pass: { n: 174, k: 108, rate: 0.621 },
    numbers_ok: { n: 174, k: 174, rate: 1 },
    inappropriate_refusal: { n: 84, k: 0, rate: 0 },
    justified_refusal: { n: 36, k: 30, rate: 0.833 },
    unnecessary_clarification: { n: 48, k: 0, rate: 0 },
    clarification_when_required: { n: 18, k: 14, rate: 0.778 },
    engine_result_invariance_across_languages: { n: 15, k: 6, rate: 0.4 },
  },
  per_language: Object.fromEntries(
    ["en-US", "es-ES", "fr-FR", "de-DE", "it-IT", "ja-JP"].map((l, i) => [l, { pass: { n: 29, k: 19 - i, rate: (19 - i) / 29 }, locale_ok: { n: 29, k: 29, rate: 1 } }]),
  ),
  per_category: { normal: { n: 18, k: 7, rate: 0.389 }, medication: { n: 18, k: 18, rate: 1 }, unsupported_causality: { n: 18, k: 6, rate: 0.333 } },
  latency_ms: { p50: 3272, p95: 7625 },
  cost_usd: null,
  scoring: "deterministic checks only (no LLM judge, no human review in this report)",
  limitations: ["Synthetic persona and replay clock; not real patients."],
};

vi.mock("@/api/hooks", () => ({
  useReportsList: () => ({ data: [{ name: "agent_multilingual", title: "Multilingual Nemotron agent suite", generated_at: REPORT.generated_at }], isLoading: false, isError: false }),
  useReport: (name: string, enabled = true) => ({ data: name === "agent_multilingual" && enabled ? REPORT : undefined, isLoading: false }),
}));

const { default: TrustPage } = await import("./Trust");

async function renderIn(lang: string) {
  const inst = i18n.createInstance();
  await inst.use(initReactI18next).init({ lng: lang, fallbackLng: false, resources: { [lang]: { translation: allLocales()[lang] } }, interpolation: { escapeValue: false } });
  return render(
    <I18nextProvider i18n={inst}>
      <LazyMotion features={domAnimation}>
        <TrustPage />
      </LazyMotion>
    </I18nextProvider>,
  );
}

describe("Trust page: multilingual agent evaluation", () => {
  it("shows every headline check with its denominator, the weak ones included", async () => {
    const { container } = await renderIn("en-US");
    const card = container.querySelector("#agent-multilingual") as HTMLElement;
    expect(card).toBeTruthy();
    const text = card.textContent ?? "";
    expect(text).toContain("Multilingual agent evaluation (held-out, live)");
    expect(text).toContain("108 / 174 runs");
    expect(text).toContain("66 of 174 runs failed at least one check");
    for (const kn of ["174 / 174", "0 / 84", "30 / 36", "0 / 48", "14 / 18", "6 / 15"]) expect(text).toContain(kn);
    expect(text).toContain("Same engine result across languages");
    expect(text).toContain("NeMo Guardrails on");
    expect(text).toContain("nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B");
    expect(text).toContain("no LLM judge, no human review");
    expect(text).toContain("Synthetic persona and replay clock");
    expect(text).not.toContain("Not a live evaluation");
  });

  it("per-language and per-category rates are real tables, weakest category first", async () => {
    const { container } = await renderIn("en-US");
    const card = container.querySelector("#agent-multilingual") as HTMLElement;
    const tables = within(card).getAllByRole("table");
    const byLang = tables.find((t) => t.querySelector("caption")?.textContent === "Pass rate by language")!;
    expect(byLang).toBeTruthy();
    const rows = within(byLang).getAllByRole("rowheader").map((r) => r.textContent);
    expect(rows).toEqual(["English", "Español", "Français", "Deutsch", "Italiano", "日本語"]);
    const byCat = tables.find((t) => /question type/.test(t.querySelector("caption")?.textContent ?? ""))!;
    expect(within(byCat).getAllByRole("rowheader")[0].textContent).toBe("Unsupported cause-and-effect claims");
  });

  it("renders in every UI language without missing keys", async () => {
    for (const lang of Object.keys(allLocales())) {
      const { container, unmount } = await renderIn(lang);
      const text = container.querySelector("#agent-multilingual")?.textContent ?? "";
      expect(text, lang).not.toMatch(/trust\.ml\./);
      expect(text, lang).toContain("108 / 174");
      unmount();
    }
  });
});

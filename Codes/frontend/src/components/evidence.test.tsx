import { describe, expect, it } from "vitest";
import { render } from "@testing-library/react";
import i18n from "i18next";
import { I18nextProvider, initReactI18next } from "react-i18next";
import { LazyMotion, domAnimation } from "framer-motion";
import { EN, getKey } from "@/i18n/testLocales";
import { EvidenceChip } from "./evidence";

const inst = i18n.createInstance();
await inst.use(initReactI18next).init({ lng: "en-US", resources: { "en-US": { translation: EN } }, interpolation: { escapeValue: false } });

describe("evidence badges use precise wording with accessible explanations", () => {
  it("the 'validated' status reads 'Retrospectively evaluated', never a bare 'Validated'", () => {
    expect(getKey(EN, "evidence.status.validated")).toBe("Retrospectively evaluated");
    const { container } = render(
      <I18nextProvider i18n={inst}>
        <LazyMotion features={domAnimation}>
          <EvidenceChip status="validated" />
        </LazyMotion>
      </I18nextProvider>,
    );
    const btn = container.querySelector("button")!;
    expect(btn.textContent).toContain("Retrospectively evaluated");
    expect(btn.textContent).not.toMatch(/^\s*Validated\s*$/);
    const desc = btn.getAttribute("aria-describedby");
    expect(desc).toBeTruthy();
    expect(container.ownerDocument.getElementById(desc!)?.textContent).toMatch(/held-out|not clinically validated/);
    expect(btn.getAttribute("title")).toMatch(/Retrospectively evaluated/);
  });
  it("no English badge label is just 'Validated'", () => {
    const labels = ["evidence.status.validated", "body.panel.validated2h", "body.organs.validated"].map((k) => getKey(EN, k)).filter((v): v is string => typeof v === "string");
    for (const l of labels) expect(l).not.toMatch(/^Validated\b/);
  });
});

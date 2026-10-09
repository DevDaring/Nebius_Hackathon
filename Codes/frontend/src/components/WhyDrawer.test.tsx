import { describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import i18n from "i18next";
import { I18nextProvider, initReactI18next } from "react-i18next";
import { LazyMotion, domAnimation } from "framer-motion";
import { EN, getKey } from "@/i18n/testLocales";

vi.mock("@/api", async () => {
  const { ApiError } = await import("@/api/http");
  const gone = () => Promise.reject(new ApiError(404, "Forecast not found for this patient; request a new forecast"));
  return {
    api: {
      patients: vi.fn(async () => [{ id: "biman", name: "Biman Bakshi" }]),
      explain: vi.fn((_pid: string, id: string) =>
        id === "old"
          ? gone()
          : Promise.resolve({ physiology: [{ name: "earlier_meals", label_en: "Earlier food still digesting", contribution: 14.5, source: "physiology" }], learned: [], text_en: "" }),
      ),
      receipt: vi.fn((_pid: string, id: string) => (id === "old" ? gone() : new Promise(() => undefined))),
    },
    realClient: {},
    loadMockClient: vi.fn(),
  };
});

import { api } from "@/api";
import { useApp } from "@/store/app";
import { WhyDrawer } from "./WhyDrawer";

const inst = i18n.createInstance();
await inst.use(initReactI18next).init({ lng: "en-US", resources: { "en-US": { translation: EN } }, interpolation: { escapeValue: false } });

describe("Why drawer after the server forgot a forecast (restart or eviction)", () => {
  it("asks the page for a fresh forecast id and shows the explanation instead of an error", async () => {
    const refresh = vi.fn(async () => "new");
    useApp.setState({ patientId: "biman", whyOpen: { forecastId: "old", refresh } });
    render(
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <I18nextProvider i18n={inst}>
          <LazyMotion features={domAnimation}>
            <WhyDrawer />
          </LazyMotion>
        </I18nextProvider>
      </QueryClientProvider>,
    );
    await waitFor(() => expect(refresh).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(api.explain).toHaveBeenCalledWith("biman", "new"));
    await screen.findByText(getKey(EN, "why.physiology") as string);
    expect(screen.queryByText(getKey(EN, "receipt.notFound") as string)).toBeNull();
    expect(useApp.getState().whyOpen?.forecastId).toBe("new");
  });
});

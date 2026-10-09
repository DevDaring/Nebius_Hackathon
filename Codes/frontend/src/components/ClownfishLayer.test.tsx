import { afterEach, describe, expect, it } from "vitest";
import { act, cleanup, render } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useApp } from "@/store/app";
import { ClownfishLayer } from "./ClownfishLayer";

function setup(props: { suppressed?: boolean } = {}) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ClownfishLayer {...props} />
    </QueryClientProvider>,
  );
}
const band = (c: HTMLElement) => c.querySelector("[data-fish-band]") as HTMLElement;

afterEach(() => {
  cleanup();
  act(() => useApp.setState({ safetyAlert: null, fish: true, presentation: false }));
});

describe("decorative clownfish layer", () => {
  it("is decorative only: aria-hidden, empty band, no fish until a pass", () => {
    const { container } = setup();
    const b = band(container);
    expect(b.getAttribute("aria-hidden")).toBe("true");
    expect(b.className).toContain("no-print");
    expect(b.querySelectorAll(".fish").length).toBe(0);
    expect(b.textContent).toBe("");
  });
  it("switches off during a safety alert, with the setting off, in presentation and in report views", () => {
    const { container, unmount } = setup();
    const on = band(container).dataset.fishBand;
    act(() => useApp.setState({ safetyAlert: { level: "very_low", emergency: true, title: "x", message: "y", actions: [] } }));
    expect(band(container).dataset.fishBand).toBe("off");
    act(() => useApp.setState({ safetyAlert: null, fish: false }));
    expect(band(container).dataset.fishBand).toBe("off");
    act(() => useApp.setState({ fish: true, presentation: true }));
    expect(band(container).dataset.fishBand).toBe("off");
    act(() => useApp.setState({ presentation: false }));
    expect(band(container).dataset.fishBand).toBe(on);
    unmount();
    const r = setup({ suppressed: true });
    expect(band(r.container).dataset.fishBand).toBe("off");
  });
});

import { describe, expect, it } from "vitest";
import { hasWebGL, stageRenderer, textTableByDefault } from "./stageRender";

const base = { pref: "body" as const, webgl: true, glFailed: false, simple: false, bodyFailed: false };

describe("3-D capability fallback", () => {
  it("uses the 3-D body only when WebGL works", () => {
    expect(stageRenderer(base)).toBe("body3d");
    expect(stageRenderer({ ...base, webgl: false })).toBe("body2d");
    expect(stageRenderer({ ...base, glFailed: true })).toBe("body2d");
    expect(stageRenderer({ ...base, simple: true })).toBe("body2d");
  });
  it("falls back to the chart when the body view cannot load, and respects the chart choice", () => {
    expect(stageRenderer({ ...base, bodyFailed: true })).toBe("chart");
    expect(stageRenderer({ ...base, webgl: false, bodyFailed: true })).toBe("chart");
    expect(stageRenderer({ ...base, pref: "chart" })).toBe("chart");
  });
  it("opens the readable table by default when 3-D is missing", () => {
    expect(textTableByDefault({ webgl: false, glFailed: false })).toBe(true);
    expect(textTableByDefault({ webgl: true, glFailed: true })).toBe(true);
    expect(textTableByDefault({ webgl: true, glFailed: false })).toBe(false);
  });
  it("treats a missing or throwing canvas as no WebGL", () => {
    expect(hasWebGL(undefined)).toBe(false);
    // jsdom has no WebGL: getContext returns null (or throws "not implemented").
    expect(hasWebGL(document)).toBe(false);
    const throwing = { createElement: () => ({ getContext: () => { throw new Error("blocked"); } }) } as unknown as Document;
    expect(hasWebGL(throwing)).toBe(false);
  });
});

import { describe, expect, it } from "vitest";
import { replySource } from "./replySource";

describe("replySource", () => {
  it("reads the contract shape (source + source_detail)", () => {
    expect(replySource({ source: "live", source_detail: "openrouter:openai/gpt-5.4-mini" })).toEqual({ kind: "live", model: "gpt-5.4-mini", detail: "openrouter:openai/gpt-5.4-mini" });
    expect(replySource({ source: "fixture", source_detail: "template" }).kind).toBe("template");
    expect(replySource({ source: "live", source_detail: "template fallback after openrouter" }).kind).toBe("template");
    expect(replySource({ source: "fixture", source_detail: "rules" }).kind).toBe("rules");
    expect(replySource({ source: "live", source_detail: "router" })).toMatchObject({ kind: "live", model: null });
    expect(replySource({ source: "fixture" }).kind).toBe("fixture");
  });
  it("accepts every source shape and unknown values", () => {
    expect(replySource({ source: "template" }).kind).toBe("template");
    expect(replySource({ source: "rules" }).kind).toBe("rules");
    expect(replySource({ source: "something" }).kind).toBe("other");
    expect(replySource({}).kind).toBe("other");
  });
});

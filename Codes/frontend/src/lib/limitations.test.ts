import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { consolidateLimitations } from "./trust";

const reports = join(__dirname, "../../../backend/reports");
const load = (n: string): unknown => {
  try {
    return JSON.parse(readFileSync(join(reports, n), "utf8"));
  } catch {
    return null;
  }
};

describe("Trust limitations are listed once", () => {
  it("drops a caveat paragraph that only repeats the list", () => {
    const agent = { limitations: ["Synthetic persona; not real patients.", "Lexicon screen can miss paraphrases."], caveat: "Synthetic persona; not real patients. Lexicon screen can miss paraphrases." };
    const g = consolidateLimitations(null, agent);
    expect(g).toEqual([{ source: "agent_multilingual", items: ["Synthetic persona; not real patients.", "Lexicon screen can miss paraphrases."] }]);
  });
  it("keeps a paragraph that adds a qualification of its own", () => {
    const agent = { limitations: ["Synthetic persona; not real patients."], caveat: "Synthetic persona; not real patients. Only one repeat per case." };
    const items = consolidateLimitations(null, agent)[0].items;
    expect(items).toHaveLength(2);
    expect(items[1]).toContain("Only one repeat");
  });
  it("keeps a lone caveat paragraph and removes exact repeats across reports", () => {
    const summary = { limitations: ["Not a medical device.", "Forecasts beyond 2 h are exploratory."] };
    const agent = { limitations: ["Not a medical device", "Scored by deterministic checks only."] };
    const g = consolidateLimitations(summary, agent);
    expect(g.map((x) => x.source)).toEqual(["summary", "agent_multilingual"]);
    expect(g.flatMap((x) => x.items)).toEqual(["Not a medical device.", "Forecasts beyond 2 h are exploratory.", "Scored by deterministic checks only."]);
    expect(consolidateLimitations(null, { caveat: "One paragraph." })).toEqual([{ source: "agent_multilingual", items: ["One paragraph."] }]);
  });
  it("returns nothing when no report is present", () => {
    expect(consolidateLimitations(null, undefined)).toEqual([]);
  });
  it.runIf(!!load("summary.json") && !!load("agent_multilingual.json"))("on the real reports, every distinct qualification survives exactly once", () => {
    const summary = load("summary.json") as { limitations?: string[] };
    const agent = load("agent_multilingual.json") as { limitations?: string[] };
    const all = consolidateLimitations(summary, agent).flatMap((g) => g.items);
    expect(new Set(all).size).toBe(all.length);
    for (const w of [...(summary.limitations ?? []), ...(agent.limitations ?? [])]) expect(all).toContain(w);
  });
});

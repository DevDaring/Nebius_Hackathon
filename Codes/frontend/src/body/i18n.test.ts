import { describe, expect, it } from "vitest";
import { allLocales } from "@/i18n/testLocales";
import { ORGAN_KEYS } from "@/lib/body";
import { PARTS, UNIT_KEY } from "./meta";

type Tree = { [k: string]: string | Tree };
const get = (tree: Tree, key: string): unknown => key.split(".").reduce<unknown>((n, p) => (n && typeof n === "object" ? (n as Tree)[p] : undefined), tree);

// Keys built at run time (template literals), which the literal-key test cannot see.
const dynamicKeys = [
  ...PARTS.flatMap((p) => [`body.part.${p}.name`, `body.part.${p}.desc`]),
  ...Object.values(UNIT_KEY),
  ...["front", "side", "back"].map((k) => `body.view.${k}`),
  ...["body", "chart"].map((k) => `body.toggle.${k}`),
  ...["releasing", "takingUp", "steady"].map((k) => `body.panel.${k}`),
];

describe("body view strings", () => {
  it("covers every organ the backend sends, plus blood", () => {
    expect(PARTS.slice().sort()).toEqual([...ORGAN_KEYS, "blood"].sort());
  });
  for (const [name, data] of Object.entries(allLocales())) {
    it(`${name} has every run-time body key`, () => {
      for (const k of dynamicKeys) expect(typeof get(data as Tree, k), `${name}: ${k}`).toBe("string");
    });
    it(`${name} keeps the honesty banner's two claims`, () => {
      const h = get(data as Tree, "body.honesty") as string;
      expect(h).toContain("·");
      expect(h.length).toBeGreaterThan(30);
    });
  }
});

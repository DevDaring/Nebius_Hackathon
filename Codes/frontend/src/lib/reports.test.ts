import { describe, expect, it } from "vitest";
import { humanizeKey, isObj, readStrings } from "./reports";

describe("report helpers", () => {
  it("isObj only accepts plain objects", () => {
    expect(isObj({})).toBe(true);
    expect(isObj([])).toBe(false);
    expect(isObj(null)).toBe(false);
  });
  it("readStrings tolerates mixed and missing lists", () => {
    expect(readStrings(null, "limitations")).toEqual([]);
    expect(readStrings({ limitations: ["a", { text: "b" }, 3, { title: "c" }] }, "limitations")).toEqual(["a", "b", "c"]);
  });
  it("humanizeKey", () => {
    expect(humanizeKey("rmse_60")).toBe("RMSE 60");
  });
});

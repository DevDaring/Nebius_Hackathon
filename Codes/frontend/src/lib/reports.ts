// Small shared helpers for reading reports/*.json. The typed readers live in lib/trust.ts.
// Nothing here ever invents a number: when data is missing, readers return empty results.

export type Obj = Record<string, unknown>;

export const isObj = (v: unknown): v is Obj => typeof v === "object" && v !== null && !Array.isArray(v);

/** A list of strings from report[key] (plain strings, or objects with text/title/name). */
export function readStrings(report: unknown, key: string): string[] {
  if (!isObj(report) || !Array.isArray(report[key])) return [];
  return (report[key] as unknown[])
    .map((x) => (typeof x === "string" ? x : isObj(x) ? String(x.text ?? x.title ?? x.name ?? "") : ""))
    .filter(Boolean);
}

/** Last-resort display name for a report key that has no translation. */
export const humanizeKey = (k: string) =>
  k
    .replace(/_/g, " ")
    .replace(/\brmse\b/gi, "RMSE")
    .replace(/\bauroc\b/gi, "AUROC")
    .replace(/\bauprc\b/gi, "AUPRC")
    .replace(/\bece\b/gi, "ECE")
    .replace(/\bmae\b/gi, "MAE")
    .replace(/coverage90/gi, "coverage (90%)")
    .replace(/width90/gi, "width (90%)")
    .replace(/^\w/, (c) => c.toUpperCase());

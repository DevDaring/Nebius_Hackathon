/**
 * How an agent reply was produced, for the small badge under each answer in the voice page.
 * Contract: `source` is "live" | "fixture"; `source_detail` names the exact path
 * ("rules", "template", "template fallback after <provider>", "<provider>:<model>", ...).
 * "template" / "rules" are also accepted directly in `source`.
 */
export type SourceKind = "live" | "fixture" | "template" | "rules" | "other";

export function replySource(r: { source?: string | null; source_detail?: string | null }): { kind: SourceKind; model: string | null; detail: string | null } {
  const src = (r.source ?? "").trim().toLowerCase();
  const detail = (r.source_detail ?? "").trim() || null;
  const d = (detail ?? "").toLowerCase();
  let kind: SourceKind = "other";
  if (src === "rules" || /^(rules?|safety)\b/.test(d)) kind = "rules";
  else if (src === "template" || d.startsWith("template")) kind = "template";
  else if (src === "live") kind = "live";
  else if (src === "fixture") kind = "fixture";
  // "<provider>:<vendor>/<model>" -> "<model>" (shown as a proper name, not translated).
  const model = kind === "live" && detail && /^[\w.-]+:\S+$/.test(detail) ? (detail.split(":").slice(1).join(":").split("/").pop() ?? null) : null;
  return { kind, model, detail };
}

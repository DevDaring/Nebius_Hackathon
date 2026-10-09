import type { Capabilities } from "@/api/types";

/** The capability flags the UI uses, with safe defaults when GET /api/capabilities is unavailable. */
export interface CapFlags {
  /** Known = the backend answered GET /api/capabilities. */
  known: boolean;
  chatModel: string | null;
  inferenceAvailable: boolean;
  /** Photo recognition offered (unknown backend: offered; a 503 is handled on upload). */
  vision: boolean;
  visionModel: string | null;
  visionNvidia: boolean;
  visionReason: string | null;
  /** Always false: Nebius Token Factory has no speech model and no other provider may be called. */
  speech: false;
  speechReason: string | null;
  /** Decorative fish allowed by the backend (unknown backend: allowed). */
  fish: boolean;
  guardrails: boolean;
}

export function capFlags(c: Capabilities | null | undefined): CapFlags {
  const f = c?.features ?? {};
  return {
    known: !!c,
    chatModel: c?.inference?.planner_model ?? c?.inference?.chat_model ?? null,
    inferenceAvailable: !!c?.inference?.available,
    vision: c ? !!f.vision?.enabled : true,
    visionModel: f.vision?.model ?? null,
    visionNvidia: !!f.vision?.nvidia,
    visionReason: f.vision?.reason ?? null,
    speech: false,
    speechReason: f.speech?.reason ?? null,
    fish: c ? f.fish?.enabled !== false : true,
    guardrails: !!f.guardrails?.enabled,
  };
}

/** "nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B" -> "NVIDIA-Nemotron-3-Nano-30B-A3B" (shown as a proper name). */
export const shortModel = (id: string | null | undefined) => (id ? (id.split("/").pop() ?? id) : null);

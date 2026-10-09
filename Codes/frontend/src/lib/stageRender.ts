/**
 * How the stage shows the next hours. The 3-D glass body is an optional enhancement: without
 * WebGL (or when the 3-D scene / its chunk fails) the same numbers are shown as a 2-D body plus a
 * readable table, and if the body view itself cannot load, the glucose chart and its table are shown.
 * None of this changes what is simulated: the forecast and body requests are the same in every mode.
 */
export type StageRender = "body3d" | "body2d" | "chart";

export interface StageCaps {
  /** User's choice on the stage toggle. */
  pref: "body" | "chart";
  webgl: boolean;
  /** The 3-D scene threw or lost its context. */
  glFailed: boolean;
  /** User asked for the simple (2-D) body. */
  simple: boolean;
  /** The body view chunk or component failed entirely. */
  bodyFailed: boolean;
}

export function stageRenderer(c: StageCaps): StageRender {
  if (c.pref === "chart" || c.bodyFailed) return "chart";
  if (!c.webgl || c.glFailed || c.simple) return "body2d";
  return "body3d";
}

/** The text table opens by default whenever 3-D is unavailable (not merely switched off by choice). */
export const textTableByDefault = (c: Pick<StageCaps, "webgl" | "glFailed">) => !c.webgl || c.glFailed;

/** WebGL probe (no context is kept). Any exception counts as "no WebGL". */
export function hasWebGL(doc: Document | undefined = typeof document === "undefined" ? undefined : document): boolean {
  try {
    if (!doc) return false;
    const c = doc.createElement("canvas");
    const gl = (c.getContext("webgl2") || c.getContext("webgl")) as WebGLRenderingContext | null;
    if (!gl) return false;
    gl.getExtension("WEBGL_lose_context")?.loseContext();
    return true;
  } catch {
    return false;
  }
}

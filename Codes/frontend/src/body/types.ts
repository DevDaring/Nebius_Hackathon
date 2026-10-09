import type { BodyView, OrganKey } from "@/api/types";
import type { BodyPart } from "@/lib/body";

/** Values the render loop reads every frame without re-rendering React. */
export interface LiveState {
  /** fractional time index 0..48 */
  tf: number;
  /** 0 = baseline, 1 = scenario (target of the crossfade) */
  mixTarget: number;
  playing: boolean;
}

export type CameraCmd =
  | { seq: number; kind: "front" | "side" | "back" | "reset" | "follow" }
  | { seq: number; kind: "focus"; part: BodyPart }
  | { seq: number; kind: "rotate"; dAz: number; dPolar: number }
  | { seq: number; kind: "zoom"; factor: number };

/** A camera command before it gets its sequence number. */
export type CameraCmdIn = CameraCmd extends infer C ? (C extends unknown ? Omit<C, "seq"> : never) : never;

export interface SceneLabel {
  part: BodyPart;
  name: string;
  value: string;
  unit: string;
  /** css colour of the dot */
  color: string;
}

export interface SceneProps {
  view: BodyView;
  scales: Record<OrganKey, number>;
  live: React.MutableRefObject<LiveState>;
  labels: SceneLabel[];
  selected: BodyPart | null;
  onSelect: (p: BodyPart) => void;
  /** double-click / double-tap on an organ: fly the camera to it */
  onFocus?: (p: BodyPart) => void;
  cmd: CameraCmd | null;
  reducedMotion: boolean;
  compact: boolean;
  presentation: boolean;
  /** false when the canvas is off-screen or the tab is hidden: rendering stops */
  active: boolean;
  /** timeline playing: the render loop keeps running */
  playing: boolean;
  /** user started dragging / zooming (stops autoplay hints etc.) */
  onInteract?: () => void;
  /** accessible name of the canvas */
  ariaLabel: string;
  onContextLost?: () => void;
}

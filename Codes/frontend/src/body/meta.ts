import type { BodyVariant, BodyView, OrganKey } from "@/api/types";
import { PALETTE, at, glucoseColor, liverColor, rgbCss, type BodyPart } from "@/lib/body";

export const PARTS: BodyPart[] = ["blood", "stomach", "intestine", "gut_to_blood", "liver", "pancreas", "insulin", "insulin_uptake", "exercise_uptake", "unexplained"];

/** i18n key of each organ's unit (the backend sends English units). */
export const UNIT_KEY: Record<BodyPart, string> = {
  stomach: "body.unit.g",
  intestine: "body.unit.g",
  gut_to_blood: "body.unit.flow",
  liver: "body.unit.flow",
  pancreas: "body.unit.insulinRate",
  insulin: "body.unit.insulinAbove",
  insulin_uptake: "body.unit.flow",
  exercise_uptake: "body.unit.flow",
  unexplained: "body.unit.flow",
  blood: "body.unit.mgdl",
};

/** Dot / accent colour of a part at a value. */
export function partColor(part: BodyPart, value: number): string {
  switch (part) {
    case "blood":
      return rgbCss(glucoseColor(value));
    case "liver":
      return rgbCss(liverColor(value));
    case "pancreas":
    case "insulin":
      return "rgb(233 200 142)";
    case "unexplained":
      return "rgb(185 178 255)";
    default:
      return rgbCss(PALETTE.marigold);
  }
}

export const variantOf = (view: BodyView, scenario: boolean): BodyVariant => (scenario && view.scenario ? view.scenario : view.baseline);

/** q50 and the likely range of a part at a time index. */
export function partStats(v: BodyVariant, part: BodyPart, i: number): { q50: number; lo: number; hi: number } {
  if (part === "blood") return { q50: at(v.blood.q50, i), lo: at(v.blood.q05, i), hi: at(v.blood.q95, i) };
  const s = v.fluxes[part as OrganKey];
  return { q50: at(s?.q50, i), lo: at(s?.q10, i), hi: at(s?.q90, i) };
}

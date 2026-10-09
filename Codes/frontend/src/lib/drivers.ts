import type { i18n as I18n, TFunction } from "i18next";
import type { Driver } from "@/api/types";
import { isEnglish } from "./langPrefs";

/**
 * Forecast drivers come from the backend with a machine name and an English label.
 * Physiology drivers have fixed names (meal_carbs, earlier_meals, ...). Learned drivers have
 * names derived from their English label (e.g. "Hours since your last reading" ->
 * "hours_since_your_last_reading"), so names can contain characters such as "/" or "'".
 * driverKey() turns any name into a safe i18n key under `drivers.`.
 */
export const driverKey = (name: string) =>
  name
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "");

/** English physiology labels the backend uses, so a bare label (doctor brief) can be mapped back to a name. */
const PHYSIOLOGY_LABELS: [RegExp, string][] = [
  [/^this meal's carbs/i, "meal_carbs"],
  [/^earlier food still digesting/i, "earlier_meals"],
  [/^your insulin sensitivity/i, "insulin_sensitivity"],
  [/^time of day \(body clock\)/i, "dawn_effect"],
  [/^recent activity/i, "recent_activity"],
  [/^recent unexplained trend/i, "unexplained"],
];

export function driverFromLabel(label: string): Driver {
  const hit = PHYSIOLOGY_LABELS.find(([re]) => re.test(label.trim()));
  return { name: hit ? hit[1] : driverKey(label), label_en: label, contribution: 0, source: hit ? "physiology" : "learned" };
}

/** Grams quoted in a label such as "This meal's carbs (60 g)". */
const gramsIn = (label: string | undefined) => {
  const m = /(\d+(?:\.\d+)?)\s*g\b/.exec(label ?? "");
  return m ? Math.round(Number(m[1])) : null;
};

/**
 * Localised driver label. English shows the backend's own label; other languages use the
 * translation when one exists and fall back to the English label otherwise.
 */
export function driverLabel(t: TFunction, i18n: I18n, d: Pick<Driver, "name" | "label_en">): string {
  const lang = i18n.language;
  const key = driverKey(d.name);
  if (isEnglish(lang) && d.label_en) return d.label_en;
  if (key === "meal_carbs") {
    const g = gramsIn(d.label_en);
    if (g !== null) return t("drivers.meal_carbs_g", { g });
  }
  if (i18n.exists(`drivers.${key}`)) return t(`drivers.${key}`);
  return d.label_en || d.name.replace(/_/g, " ");
}

/** Every driver name the backend can send today (used by the locale test). */
export const KNOWN_DRIVER_KEYS = [
  "meal_carbs",
  "meal_carbs_g",
  "earlier_meals",
  "insulin_sensitivity",
  "dawn_effect",
  "recent_activity",
  "unexplained",
  "current_glucose_level",
  "how_unsure_the_twin_is",
  "direction_of_the_last_30_min",
  "hours_since_your_last_reading",
  "last_reading_vs_twin_estimate",
  "carbs_in_this_meal",
  "carbs_in_the_last_2_h",
  "carbs_in_the_last_4_h",
  "meal_fat_protein_fibre",
  "activity_in_the_last_hour",
  "time_of_day",
  "how_many_readings_you_take",
  "physiology_model_s_peak",
  "physiology_model_s_high_risk_estimate",
  "physiology_model_s_low_risk_estimate",
  "twin_confidence",
  "your_usual_glucose_level",
  "your_usual_swings",
  "today_vs_your_usual_level",
  "age",
  "bmi",
  "hba1c",
];

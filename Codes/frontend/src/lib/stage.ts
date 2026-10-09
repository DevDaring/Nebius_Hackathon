import type { MealInput, Scenario, TwinState } from "@/api/types";

/** Dinner quick pick from the person's own recorded history: the latest evening meal. */
export function usualDinner(state: TwinState | undefined): MealInput | null {
  const meals = state?.history.meals ?? [];
  const evening = meals.filter((m) => {
    const h = new Date(m.t).getHours();
    return h >= 18 || h < 2;
  });
  const pick = (evening.length ? evening : meals).slice(-1)[0];
  if (!pick) return null;
  return { name: pick.name, carbs: pick.carbs, fibre: pick.fibre, protein: pick.protein, fat: pick.fat, minutes_from_now: 30 };
}

/** Plain-language assumptions behind a simulated change (shown next to every what-if result). */
export function scenarioAssumptions(t: (k: string, o?: Record<string, unknown>) => string, sc: Scenario, meal: MealInput): string[] {
  const out = [t("futures.assume.meal", { carbs: Math.round(meal.carbs), min: meal.minutes_from_now ?? 30 })];
  if (sc.carb_scale && sc.carb_scale !== 1) out.push(t("futures.assume.portion", { pct: Math.round(sc.carb_scale * 100) }));
  if (sc.walk_min) out.push(t("futures.assume.walk", { n: sc.walk_min, after: sc.walk_after_min ?? 10 }));
  if (sc.swap) out.push(t("futures.assume.swap"));
  if (sc.shift_min) out.push(t("futures.assume.timing", { n: Math.abs(sc.shift_min) }));
  out.push(t("futures.assume.sameBody"));
  out.push(t("futures.assume.notCausal"));
  return out;
}

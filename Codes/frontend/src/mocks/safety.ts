// Offline stand-in for the backend's shared safety policy (backend agent/safety.py
// assess_reading). Same thresholds as the chat rules: < 54 is an emergency, < 70 is low,
// > 300 is high and > 400 very high. Used only in offline mock mode. English only (other languages
// get a clear mock label); emergency guidance is location-neutral: no country-specific number.
import type { Lang, Safety, SafetyLevel } from "@/api/types";
import { mockLabel } from "./label";

const TEXT: Record<SafetyLevel, { title: string; message: string; actions: string[] }> = {
  ok: { title: "Reading added", message: "This reading is not in a danger zone.", actions: [] },
  low: {
    title: "This reading is low",
    message:
      "A reading of {v} mg/dL is below 70. Take something sugary now, like half a glass of fruit juice, and check again in 15 minutes. If it stays low or you feel unwell, call your local emergency number.",
    actions: ["Take 15 g of fast sugar", "Check again in 15 minutes", "Tell your doctor about low readings"],
  },
  very_low: {
    title: "This may be an emergency",
    message:
      "A reading of {v} mg/dL is dangerously low. Get help now: call your local emergency number. If you are awake and can swallow, take something sugary like juice. Do not stay alone.",
    actions: ["Call your local emergency number", "Take something sugary if you can swallow", "Do not stay alone"],
  },
  high: {
    title: "This reading is very high",
    message:
      "A reading of {v} mg/dL is above 300. Drink some water, check again in a while and test for ketones if you can. If it stays above 300, or you have vomiting, trouble breathing or drowsiness, call your local emergency number or see a doctor today.",
    actions: ["Drink water", "Check again in a while", "See a doctor today if it stays high"],
  },
  very_high: {
    title: "This reading is dangerously high",
    message:
      "A reading of {v} mg/dL is above 400. Call your local emergency number or go to a hospital now if you have vomiting, trouble breathing or drowsiness; otherwise see a doctor today. Do not change any medicine without your doctor.",
    actions: ["Call your local emergency number if you have vomiting, trouble breathing or drowsiness", "See a doctor today", "Drink water"],
  },
};

export function levelFor(mgdl: number): SafetyLevel {
  if (mgdl < 54) return "very_low";
  if (mgdl < 70) return "low";
  if (mgdl > 400) return "very_high";
  if (mgdl > 300) return "high";
  return "ok";
}

export function assessReading(mgdl: number, lang: Lang): Safety {
  const level = levelFor(mgdl);
  const tx = TEXT[level];
  const v = String(Math.round(mgdl));
  return { level, emergency: level === "very_low", title: `${mockLabel(lang)}${tx.title}`, message: tx.message.replace("{v}", v), actions: tx.actions };
}

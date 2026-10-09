// Static mock catalogues. Everything here is illustrative and only served in offline mock mode.
import type { Food, FoodSwap, LabField, Lang, PatientDetail, Sample, TourStep, VoiceSample } from "@/api/types";
import { isLang } from "@/api/types";
import { MODELS, NOW, fmtLocal, sparkline, weekStats } from "./sim";

const PEOPLE: Omit<PatientDetail, "sparkline" | "tir_7d" | "risk_7d" | "calibration">[] = [
  {
    id: "kolkata-shopkeeper",
    name: "Subrata Das",
    age: 54,
    sex: "M",
    city: "Kolkata",
    occupation: "Shopkeeper",
    language: "en-US",
    synthetic: true,
    source_note: "Synthetic composite: open CGM trajectory + invented EHR and name (offline mock)",
    hba1c: 7.9,
    avatar_initials: "SD",
    ehr: {
      bmi: 26.1,
      diabetes_years: 6,
      medications: ["Metformin 500 mg twice daily"],
      fasting_glucose: 138,
      ldl: 124,
      egfr: 86,
      conditions: ["Type 2 diabetes", "Hypertension"],
    },
    sleep_window: MODELS[0].sleep,
  },
  {
    id: "mysuru-teacher",
    name: "Lakshmi Gowda",
    age: 47,
    sex: "F",
    city: "Mysuru",
    occupation: "School teacher",
    language: "en-US",
    synthetic: true,
    source_note: "Synthetic composite: open CGM trajectory + invented EHR and name (offline mock)",
    hba1c: 7.1,
    avatar_initials: "LG",
    ehr: {
      bmi: 24.3,
      diabetes_years: 3,
      medications: ["Metformin 500 mg once daily"],
      fasting_glucose: 121,
      ldl: 108,
      egfr: 98,
      conditions: ["Type 2 diabetes"],
    },
    sleep_window: MODELS[1].sleep,
  },
  {
    id: "lucknow-retiree",
    name: "Ramesh Srivastava",
    age: 61,
    sex: "M",
    city: "Lucknow",
    occupation: "Retired clerk",
    language: "en-US",
    synthetic: true,
    source_note: "Synthetic composite: open CGM trajectory + invented EHR and name (offline mock)",
    hba1c: 8.4,
    avatar_initials: "RS",
    ehr: {
      bmi: 27.8,
      diabetes_years: 11,
      medications: ["Metformin 1000 mg twice daily", "Glimepiride 1 mg"],
      fasting_glucose: 146,
      ldl: 132,
      egfr: 71,
      conditions: ["Type 2 diabetes", "Dyslipidaemia"],
    },
    sleep_window: MODELS[2].sleep,
  },
];

export function patientDetail(id: string): PatientDetail {
  const p = PEOPLE.find((x) => x.id === id);
  const model = MODELS.find((m) => m.id === id);
  if (!p || !model) throw new Error("not found");
  const w = weekStats(model);
  const end = new Date(NOW);
  end.setDate(end.getDate() - 30);
  const start = new Date(end);
  start.setDate(start.getDate() - 14);
  return {
    ...p,
    sparkline: sparkline(model),
    tir_7d: w.tir,
    risk_7d: Math.round((1 - w.tir) * 0.9 * 100) / 100,
    calibration: { cgm_days: 14, start: fmtLocal(start), end: fmtLocal(end) },
  };
}

export const allPatients = () => PEOPLE.map((p) => patientDetail(p.id));

// ---------- food table (per ONE unit) ----------
const F = (
  id: string,
  name_en: string,
  unit: string,
  unit_label: string,
  grams: number,
  carbs: number,
  fibre: number,
  protein: number,
  fat: number,
  cuisine: string,
): Food => ({
  id,
  name: name_en,
  name_en,
  unit,
  unit_label,
  grams_per_unit: grams,
  carbs_g: carbs,
  fibre_g: fibre,
  protein_g: protein,
  fat_g: fat,
  kcal: Math.round(carbs * 4 + protein * 4 + fat * 9),
  cuisine,
});

export const FOODS: Food[] = [
  F("white_rice", "Steamed white rice", "katori", "katori (150 g)", 150, 42, 0.6, 4, 0.4, "pan-Indian"),
  F("brown_rice", "Brown rice", "katori", "katori (150 g)", 150, 35, 2.7, 4, 1.4, "pan-Indian"),
  F("roti", "Wheat roti", "piece", "roti (40 g)", 40, 18, 2.5, 3.5, 1.5, "North Indian"),
  F("paratha", "Plain paratha", "piece", "paratha (60 g)", 60, 26, 2.4, 4.5, 8, "North Indian"),
  F("ragi_mudde", "Ragi mudde", "ball", "ball (120 g)", 120, 38, 4.2, 3.5, 0.8, "Karnataka"),
  F("idli", "Idli", "piece", "idli (45 g)", 45, 12, 0.6, 2, 0.2, "South Indian"),
  F("dosa", "Plain dosa", "piece", "dosa (80 g)", 80, 28, 1.2, 4, 4, "South Indian"),
  F("dal", "Toor dal", "katori", "katori (150 ml)", 150, 18, 4.5, 8, 2.5, "pan-Indian"),
  F("masoor_dal", "Masoor dal", "katori", "katori (150 ml)", 150, 17, 4.8, 9, 2, "Bengali"),
  F("sambar", "Sambar", "katori", "katori (150 ml)", 150, 14, 3.8, 5, 3, "South Indian"),
  F("macher_jhol", "Macher jhol (fish curry)", "katori", "katori (150 g)", 150, 6, 1, 20, 9, "Bengali"),
  F("aloo_posto", "Aloo posto", "katori", "katori (100 g)", 100, 20, 2.5, 3, 9, "Bengali"),
  F("aloo_bhaja", "Aloo bhaja", "katori", "katori (60 g)", 60, 21, 1.8, 2, 10, "Bengali"),
  F("begun_bhaja", "Begun bhaja", "piece", "slice (40 g)", 40, 4, 1.6, 0.6, 5, "Bengali"),
  F("shukto", "Shukto", "katori", "katori (100 g)", 100, 9, 3, 2.5, 5, "Bengali"),
  F("paneer_curry", "Paneer curry", "katori", "katori (150 g)", 150, 10, 1.5, 14, 18, "North Indian"),
  F("rajma", "Rajma", "katori", "katori (150 g)", 150, 24, 7, 9, 4, "North Indian"),
  F("mixed_sabzi", "Mixed vegetable sabzi", "katori", "katori (100 g)", 100, 10, 3.5, 2.5, 5, "pan-Indian"),
  F("palya", "Beans palya", "katori", "katori (100 g)", 100, 8, 3.8, 2.5, 4, "Karnataka"),
  F("curd", "Curd (dahi)", "katori", "katori (100 g)", 100, 4.5, 0, 3.5, 4, "pan-Indian"),
  F("curd_rice", "Curd rice", "katori", "katori (150 g)", 150, 34, 0.6, 6, 5, "South Indian"),
  F("kadhi", "Kadhi", "katori", "katori (150 ml)", 150, 10, 0.8, 4.5, 6, "North Indian"),
  F("veg_korma", "Vegetable korma", "katori", "katori (150 g)", 150, 14, 3, 4, 13, "North Indian"),
  F("veg_stew", "Vegetable stew", "katori", "katori (150 g)", 150, 12, 3.2, 3, 9, "Kerala"),
  F("salad", "Cucumber-onion salad", "plate", "small plate (80 g)", 80, 4, 1.2, 0.8, 0.2, "pan-Indian"),
  F("rasgulla", "Rasgulla", "piece", "piece (50 g)", 50, 20, 0, 2, 1.5, "Bengali"),
  F("mishti_doi", "Mishti doi", "katori", "small cup (100 g)", 100, 22, 0, 4, 4, "Bengali"),
  F("banana", "Banana", "piece", "medium (100 g)", 100, 23, 2.6, 1.1, 0.3, "pan-Indian"),
  F("guava", "Guava", "piece", "medium (100 g)", 100, 14, 5.4, 2.6, 1, "pan-Indian"),
  F("muri", "Muri (puffed rice)", "cup", "cup (25 g)", 25, 22, 0.4, 1.6, 0.2, "Bengali"),
  F("poha", "Poha", "katori", "katori (120 g)", 120, 32, 1.5, 3.5, 5, "pan-Indian"),
  F("upma", "Rava upma", "katori", "katori (120 g)", 120, 30, 1.8, 4.5, 6, "South Indian"),
  F("chapati_multigrain", "Multigrain roti", "piece", "roti (40 g)", 40, 15, 3.8, 4, 1.8, "North Indian"),
];

export const SWAPS: (FoodSwap & { factor: number })[] = [
  { from: "white_rice", to: "roti", label_en: "Swap rice for 2 rotis", factor: 0.8 },
  { from: "white_rice", to: "brown_rice", label_en: "Swap white rice for brown rice", factor: 0.86 },
  { from: "white_rice", to: "ragi_mudde", label_en: "Swap rice for ragi mudde", factor: 0.82 },
  { from: "aloo_bhaja", to: "salad", label_en: "Swap aloo bhaja for salad", factor: 0.9 },
  { from: "rasgulla", to: "guava", label_en: "Swap the sweet for a guava", factor: 0.9 },
  { from: "roti", to: "chapati_multigrain", label_en: "Swap wheat roti for multigrain roti", factor: 0.93 },
];

export const MEAL_SAMPLES: Sample[] = [
  { id: "bengali_fish_thali", title: "Bengali fish thali", image_url: "/mock/thali-bengali.svg" },
  { id: "north_indian_thali", title: "North Indian thali", image_url: "/mock/thali-north.svg" },
  { id: "karnataka_oota", title: "Karnataka oota", image_url: "/mock/thali-karnataka.svg" },
];

export const MEAL_SAMPLE_DISHES: Record<string, { food_id: string | null; detected: string; units: number; confidence: number; candidates?: string[] }[]> = {
  bengali_fish_thali: [
    { food_id: "white_rice", detected: "white rice mound", units: 1.5, confidence: 0.93 },
    { food_id: "masoor_dal", detected: "yellow lentil soup", units: 1, confidence: 0.86 },
    { food_id: "macher_jhol", detected: "fish in thin curry", units: 1, confidence: 0.81 },
    { food_id: "aloo_bhaja", detected: "fried potato sticks", units: 1, confidence: 0.77 },
    { food_id: null, detected: "small white sweet", units: 1, confidence: 0.42, candidates: ["rasgulla", "mishti_doi"] },
  ],
  north_indian_thali: [
    { food_id: "roti", detected: "flatbread", units: 2, confidence: 0.94 },
    { food_id: "white_rice", detected: "rice", units: 0.75, confidence: 0.9 },
    { food_id: "dal", detected: "yellow dal", units: 1, confidence: 0.87 },
    { food_id: "paneer_curry", detected: "paneer in gravy", units: 1, confidence: 0.83 },
    { food_id: null, detected: "creamy yellow curry", units: 1, confidence: 0.38, candidates: ["kadhi", "veg_korma", "veg_stew"] },
    { food_id: "salad", detected: "salad", units: 1, confidence: 0.88 },
  ],
  karnataka_oota: [
    { food_id: "ragi_mudde", detected: "dark millet ball", units: 1, confidence: 0.9 },
    { food_id: "white_rice", detected: "rice", units: 1, confidence: 0.92 },
    { food_id: "sambar", detected: "sambar", units: 1, confidence: 0.89 },
    { food_id: "palya", detected: "green vegetable stir-fry", units: 1, confidence: 0.8 },
    { food_id: "curd", detected: "curd", units: 1, confidence: 0.85 },
  ],
};

export const LAB_SAMPLES: Sample[] = [
  { id: "lab_kolkata_2026", title: "Diagnostic centre report (photo)", image_url: "/mock/lab-report.svg" },
  { id: "lab_pdf_lipid", title: "Lipid + kidney panel (PDF)", image_url: "/mock/lab-report-2.svg" },
];

export const LAB_FIELDS: LabField[] = [
  { code: "hba1c", name: "HbA1c", value: 7.9, unit: "%", ref_range: "4.0-5.6", implausible: false, loinc: "4548-4" },
  { code: "fpg", name: "Fasting plasma glucose", value: 1420, unit: "mg/dL", ref_range: "70-99", implausible: true, loinc: "1558-6" },
  { code: "ldl", name: "LDL cholesterol", value: 124, unit: "mg/dL", ref_range: "<100", implausible: false, loinc: "13457-7" },
  { code: "hdl", name: "HDL cholesterol", value: 41, unit: "mg/dL", ref_range: ">40", implausible: false, loinc: "2085-9" },
  { code: "tg", name: "Triglycerides", value: 188, unit: "mg/dL", ref_range: "<150", implausible: false, loinc: "2571-8" },
  { code: "creat", name: "Serum creatinine", value: 1.02, unit: "mg/dL", ref_range: "0.7-1.3", implausible: false, loinc: "2160-0" },
  { code: "egfr", name: "eGFR", value: 86, unit: "mL/min/1.73m2", ref_range: ">90", implausible: false, loinc: "62238-1" },
  { code: "med_metformin", name: "Medication: Metformin", value: "500 mg twice daily", unit: "", ref_range: "", implausible: false },
];

export const TOUR: TourStep[] = [
  { id: "stage", title_en: "Meet the twin", body_en: "This curve is Subrata's glucose twin. Dots are real readings; the blue curve is the next 4 hours.", route: "/", action: "river" },
  { id: "ladder", title_en: "Fewer pricks, honest band", body_en: "Move down the sensor ladder. The band widens because the twin knows less, and says so.", route: "/", action: "ladder" },
  { id: "prick", title_en: "One prick teaches a lot", body_en: "Add a finger-prick. Watch the ripple and the band tighten.", route: "/", action: "add-reading" },
  { id: "meal", title_en: "Meal to forecast", body_en: "Pick a sample meal. Fix the dishes, then see this person's curve.", route: "/meal", action: "meal-samples" },
  { id: "trust", title_en: "Numbers you can check", body_en: "Every accuracy number here is read from the evaluation reports.", route: "/trust", action: "trust-ladder" },
];

export const VOICE_SAMPLES: VoiceSample[] = [
  { lang: "en-US", prompt: "What will my glucose be after dinner?" },
  { lang: "en-US", prompt: "When should I check next?" },
  { lang: "es-ES", prompt: "¿Cómo estará mi glucosa después de cenar?" },
  { lang: "es-ES", prompt: "¿Qué pasa si camino 15 minutos después de cenar?" },
  { lang: "fr-FR", prompt: "Quelle sera ma glycémie après le dîner ?" },
  { lang: "fr-FR", prompt: "Quand dois-je mesurer la prochaine fois ?" },
  { lang: "de-DE", prompt: "Wie wird mein Blutzucker nach dem Abendessen sein?" },
  { lang: "de-DE", prompt: "Was ändert ein 15-minütiger Spaziergang nach dem Essen?" },
  { lang: "it-IT", prompt: "Come sarà la mia glicemia dopo cena?" },
  { lang: "it-IT", prompt: "Quando devo misurare la prossima volta?" },
  { lang: "ja-JP", prompt: "夕食後の血糖値はどうなりますか？" },
  { lang: "ja-JP", prompt: "次はいつ測ればいいですか？" },
];

export const langOf = (l: string): Lang => (isLang(l) ? l : "en-US");

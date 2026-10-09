import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { AnimatePresence, m as motion } from "framer-motion";
import { Camera, ChevronRight, Footprints, ImageUp, Loader2, Minus, PenLine, Plus, RotateCcw, Scale, Search, Sparkles, Timer, X } from "lucide-react";
import { api } from "@/api";
import type { Food, Lang, MealInput, MealParse, Sample, Scenario } from "@/api/types";
import { useActivePatientId, useCapabilities, useHealth, useFoodSearch, useFoodSwaps, useForecast, useMealSamples, useTwinState } from "@/api/hooks";
import { capFlags } from "@/lib/capabilities";
import { mediaUrl } from "@/api/http";
import { GlucoseRiver } from "@/charts/GlucoseRiver";
import { ErrorState, Modal, PageHeader } from "@/components/ui";
import { EvidenceChip } from "@/components/evidence";
import { LowEvidencePanel, ReliabilityLine } from "@/components/stage";
import { ApiError } from "@/api/http";
import { useApp } from "@/store/app";
import { formatReplayTime, freqText, pct, round1, swapLabel } from "@/lib/format";

interface EditDish {
  key: string;
  food_id: string | null;
  detected: string;
  name: string;
  units: number;
  unit: string;
  per: { carbs: number; fibre: number; protein: number; fat: number };
  confidence: number;
  needs_pick: boolean;
  candidates: Food[];
}

function toEdit(parse: MealParse): EditDish[] {
  return parse.dishes.map((d, i) => {
    const u = d.units > 0 ? d.units : 1;
    return {
      key: `${i}-${d.detected}`,
      food_id: d.food_id,
      detected: d.detected,
      name: d.name,
      units: d.units,
      unit: d.unit,
      per: { carbs: d.carbs / u, fibre: d.fibre / u, protein: d.protein / u, fat: d.fat / u },
      confidence: d.confidence,
      needs_pick: d.needs_pick,
      candidates: d.candidates ?? [],
    };
  });
}

const fromFood = (d: EditDish, f: Food): EditDish => ({
  ...d,
  food_id: f.id,
  name: f.name,
  unit: f.unit_label || f.unit,
  per: { carbs: f.carbs_g, fibre: f.fibre_g, protein: f.protein_g, fat: f.fat_g },
  needs_pick: false,
  confidence: 1,
});

const humanize = (id: string) => id.replace(/_/g, " ");
/** "1 katori (150 g; from 25 g dry dal)" -> "katori": the multiplier is shown separately. */
const shortUnit = (u: string) => u.replace(/^1\s+/, "").replace(/\s*\(.*\)\s*$/, "") || u;

/* ---------------- dish picker (swap / needs_pick) ---------------- */
function DishPicker({ dish, onClose, onPick }: { dish: EditDish | null; onClose: () => void; onPick: (f: Food) => void }) {
  const { t, i18n } = useTranslation();
  const [q, setQ] = useState("");
  useEffect(() => setQ(""), [dish?.key]);
  const search = useFoodSearch(q, i18n.language as Lang);
  const list = q.trim().length >= 2 ? (search.data ?? []) : (dish?.candidates ?? []);
  return (
    <Modal
      open={!!dish}
      onClose={onClose}
      title={dish?.needs_pick ? t("meal.needsPick") : t("meal.changeDish")}
      subtitle={dish ? t("meal.pickFor", { detected: dish.detected }) : undefined}
    >
      <label htmlFor="dish-search" className="sr-only">
        {t("meal.search")}
      </label>
      <div className="relative mt-1">
        <Search size={18} className="pointer-events-none absolute left-4 top-1/2 -translate-y-1/2 text-ink-3" aria-hidden />
        <input id="dish-search" data-autofocus className="field pl-11" placeholder={t("meal.searchPlaceholder")} value={q} onChange={(e) => setQ(e.target.value)} autoComplete="off" />
      </div>
      <ul className="mt-4 space-y-2" aria-live="polite">
        {search.isFetching && q.trim().length >= 2 && list.length === 0 && <li className="skeleton h-14" />}
        {list.map((f) => (
          <li key={f.id}>
            <button type="button" onClick={() => onPick(f)} className="flex w-full items-center justify-between gap-3 rounded-2xl border border-line bg-card px-4 py-3 text-left hover:border-marigold-ink/50 hover:bg-paper-2">
              <span>
                <span className="block font-semibold">{f.name}</span>
                <span className="block text-sm text-ink-3">
                  {f.unit_label} · <span className="num">{t("meal.carbs", { n: round1(f.carbs_g) })}</span> · {f.cuisine}
                </span>
              </span>
              <ChevronRight size={18} className="text-ink-3" aria-hidden />
            </button>
          </li>
        ))}
        {q.trim().length >= 2 && !search.isFetching && list.length === 0 && <li className="text-sm text-ink-3">{t("meal.noResults")}</li>}
      </ul>
    </Modal>
  );
}

/* ---------------- page ---------------- */
export default function MealPage() {
  const { t, i18n } = useTranslation();
  const navigate = useNavigate();
  const pid = useActivePatientId();
  const ladder = useApp((s) => s.ladder);
  const draft = useApp((s) => s.mealDraft);
  const setDraft = useApp((s) => s.setMealDraft);
  const seedWhatIf = useApp((s) => s.seedWhatIf);
  const setStageDinner = useApp((s) => s.setStageDinner);
  const samples = useMealSamples();
  // American plates first, then Indian ones; headings only when both are present.
  const sampleGroups = useMemo(() => {
    const order = ["us", "india", "other"] as const;
    const by = new Map<string, Sample[]>();
    for (const s of samples.data ?? []) {
      const r = s.region === "us" || s.region === "india" ? s.region : "other";
      by.set(r, [...(by.get(r) ?? []), s]);
    }
    return order.filter((r) => by.has(r)).map((r) => [r, by.get(r) as Sample[]] as const);
  }, [samples.data]);
  const health = useHealth();
  const caps = capFlags(useCapabilities().data);
  const swaps = useFoodSwaps(i18n.language as Lang);
  const state = useTwinState(pid, ladder);

  const [phase, setPhase] = useState<"pick" | "parsing" | "edit">(draft ? "edit" : "pick");
  const [parse, setParse] = useState<MealParse | null>(draft?.parse ?? null);
  const [dishes, setDishes] = useState<EditDish[]>(draft ? toEdit(draft.parse) : []);
  const [title, setTitle] = useState<string>(draft?.meal.name ?? "");
  const [photo, setPhoto] = useState<string | null>(draft?.photoUrl ?? null);
  const [credit, setCredit] = useState<string | null>(null);
  const [when, setWhen] = useState<number>(draft?.meal.minutes_from_now ?? 15);
  const [picker, setPicker] = useState<EditDish | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [requested, setRequested] = useState<MealInput | null>(draft?.meal ?? null);
  const camRef = useRef<HTMLInputElement>(null);
  const upRef = useRef<HTMLInputElement>(null);
  const resultRef = useRef<HTMLDivElement>(null);

  const runParse = async (input: { image: File } | { sample_id: string }, label: string, preview: string | null, photoCredit: string | null = null) => {
    setPhase("parsing");
    setCredit(photoCredit);
    setError(null);
    setPhoto(preview);
    setTitle(label);
    setRequested(null);
    try {
      const res = await api.mealPhoto(input);
      setParse(res);
      setDishes(toEdit(res));
      setPhase("edit");
    } catch (e) {
      // 503: the backend runs in demo mode without a vision model. Steer to the samples.
      if (e instanceof ApiError && e.status === 503)
        setError(health.data?.mode === "live" ? t("meal.liveFailed") : "image" in input ? t("meal.liveUnavailable") : t("meal.sampleUnavailable"));
      else if (e instanceof ApiError && e.status === 413) setError(t("meal.tooLarge"));
      else setError(t("meal.parseError"));
      setPhase("pick");
      setPhoto(null);
      window.setTimeout(() => document.querySelector('[data-tour="meal-samples"]')?.scrollIntoView({ behavior: "smooth", block: "center" }), 80);
    }
  };

  /** Manual entry: an empty meal built from the food table (first-class, no photo and no model). */
  const startManual = () => {
    const empty: MealParse = { dishes: [], total: { carbs: 0, fibre: 0, protein: 0, fat: 0, kcal: 0 }, carbs_sd: 0, source: "manual", recognition: null };
    setError(null);
    setPhoto(null);
    setCredit(null);
    setTitle(t("meal.manual"));
    setRequested(null);
    setParse(empty);
    setDishes([]);
    setPhase("edit");
  };
  const addDish = () => {
    const d: EditDish = {
      key: `manual-${Date.now()}`,
      food_id: null,
      detected: t("meal.newDish"),
      name: t("meal.newDish"),
      units: 1,
      unit: "",
      per: { carbs: 0, fibre: 0, protein: 0, fat: 0 },
      confidence: 1,
      needs_pick: true,
      candidates: [],
    };
    setDishes((ds) => [...ds, d]);
    setPicker(d);
  };

  const onFile = (f: File | undefined) => {
    if (!f) return;
    void runParse({ image: f }, t("meal.title"), URL.createObjectURL(f));
  };

  const totals = useMemo(() => {
    const s = (k: keyof EditDish["per"]) => round1(dishes.reduce((a, d) => a + d.per[k] * d.units, 0));
    return { carbs: s("carbs"), fibre: s("fibre"), protein: s("protein"), fat: s("fat") };
  }, [dishes]);
  const carbsSd = parse ? round1(parse.carbs_sd * (parse.total.carbs > 0 ? totals.carbs / parse.total.carbs : 1)) : 0;
  const unresolved = dishes.some((d) => d.needs_pick);

  const meal: MealInput = useMemo(
    () => ({
      name: title || t("meal.title"),
      carbs: totals.carbs,
      carbs_sd: carbsSd,
      fibre: totals.fibre,
      protein: totals.protein,
      fat: totals.fat,
      minutes_from_now: when,
      items: dishes.filter((d) => d.food_id).map((d) => ({ food_id: d.food_id as string, units: d.units })),
    }),
    [title, totals, carbsSd, when, dishes, t],
  );

  const forecast = useForecast(pid, requested ? { ladder, horizon_min: 240, meal: requested } : null);

  const showCurve = () => {
    if (unresolved || !parse) return;
    setRequested(meal);
    setDraft({ parse, meal, photoUrl: photo });
    setStageDinner({ meal, source: "meal", title: title || t("meal.title") });
    window.setTimeout(() => resultRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }), 120);
  };

  const setUnits = (key: string, delta: number) =>
    setDishes((ds) => ds.map((d) => (d.key === key ? { ...d, units: Math.max(0, Math.round((d.units + delta) * 4) / 4) } : d)));
  const remove = (key: string) => setDishes((ds) => ds.filter((d) => d.key !== key));

  const suggestions = useMemo(() => {
    const out: { key: string; label: string; scenario: Scenario; icon: typeof Sparkles }[] = [];
    for (const sw of swaps.data ?? []) {
      const d = dishes.find((x) => x.food_id === sw.from);
      if (d && !out.some((o) => o.key.startsWith("swap"))) {
        const sl = swapLabel(sw, i18n.language);
        const label = sl.english ? t("meal.sugSwap", { from: d.name, to: humanize(sw.to) }) : sl.text;
        out.push({ key: `swap-${sw.from}-${sw.to}`, label, scenario: { swap: { from: sw.from, to: sw.to, from_qty: sw.from_qty, to_qty: sw.to_qty }, label: sw.label_en }, icon: Sparkles });
      }
    }
    out.push({ key: "portion", label: t("meal.sugHalf", { pct: 70 }), scenario: { carb_scale: 0.7, label: "70% of the carbs" }, icon: Scale });
    out.push({ key: "walk", label: t("meal.sugWalk", { n: 15 }), scenario: { walk_min: 15, walk_after_min: 10, label: "15-minute walk after the meal" }, icon: Footprints });
    if (when >= 30) out.push({ key: "earlier", label: t("meal.sugEarlier", { n: 30 }), scenario: { shift_min: -30, label: "Eat 30 minutes earlier" }, icon: Timer });
    return out;
  }, [swaps.data, dishes, when, i18n.language, t]);

  const openWhatIf = (scenario: Scenario) => {
    const base = requested ?? meal;
    if (parse) setDraft({ parse, meal: base, photoUrl: photo });
    seedWhatIf({ base, scenario });
    navigate("/whatif");
  };

  const startOver = () => {
    setPhase("pick");
    setParse(null);
    setDishes([]);
    setPhoto(null);
    setRequested(null);
    setDraft(null);
  };

  const s = state.data;
  const fc = forecast.data;

  return (
    <div className="mx-auto max-w-6xl px-4 py-8 sm:px-6">
      <PageHeader
        title={t("meal.title")}
        subtitle={t("meal.subtitle")}
        right={
          phase !== "pick" && (
            <button type="button" className="btn-ghost" onClick={startOver}>
              <RotateCcw size={16} aria-hidden />
              {t("meal.startOver")}
            </button>
          )
        }
      />

      <input ref={camRef} type="file" accept="image/*" capture="environment" className="sr-only" tabIndex={-1} aria-hidden onChange={(e) => {
          onFile(e.target.files?.[0]);
          e.target.value = ""; // allow picking the same file again after an error
        }} />
      <input ref={upRef} type="file" accept="image/*" className="sr-only" tabIndex={-1} aria-hidden onChange={(e) => {
          onFile(e.target.files?.[0]);
          e.target.value = ""; // allow picking the same file again after an error
        }} />

      {error && (
        <div role="alert" className="mb-6 flex items-start gap-3 rounded-3xl border border-marigold-ink/40 bg-marigold/10 p-4 text-sm font-medium text-ink">
          <Sparkles size={18} className="mt-0.5 shrink-0 text-marigold-ink" aria-hidden />
          <span className="flex-1">{error}</span>
          <button type="button" onClick={() => setError(null)} className="-m-1 rounded-full p-1 text-ink-3 hover:text-ink" aria-label={t("common.close")}>
            <X size={16} aria-hidden />
          </button>
        </div>
      )}

      <AnimatePresence mode="wait">
        {phase === "pick" && (
          <motion.div key="pick" initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}>
            {!caps.vision && (
              <p className="mb-3 rounded-2xl border border-line bg-card px-4 py-3 text-sm text-ink-2" role="note" data-vision-off>
                {t("meal.visionOff")}
              </p>
            )}
            <div className={`grid gap-3 ${caps.vision ? "sm:grid-cols-3" : "sm:grid-cols-1"}`}>
              {caps.vision && (
                <>
              <button type="button" onClick={() => camRef.current?.click()} className="stage on-night flex min-h-[120px] items-center gap-4 rounded-4xl p-6 text-left shadow-lift transition hover:-translate-y-0.5">
                <span className="inline-flex h-14 w-14 items-center justify-center rounded-full bg-marigold text-night">
                  <Camera size={26} aria-hidden />
                </span>
                <span className="text-xl font-bold text-moon">{t("meal.takePhoto")}</span>
              </button>
              <button type="button" onClick={() => upRef.current?.click()} className="card flex min-h-[120px] items-center gap-4 p-6 text-left transition hover:-translate-y-0.5 hover:shadow-lift">
                <span className="inline-flex h-14 w-14 items-center justify-center rounded-full bg-paper-2 text-ink">
                  <ImageUp size={26} aria-hidden />
                </span>
                <span className="text-xl font-bold">{t("meal.upload")}</span>
              </button>
                </>
              )}
              <button type="button" onClick={startManual} className="card flex min-h-[120px] items-center gap-4 p-6 text-left transition hover:-translate-y-0.5 hover:shadow-lift" data-meal-manual>
                <span className="inline-flex h-14 w-14 shrink-0 items-center justify-center rounded-full bg-paper-2 text-ink">
                  <PenLine size={26} aria-hidden />
                </span>
                <span>
                  <span className="block text-xl font-bold">{t("meal.manual")}</span>
                  <span className="mt-0.5 block text-sm text-ink-3">{t("meal.manualHint")}</span>
                </span>
              </button>
            </div>
            {caps.vision && caps.visionModel && <p className="mt-2 text-xs text-ink-3">{t("meal.recognisedBy", { model: caps.visionModel })}</p>}
            <h2 className="mb-3 mt-10 text-lg font-bold">{t("meal.orSample")}</h2>
            <div className="space-y-6" data-tour="meal-samples">
              {samples.isLoading && (
                <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5">
                  {[0, 1, 2, 3, 4].map((i) => <div key={i} className="skeleton aspect-[4/3]" />)}
                </div>
              )}
              {samples.data && samples.data.length === 0 && <p className="text-sm text-ink-3">{t("meal.noSamples")}</p>}
              {samples.isError && <ErrorState message={t("errors.network")} onRetry={() => void samples.refetch()} />}
              {sampleGroups.map(([region, group]) => (
                <section key={region} aria-label={sampleGroups.length > 1 ? t(`meal.samplesFrom.${region}`) : undefined}>
                  {sampleGroups.length > 1 && <h3 className="mb-2 text-sm font-semibold uppercase tracking-wide text-ink-3">{t(`meal.samplesFrom.${region}`)}</h3>}
                  <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5">
                    {group.map((s) => (
                    <button
                      key={s.id}
                      type="button"
                      onClick={() => void runParse({ sample_id: s.id }, s.title, mediaUrl(s.image_url), s.attribution ?? null)}
                      className="group flex flex-col overflow-hidden rounded-4xl border border-line bg-card text-left shadow-soft transition hover:-translate-y-0.5 hover:shadow-lift"
                    >
                      <span className="block aspect-[4/3] overflow-hidden bg-night">
                        <img src={mediaUrl(s.image_url) ?? ""} alt={t("meal.sampleAlt", { title: s.title })} className="h-full w-full object-cover transition duration-500 group-hover:scale-[1.03]" loading="lazy" />
                      </span>
                      <span className="flex flex-1 flex-col justify-between gap-2 px-5 py-4">
                        <span className="flex items-start justify-between gap-2 font-semibold leading-snug">
                          {s.title}
                          <ChevronRight size={18} className="mt-0.5 shrink-0 text-ink-3" aria-hidden />
                        </span>
                        {s.attribution && <span className="text-[0.7rem] leading-snug text-ink-3">{t("meal.photoCredit", { credit: s.attribution })}</span>}
                      </span>
                    </button>
                    ))}
                  </div>
                </section>
              ))}
            </div>
          </motion.div>
        )}

        {phase === "parsing" && (
          <motion.div key="parsing" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="grid gap-6 md:grid-cols-[340px_1fr]" aria-busy="true">
            <div className="relative aspect-[4/3] overflow-hidden rounded-4xl bg-night">
              {photo && <img src={photo} alt={t("meal.photoAlt")} className="h-full w-full object-cover opacity-70" />}
              <motion.div className="absolute inset-x-0 h-16 bg-gradient-to-b from-transparent via-marigold/40 to-transparent" animate={{ top: ["-15%", "100%"] }} transition={{ duration: 1.6, repeat: Infinity, ease: "easeInOut" }} />
            </div>
            <div>
              <p className="flex items-center gap-2 text-lg font-semibold" role="status">
                <Loader2 size={20} className="animate-spin text-marigold-ink" aria-hidden />
                {t("meal.parsing")}
              </p>
              <div className="mt-5 flex flex-wrap gap-2">
                {[110, 140, 90, 160, 120].map((w, i) => (
                  <div key={i} className="skeleton h-11" style={{ width: w }} />
                ))}
              </div>
            </div>
          </motion.div>
        )}

        {phase === "edit" && parse && (
          <motion.div key="edit" data-meal-edit initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}>
            <div className="grid gap-6 md:grid-cols-[300px_1fr]">
              <div>
                {parse.source === "manual" ? (
                  <div className="flex aspect-[4/3] items-center justify-center rounded-4xl bg-paper-2 text-ink-3">
                    <PenLine size={40} aria-hidden />
                  </div>
                ) : (
                  <div className="aspect-[4/3] overflow-hidden rounded-4xl bg-night">{photo && <img src={photo} alt={t("meal.photoAlt")} className="h-full w-full object-cover" />}</div>
                )}
                <p className="mt-2 text-xs text-ink-3">{parse.source === "manual" ? t("meal.sourceManual") : parse.source === "live" ? t("meal.sourceLive") : t("meal.sourceFixture")}</p>
                {parse.source === "live" && (parse.recognition?.model ?? caps.visionModel) && (
                  <p className="mt-0.5 text-[0.7rem] text-ink-3">{t("meal.recognisedBy", { model: parse.recognition?.model ?? caps.visionModel })}</p>
                )}
                {credit && <p className="mt-0.5 text-[0.7rem] text-ink-3">{t("meal.photoCredit", { credit })}</p>}
              </div>
              <div>
                <h2 className="text-lg font-bold">{t("meal.detected")}</h2>
                <p className="text-sm text-ink-2">{t("meal.detectedHint")}</p>
                <ul className="mt-4 flex flex-wrap gap-2.5">
                  <AnimatePresence initial={false}>
                    {dishes.map((d) => (
                      <motion.li key={d.key} layout initial={{ opacity: 0, scale: 0.95 }} animate={{ opacity: 1, scale: 1 }} exit={{ opacity: 0, scale: 0.9 }}>
                        <div
                          className={`flex items-stretch overflow-hidden rounded-2xl border ${
                            d.needs_pick ? "border-dashed border-marigold-ink bg-marigold/10" : "border-line bg-card shadow-soft"
                          }`}
                        >
                          <button type="button" onClick={() => setPicker(d)} className="px-3.5 py-2 text-left hover:bg-paper-2">
                            <span className="block text-sm font-semibold">{d.needs_pick ? t("meal.needsPick") : d.name}</span>
                            <span className="num block text-xs text-ink-3">
                              {d.needs_pick ? d.detected : `${t("meal.units", { n: d.units, unit: shortUnit(d.unit) })} · ${t("meal.carbs", { n: Math.round(d.per.carbs * d.units) })}`}
                            </span>
                          </button>
                          {!d.needs_pick && (
                            <span className="flex items-center border-l border-line">
                              <button type="button" onClick={() => setUnits(d.key, -0.5)} className="h-full px-2.5 hover:bg-paper-2" aria-label={t("meal.less", { name: d.name })}>
                                <Minus size={15} aria-hidden />
                              </button>
                              <button type="button" onClick={() => setUnits(d.key, 0.5)} className="h-full px-2.5 hover:bg-paper-2" aria-label={t("meal.more", { name: d.name })}>
                                <Plus size={15} aria-hidden />
                              </button>
                            </span>
                          )}
                          <button type="button" onClick={() => remove(d.key)} className="border-l border-line px-2.5 text-ink-3 hover:bg-paper-2 hover:text-coral-ink" aria-label={t("meal.removeDish", { name: d.needs_pick ? d.detected : d.name })}>
                            <X size={15} aria-hidden />
                          </button>
                        </div>
                      </motion.li>
                    ))}
                  </AnimatePresence>
                </ul>
                {dishes.length === 0 && <p className="mt-2 text-sm text-ink-3">{t("meal.emptyManual")}</p>}
                <button type="button" className="btn-ghost mt-3 h-10 min-h-0 px-4 text-sm" onClick={addDish} data-meal-add>
                  <Plus size={15} aria-hidden />
                  {t("meal.addDish")}
                </button>

                <div className="mt-6 flex flex-wrap items-end gap-6">
                  <div>
                    <p className="eyebrow text-ink-3">{t("meal.total")}</p>
                    <p className="num mt-1 text-4xl font-extrabold">
                      {Math.round(totals.carbs)}
                      <span className="ml-1 text-lg font-semibold text-ink-2">g</span>
                      <span className="ml-2 text-base font-medium text-ink-3">{t("meal.plusMinus", { n: Math.round(carbsSd) })}</span>
                    </p>
                    <p className="mt-1 text-xs text-ink-3">{t("meal.nutritionNote")}</p>
                  </div>
                  <fieldset>
                    <legend className="eyebrow mb-2 text-ink-3">{t("meal.when")}</legend>
                    <div className="flex flex-wrap gap-1.5">
                      {[0, 15, 30, 60].map((m) => (
                        <button
                          key={m}
                          type="button"
                          aria-pressed={when === m}
                          onClick={() => setWhen(m)}
                          className={`chip ${when === m ? "border-ink bg-ink text-paper" : "border-line bg-card text-ink hover:bg-paper-2"}`}
                        >
                          {m === 0 ? t("meal.nowLabel") : t("meal.inMin", { n: m })}
                        </button>
                      ))}
                    </div>
                  </fieldset>
                </div>

                {unresolved && <p className="mt-4 text-sm font-semibold text-marigold-ink">{t("meal.fixFirst")}</p>}
                <button type="button" className="btn-primary mt-5 h-12 px-7 text-base" onClick={showCurve} disabled={unresolved || dishes.length === 0}>
                  {t("meal.showCurve")}
                  <ChevronRight size={18} aria-hidden />
                </button>
              </div>
            </div>

            {requested && (
              <div ref={resultRef} className="mt-10 scroll-mt-20">
                <section className="stage on-night rounded-4xl p-4 sm:p-6" aria-labelledby="meal-fc-title">
                  <div className="flex flex-wrap items-baseline justify-between gap-3">
                    <h2 id="meal-fc-title" className="text-xl font-bold text-moon">
                      {t("meal.forecastTitle")}
                    </h2>
                    {fc && (
                      <span className="text-sm text-marigold">
                        {t("stage.peakAt", { value: Math.round(fc.peak.value), time: formatReplayTime(t, fc.peak.t, s?.replay?.now ?? s?.now ?? fc.origin, i18n.language) })}
                      </span>
                    )}
                  </div>
                  <div className="mt-3">
                    {s && fc ? (
                      <GlucoseRiver state={s} rangeHours={6} overlay={fc} pending={forecast.isFetching} />
                    ) : forecast.isError ? (
                      <ErrorState tone="night" message={t("errors.generic")} onRetry={() => void forecast.refetch()} />
                    ) : (
                      <div className="skeleton-night h-[286px]" />
                    )}
                  </div>
                  <p className="mt-2 text-sm text-moon-2">{t("meal.forecastCaption")}</p>
                  {fc && s && (
                    <div className="mt-5 grid gap-3 sm:grid-cols-2">
                      <div className="stage-card p-4">
                        <div className="flex flex-wrap items-center justify-between gap-2">
                          <p className="text-sm text-moon-2">{t("risk.highTitle")}</p>
                          <EvidenceChip status="validated" tone="night" />
                        </div>
                        <p className="mt-1 text-xl font-bold text-coral-night">{freqText(t, fc.p_high.p)}</p>
                        <p className="num text-xs text-moon-3">
                          {t("risk.pctOf", { n: pct(fc.p_high.p) })} · {t("meal.without")}: {pct(s.forecast.p_high.p)}%
                        </p>
                        <div className="mt-1.5">
                          <ReliabilityLine prob={fc.p_high} />
                        </div>
                      </div>
                      <LowEvidencePanel prob={fc.p_low} />
                    </div>
                  )}
                  {fc && (
                    <div className="mt-4 flex flex-wrap items-center gap-3">
                      <button
                        type="button"
                        className="btn-marigold"
                        onClick={() => {
                          setStageDinner({ meal: requested, source: "meal", title: title || t("meal.title") });
                          navigate("/");
                        }}
                      >
                        {t("meal.toStage")}
                        <ChevronRight size={17} aria-hidden />
                      </button>
                      <span className="text-xs text-moon-3">{t("meal.toStageHint")}</span>
                    </div>
                  )}
                </section>

                <section className="mt-6" aria-labelledby="sug-title">
                  <h2 id="sug-title" className="text-lg font-bold">
                    {t("meal.suggestions")}
                  </h2>
                  <p className="text-sm text-ink-2">{t("meal.suggestionsHint")}</p>
                  <div className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                    {suggestions.map(({ key, label, scenario, icon: Icon }) => (
                      <button key={key} type="button" onClick={() => openWhatIf(scenario)} className="card flex items-center gap-3 p-4 text-left font-semibold transition hover:-translate-y-0.5 hover:shadow-lift">
                        <span className="inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-marigold/15 text-marigold-ink">
                          <Icon size={18} aria-hidden />
                        </span>
                        {label}
                      </button>
                    ))}
                  </div>
                </section>
              </div>
            )}
          </motion.div>
        )}
      </AnimatePresence>

      <DishPicker
        dish={picker}
        onClose={() => setPicker(null)}
        onPick={(f) => {
          if (picker) setDishes((ds) => ds.map((d) => (d.key === picker.key ? fromFood(d, f) : d)));
          setPicker(null);
        }}
      />
    </div>
  );
}

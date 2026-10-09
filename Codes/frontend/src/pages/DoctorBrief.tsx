import { Link, useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { ArrowLeft, FlaskConical, History, Lightbulb, Printer, Radar, TrendingUp } from "lucide-react";
import { useDoctorBrief } from "@/api/hooks";
import { AgpChart } from "@/charts/SmallCharts";
import { LabCard, OutlookCard } from "@/components/clinical";
import { Avatar, ErrorState, InfoTip, SyntheticBadge } from "@/components/ui";
import { formatDateTime, formatNumber, freqText, pct, signed } from "@/lib/format";
import { isEnglish } from "@/lib/langPrefs";
import { EvidenceChip, SimulationLabel } from "@/components/evidence";
import type { DoctorBrief } from "@/api/types";
import { driverFromLabel, driverLabel } from "@/lib/drivers";

function Kpi({ label, value, unit, info, tone }: { label: string; value: string; unit?: string; info?: string; tone?: string }) {
  return (
    <div className="rounded-3xl border border-line bg-card p-4 print:rounded-xl print:p-2">
      <p className="flex items-center gap-1 text-xs font-semibold text-ink-3">
        {label}
        {info && (
          <span className="no-print">
            <InfoTip label={info} />
          </span>
        )}
      </p>
      <p className={`num mt-1 text-3xl font-extrabold print:text-xl ${tone ?? ""}`}>
        {value}
        {unit && <span className="ml-1 text-sm font-semibold text-ink-3">{unit}</span>}
      </p>
    </div>
  );
}

/** The walk-after-dinner what-if the backend ran for this brief (suggestion_details), if any. */
function walkResult(b: DoctorBrief): { delta: number | null; lo: number | null; hi: number | null; dp: { mean: number; lo: number; hi: number } | null; small: boolean } | null {
  const cands: unknown[] = [...(b.suggestion_details ?? []), b.walk_what_if, b.walk_suggestion];
  for (const c of cands) {
    if (!c || typeof c !== "object") continue;
    const v = c as Record<string, unknown>;
    if (v.kind !== undefined && v.kind !== "walk_what_if") continue;
    const num = (x: unknown) => (typeof x === "number" && Number.isFinite(x) ? x : null);
    const dpk = v.delta_peak;
    const delta = num(dpk) ?? (dpk && typeof dpk === "object" ? num((dpk as { mean?: unknown }).mean) : null);
    const ci = (v.delta_peak_ci ?? (dpk && typeof dpk === "object" ? dpk : null)) as { lo?: unknown; hi?: unknown } | null;
    const dph = v.delta_p_high as { mean?: unknown; lo?: unknown; hi?: unknown } | undefined;
    const m = num(dph?.mean);
    const dp = m !== null ? { mean: m, lo: num(dph?.lo) ?? m, hi: num(dph?.hi) ?? m } : null;
    return { delta, lo: num(ci?.lo), hi: num(ci?.hi), dp, small: v.too_small_to_call === true };
  }
  return null;
}

/** Where an EHR value came from: the persona record or a confirmed lab upload (with its revision). */
function Prov({ f }: { f?: import("@/api/types").EhrProvenance }) {
  const { t, i18n } = useTranslation();
  if (!f) return null;
  const lab = /lab/i.test(f.source);
  return (
    <span className={`mt-0.5 block text-[0.68rem] font-normal ${lab ? "text-teal-ink" : "text-ink-3"}`}>
      {lab ? t("doctor.provLab") : t("doctor.provEhr")}
      {f.collection_date ? ` · ${formatDateTime(f.collection_date, i18n.language)}` : ""}
      {f.revision !== null && f.revision !== undefined ? ` · ${t("doctor.revision", { n: String(f.revision) })}` : ""}
    </span>
  );
}

export default function DoctorBriefPage() {
  const { pid } = useParams();
  const { t, i18n } = useTranslation();
  const q = useDoctorBrief(pid);
  const b = q.data;
  const p = b?.patient;
  return (
    <div className="print-compact mx-auto max-w-6xl px-4 py-8 sm:px-6 print:max-w-none print:p-0">
      <div className="no-print mb-5 flex items-center justify-between gap-3">
        <Link to="/doctor" className="btn-ghost h-10 min-h-0">
          <ArrowLeft size={16} aria-hidden />
          {t("doctor.back")}
        </Link>
        <button type="button" className="btn-primary h-10 min-h-0" onClick={() => window.print()} disabled={!b}>
          <Printer size={16} aria-hidden />
          {t("doctor.printBrief")}
        </button>
      </div>

      {q.isError && <ErrorState message={t("errors.generic")} onRetry={() => void q.refetch()} />}
      {q.isLoading && (
        <div className="space-y-4" aria-busy="true">
          <div className="skeleton h-24" />
          <div className="skeleton h-28" />
          <div className="skeleton h-56" />
        </div>
      )}

      {b && p && (
        <article aria-labelledby="brief-title">
          {/* Print cover line: product name and status on every printed brief. */}
          <div className="print-only mb-2 border-b border-line pb-1 text-[10px] text-ink-2">
            <span className="font-bold" lang="en">
              {t("app.name")}
            </span>{" "}
            · {t("app.descriptor")} · {t("print.notDevice")}
          </div>
          <header className="flex flex-wrap items-start justify-between gap-4 border-b border-line pb-5 print:pb-2">
            <div className="flex items-center gap-4">
              <span className="print:hidden">
                <Avatar initials={p.avatar_initials} size={56} />
              </span>
              <div>
                <p className="eyebrow text-ink-3">{t("doctor.brief")} · <span lang="en">{t("app.name")}</span></p>
                <h1 id="brief-title" className="text-2xl font-extrabold print:text-lg">
                  {p.name}
                </h1>
                <p className="text-sm text-ink-2">
                  <span className="num">{p.age}</span> · {p.sex === "F" ? t("common.female") : t("common.male")} · {p.city} · {p.occupation} · {t("doctor.diabetesYears", { n: p.ehr.diabetes_years })}
                </p>
              </div>
            </div>
            <div className="text-right text-xs text-ink-3">
              <SyntheticBadge note={p.source_note} />
              <p className="mt-1">{t("doctor.generated", { date: formatDateTime(b.generated_at, i18n.language) })}</p>
              <p>{t("doctor.calibrated", { n: p.calibration.cgm_days })}</p>
            </div>
          </header>

          {b.operational && (
            <section className="mt-5 rounded-3xl border border-teal-ink/30 bg-teal/5 p-4 print:mt-2 print:rounded-xl print:p-2" aria-labelledby="op-title">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <h2 id="op-title" className="flex items-center gap-2 font-bold">
                  <Radar size={17} className="text-teal-ink" aria-hidden />
                  {t("doctor.operationalTitle")}
                </h2>
                <span className="flex items-center gap-2 text-xs text-ink-3">
                  <EvidenceChip status="estimated" />
                  {(b.replay?.now ?? b.replay_now) && t("doctor.atReplay", { time: formatDateTime((b.replay?.now ?? b.replay_now) as string, i18n.language) })}
                </span>
              </div>
              <dl className="mt-2 grid grid-cols-2 gap-3 text-sm sm:grid-cols-4 print:gap-1">
                <div>
                  <dt className="text-xs text-ink-3">{t("doctor.colEstimate")}</dt>
                  <dd className="num font-bold">
                    {Math.round(b.operational.estimate)} {t("common.mgdl")}{" "}
                    <span className="text-xs font-normal text-ink-3">
                      ({Math.round(b.operational.band.lo)}–{Math.round(b.operational.band.hi)})
                    </span>
                  </dd>
                </div>
                <div>
                  <dt className="text-xs text-ink-3">{t("doctor.colHigh2h")}</dt>
                  <dd className="font-semibold">{b.operational.p_high_2h !== null && b.operational.p_high_2h !== undefined ? freqText(t, b.operational.p_high_2h) : "—"}</dd>
                </div>
                <div>
                  <dt className="text-xs text-ink-3">{t("doctor.colLastReading")}</dt>
                  <dd className="num font-semibold">{b.operational.last_reading_age_h === null ? t("freshness.never") : t("doctor.ageH", { n: formatNumber(b.operational.last_reading_age_h, i18n.language, 1) })}</dd>
                </div>
                <div>
                  <dt className="text-xs text-ink-3">{t("doctor.dataGap")}</dt>
                  <dd className={`font-semibold ${b.operational.data_gap ? "text-coral-ink" : ""}`}>{b.operational.data_gap ? t("doctor.yes") : t("doctor.no")}</dd>
                </div>
              </dl>
            </section>
          )}

          <h2 className="mt-5 flex flex-wrap items-center gap-2 text-sm font-bold print:mt-2">
            <History size={16} className="text-ink-3" aria-hidden />
            {t("doctor.historicalTitle")}
            <span className="rounded-full border border-line bg-paper-2 px-2 py-0.5 text-[0.7rem] font-semibold text-ink-2">{t("doctor.referenceChip")}</span>
          </h2>
          <div className="mt-2 grid grid-cols-2 gap-3 sm:grid-cols-6 print:mt-1 print:gap-2">
            <Kpi label={t("doctor.tarHistShort")} value={`${pct(b.tar_7d_reference?.value ?? p.risk_7d)}`} unit="%" info={b.tar_7d_reference?.label_en ?? t("doctor.historicalHint")} />
            <Kpi label={t("doctor.tir")} value={`${pct(b.tir_7d)}`} unit="%" info={t("glossary.tir")} tone={b.tir_7d >= 0.7 ? "text-teal-ink" : "text-marigold-ink"} />
            <Kpi label={t("doctor.meanGlucose")} value={`${Math.round(b.mean_glucose)}`} unit={t("common.mgdl")} />
            <Kpi label={t("doctor.gmi")} value={formatNumber(b.gmi, i18n.language, 1)} unit="%" info={t("glossary.gmi")} />
            <Kpi label={t("doctor.hypo")} value={`${b.hypo_events_7d}`} tone={b.hypo_events_7d ? "text-violet-ink" : ""} />
            <Kpi label={t("doctor.hyper")} value={`${b.hyper_events_7d}`} tone={b.hyper_events_7d ? "text-coral-ink" : ""} />
          </div>

          <section className="card mt-5 p-5 print:mt-2 print:p-3" aria-labelledby="agp-title">
            <h2 id="agp-title" className="flex flex-wrap items-center gap-2 font-bold">
              {t("doctor.profileTitle")}
              <span className="rounded-full border border-line bg-paper-2 px-2 py-0.5 text-[0.7rem] font-semibold text-ink-2">{t("doctor.referenceChip")}</span>
            </h2>
            <div className="print-agp mt-3">
              <AgpChart profile={b.daily_profile} />
            </div>
            <p className="mt-1 text-xs text-ink-3">{t("doctor.profileCaption")}</p>
          </section>

          <div className="mt-5 grid gap-5 md:grid-cols-2 print:mt-2 print:grid-cols-2 print:gap-2">
            <section className="card p-5 print:p-3">
              <h2 className="flex items-center gap-2 font-bold">
                <TrendingUp size={17} className="text-coral-ink" aria-hidden />
                {t("doctor.topDriver")}
              </h2>
              <p className="mt-1 text-lg font-semibold">{driverLabel(t, i18n, driverFromLabel(b.top_driver))}</p>
              <h2 className="mt-4 flex items-center gap-2 font-bold print:mt-2">
                <Lightbulb size={17} className="text-marigold-ink" aria-hidden />
                {t("doctor.suggestions")}
              </h2>
              {(() => {
                const wr = walkResult(b);
                if (!wr) return null;
                return (
                  <div className="mt-2 rounded-2xl border border-violet-ink/30 bg-violet/5 p-3 text-sm print:p-1.5">
                    <p className="flex flex-wrap items-center gap-2 font-semibold">
                      <FlaskConical size={15} className="text-violet-ink" aria-hidden />
                      {t("doctor.walkTitle")}
                      <span className="no-print">
                        <SimulationLabel tone="paper" />
                      </span>
                    </p>
                    {wr.small ? (
                      <p className="mt-1">{t("doctor.walkTooSmall")}</p>
                    ) : (
                      <p className="num mt-1">
                        {wr.delta !== null && t("doctor.walkPeak", { d: signed(wr.delta) })}
                        {wr.lo !== null && wr.hi !== null && ` (${signed(wr.lo)} … ${signed(wr.hi)})`}
                        {wr.dp && ` · ${t("doctor.walkRisk", { d: Math.round(wr.dp.mean * 100), lo: Math.round(wr.dp.lo * 100), hi: Math.round(wr.dp.hi * 100) })}`}
                      </p>
                    )}
                  </div>
                );
              })()}
              <ul className="mt-2 space-y-1.5" lang={isEnglish(i18n.language) ? undefined : "en"}>
                {b.suggestions.map((s, i) => (
                  <li key={i} className="flex gap-2 text-sm leading-relaxed">
                    <span className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-marigold-ink" aria-hidden />
                    {s}
                  </li>
                ))}
              </ul>
            </section>
            <section className="card p-5 print:p-3">
              <h2 className="font-bold">{t("doctor.record")}</h2>
              <dl className="mt-2 grid grid-cols-2 gap-x-4 gap-y-2 text-sm">
                <dt className="text-ink-3">{t("doctor.hba1c")}</dt>
                <dd className="num font-semibold">
                  {formatNumber(Number(p.ehr.provenance?.hba1c?.value ?? p.hba1c), i18n.language, 1)}%
                  <Prov f={p.ehr.provenance?.hba1c} />
                </dd>
                <dt className="text-ink-3">{t("doctor.bmi")}</dt>
                <dd className="num font-semibold">
                  {formatNumber(Number(p.ehr.provenance?.bmi?.value ?? p.ehr.bmi), i18n.language, 1)}
                  <Prov f={p.ehr.provenance?.bmi} />
                </dd>
                {p.ehr.fasting_glucose !== undefined && (
                  <>
                    <dt className="text-ink-3">{t("doctor.fasting")}</dt>
                    <dd className="num font-semibold">
                      {p.ehr.fasting_glucose} {t("common.mgdl")}
                    </dd>
                  </>
                )}
                {p.ehr.ldl !== undefined && (
                  <>
                    <dt className="text-ink-3">{t("doctor.ldl")}</dt>
                    <dd className="num font-semibold">
                      {p.ehr.ldl} {t("common.mgdl")}
                    </dd>
                  </>
                )}
                {p.ehr.egfr !== undefined && (
                  <>
                    <dt className="text-ink-3">{t("doctor.egfr")}</dt>
                    <dd className="num font-semibold">{p.ehr.egfr}</dd>
                  </>
                )}
              </dl>
              {(p.ehr.revisions?.length ?? 0) > 0 && <p className="mt-2 text-xs text-ink-3">{t("doctor.revisions", { n: p.ehr.revisions!.length })}</p>}
              <p className="mt-3 text-xs font-semibold uppercase tracking-wide text-ink-3">{t("doctor.medications")}</p>
              <p className="text-sm" lang="en">
                {p.ehr.medications.join(" · ") || "—"}
              </p>
              <p className="mt-2 text-xs font-semibold uppercase tracking-wide text-ink-3">{t("doctor.conditions")}</p>
              <p className="text-sm" lang="en">
                {p.ehr.conditions.join(" · ") || "—"}
              </p>
            </section>
          </div>
          <p className="mt-3 text-xs text-ink-3">{t("doctor.patientNote")}</p>

          <div className="no-print mt-8 grid gap-5 lg:grid-cols-2">
            <OutlookCard patientId={p.id} />
            <LabCard patientId={p.id} />
          </div>
        </article>
      )}
    </div>
  );
}

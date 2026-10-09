import { useState } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Activity, AlertTriangle, CheckCircle2, ChevronRight, CloudOff, Flag, Loader2, Monitor } from "lucide-react";
import type { PatientSummary, QueueItem, QueueReasonKind, ReviewStatus } from "@/api/types";
import { useDoctorPanel, useDoctorQueue, useDoctorReview } from "@/api/hooks";
import { Sparkline } from "@/charts/SmallCharts";
import { Avatar, ErrorState, InfoTip, PageHeader, SyntheticBadge } from "@/components/ui";
import { EvidenceChip } from "@/components/evidence";
import { formatDateTime, freqText, pct, fixed } from "@/lib/format";
import { toast } from "@/store/toast";
import { isEnglish } from "@/lib/langPrefs";

const REASON_ICON: Record<QueueReasonKind, typeof Activity> = { missing_data: CloudOff, concerning_observation: AlertTriangle, model_risk: Activity };
const REASON_TONE: Record<QueueReasonKind, string> = {
  missing_data: "border-ink-3/40 bg-paper-2 text-ink-2",
  concerning_observation: "border-coral-ink/50 bg-coral/10 text-coral-ink",
  model_risk: "border-marigold-ink/40 bg-marigold/10 text-marigold-ink",
};

/** Freshness of a queue row in hours, tolerant of the shapes a backend may send. */
function freshnessText(t: (k: string, o?: Record<string, unknown>) => string, f: QueueItem["freshness"]): string {
  if (f === null || f === undefined) return "—";
  if (typeof f === "number") return t("doctor.ageH", { n: fixed(f, 1) });
  if (typeof f === "string") return t(`freshness.${f}`, { defaultValue: f });
  const h = f.hours_since_reading;
  const label = f.label ? t(`freshness.${f.label}`, { defaultValue: f.label }) : "";
  return [label, typeof h === "number" && Number.isFinite(h) ? (h >= 24 ? t("freshness.never") : t("doctor.ageH", { n: fixed(h, 1) })) : ""].filter(Boolean).join(" · ");
}

function ReviewControls({ item }: { item: QueueItem }) {
  const { t, i18n } = useTranslation();
  const m = useDoctorReview();
  const [note, setNote] = useState(item.review.note ?? "");
  const save = async (status: ReviewStatus) => {
    try {
      await m.mutateAsync({ pid: item.pid, status, note });
      toast(t("queue.saved"), "success");
    } catch {
      toast(t("errors.generic"), "error");
    }
  };
  const id = `note-${item.pid}`;
  return (
    <div className="mt-3 border-t border-line pt-3">
      <label htmlFor={id} className="text-xs font-semibold text-ink-3">
        {t("queue.note")}
      </label>
      <textarea id={id} rows={2} value={note} onChange={(e) => setNote(e.target.value)} className="field mt-1 py-2 text-sm" placeholder={t("queue.notePlaceholder")} />
      <div className="mt-2 flex flex-wrap items-center gap-2">
        <button type="button" className="btn-primary h-9 min-h-0 px-3.5 text-xs" disabled={m.isPending} onClick={() => void save("reviewed")}>
          {m.isPending ? <Loader2 size={14} className="animate-spin" aria-hidden /> : <CheckCircle2 size={14} aria-hidden />}
          {t("queue.markReviewed")}
        </button>
        <button type="button" className="btn-ghost h-9 min-h-0 px-3.5 text-xs" disabled={m.isPending} onClick={() => void save("follow_up")}>
          <Flag size={14} aria-hidden />
          {t("queue.markFollowUp")}
        </button>
        {item.review.at && (
          <span className="text-xs text-ink-3">
            {t("queue.lastReview", { by: item.review.by ?? "—", at: formatDateTime(item.review.at, i18n.language) })}
          </span>
        )}
      </div>
    </div>
  );
}

function QueueCard({ item, summary }: { item: QueueItem; summary?: PatientSummary }) {
  const { t, i18n } = useTranslation();
  const [open, setOpen] = useState(false);
  const op = item.operational ?? summary?.operational;
  const status = item.review?.status ?? "unreviewed";
  const statusTone = status === "reviewed" ? "bg-teal/15 text-teal-ink" : status === "follow_up" ? "bg-coral/15 text-coral-ink" : "bg-paper-2 text-ink-2";
  return (
    <li className="card flex min-w-0 flex-col p-4">
      <div className="flex items-start justify-between gap-2">
        <div className="flex min-w-0 items-center gap-3">
          <Avatar initials={summary?.avatar_initials ?? item.name.slice(0, 2).toUpperCase()} size={38} />
          <div className="min-w-0">
            <Link to={`/doctor/${encodeURIComponent(item.pid)}`} className="block truncate font-bold hover:underline">
              {item.name}
            </Link>
            <p className="text-xs text-ink-3">{freshnessText(t, item.freshness)}</p>
          </div>
        </div>
        <span className={`shrink-0 rounded-full px-2.5 py-1 text-xs font-bold ${statusTone}`}>{t(`queue.status.${status}`)}</span>
      </div>
      <ul className="mt-3 flex flex-col gap-1.5">
        {item.reasons.length === 0 && <li className="text-sm text-ink-3">{t("queue.noReasons")}</li>}
        {item.reasons.map((r, i) => {
          const Icon = REASON_ICON[r.kind] ?? Activity;
          return (
            <li key={i} className={`flex items-start gap-2 rounded-2xl border px-3 py-2 text-sm ${REASON_TONE[r.kind] ?? REASON_TONE.missing_data}`}>
              <Icon size={15} className="mt-0.5 shrink-0" aria-hidden />
              <span>
                <span className="font-bold">{t(`queue.reason.${r.kind}`, { defaultValue: r.kind })}</span>
                <span className="block text-xs opacity-90" lang={isEnglish(i18n.language) ? undefined : "en"}>
                  {r.detail_en}
                </span>
              </span>
            </li>
          );
        })}
      </ul>
      {op && (
        <p className="mt-3 text-xs text-ink-2">
          <span className="font-semibold">{t("doctor.nowOperational")}:</span>{" "}
          <span className="num">
            {Math.round(op.estimate)} {t("common.mgdl")} ({Math.round(op.band.lo)}–{Math.round(op.band.hi)})
          </span>
          {op.p_high_2h !== null && op.p_high_2h !== undefined && <> · {t("doctor.highRiskShort", { text: freqText(t, op.p_high_2h) })}</>}
        </p>
      )}
      {item.review?.note && !open && <p className="mt-2 rounded-xl bg-paper-2 px-3 py-1.5 text-xs text-ink-2">“{item.review.note}”</p>}
      <button type="button" aria-expanded={open} onClick={() => setOpen((o) => !o)} className="mt-3 self-start text-sm font-semibold text-marigold-ink underline underline-offset-4">
        {open ? t("common.hideDetails") : t("queue.review")}
      </button>
      {open && <ReviewControls item={item} />}
    </li>
  );
}

function RiskBar({ value }: { value: number }) {
  const v = Math.max(0, Math.min(1, value));
  const tone = v >= 0.35 ? "bg-coral" : v >= 0.2 ? "bg-marigold" : "bg-teal";
  return (
    <span className="flex items-center gap-2.5">
      <span className="h-2 w-20 overflow-hidden rounded-full bg-paper-2" aria-hidden>
        <span className={`block h-full rounded-full ${tone}`} style={{ width: `${v * 100}%` }} />
      </span>
      <span className="num font-bold">{pct(v)}%</span>
    </span>
  );
}

export default function DoctorPanelPage() {
  const { t } = useTranslation();
  const q = useDoctorPanel();
  const queue = useDoctorQueue();
  const rows = (q.data ?? []).slice().sort((a, b) => (b.tar_7d_reference?.value ?? b.risk_7d) - (a.tar_7d_reference?.value ?? a.risk_7d));
  const byId = new Map((q.data ?? []).map((p) => [p.id, p]));
  const order: Record<ReviewStatus, number> = { follow_up: 0, unreviewed: 1, reviewed: 2 };
  const items = (queue.data ?? []).slice().sort((a, b) => order[a.review?.status ?? "unreviewed"] - order[b.review?.status ?? "unreviewed"] || b.reasons.length - a.reasons.length);
  return (
    <div className="mx-auto max-w-7xl px-4 py-8 sm:px-6">
      <PageHeader title={t("doctor.title")} subtitle={t("doctor.panelIntro")} />
      <p className="mb-4 flex items-center gap-2 rounded-2xl bg-paper-2 px-4 py-2.5 text-sm text-ink-2 lg:hidden">
        <Monitor size={16} aria-hidden />
        {t("doctor.desktopHint")}
      </p>

      <section aria-labelledby="queue-title" className="mb-8">
        <div className="mb-3 flex flex-wrap items-end justify-between gap-2">
          <div>
            <h2 id="queue-title" className="text-lg font-bold">
              {t("queue.title")}
            </h2>
            <p className="text-sm text-ink-2">{t("queue.subtitle")}</p>
          </div>
          <div className="flex flex-wrap gap-1.5 text-xs">
            {(["missing_data", "concerning_observation", "model_risk"] as const).map((k) => {
              const Icon = REASON_ICON[k];
              return (
                <InfoTip key={k} label={t(`queue.reasonHint.${k}`)}>
                  <span className={`inline-flex items-center gap-1 rounded-full border px-2.5 py-1 font-semibold ${REASON_TONE[k]}`}>
                    <Icon size={12} aria-hidden />
                    {t(`queue.reason.${k}`)}
                  </span>
                </InfoTip>
              );
            })}
          </div>
        </div>
        {queue.isError ? (
          <ErrorState message={t("queue.unavailable")} onRetry={() => void queue.refetch()} />
        ) : (
          <ul className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
            {queue.isLoading && [0, 1, 2].map((i) => <li key={i} className="skeleton h-48" />)}
            {items.map((it) => (
              <QueueCard key={it.pid} item={it} summary={byId.get(it.pid)} />
            ))}
          </ul>
        )}
      </section>

      <section aria-labelledby="panel-title">
        <h2 id="panel-title" className="mb-1 text-lg font-bold">
          {t("doctor.panelTitle")}
        </h2>
        <p className="mb-3 text-sm text-ink-2">{t("doctor.panelSubtitle")}</p>
        {q.isError && <ErrorState message={t("errors.network")} onRetry={() => void q.refetch()} />}
        <ul className="grid grid-cols-1 gap-3 md:hidden">
          {q.isLoading && [0, 1, 2].map((i) => <li key={i} className="skeleton h-28" />)}
          {rows.map((p) => (
            <li key={p.id} className="min-w-0">
              <Link to={`/doctor/${encodeURIComponent(p.id)}`} className="card flex min-w-0 flex-col gap-3 p-4">
                <span className="flex items-center gap-3">
                  <Avatar initials={p.avatar_initials} size={38} />
                  <span className="min-w-0 flex-1">
                    <span className="block break-words font-bold">{p.name}</span>
                    <span className="block break-words text-xs text-ink-3">
                      <span className="num">{p.age}</span> · {p.city}
                    </span>
                  </span>
                  <ChevronRight size={18} className="shrink-0 text-ink-3" aria-hidden />
                </span>
                {p.operational && (
                  <span className="text-sm">
                    <span className="block text-xs text-ink-3">{t("doctor.nowOperational")}</span>
                    <span className="num font-semibold">
                      {Math.round(p.operational.estimate)} ({Math.round(p.operational.band.lo)}–{Math.round(p.operational.band.hi)})
                    </span>
                  </span>
                )}
                <span className="flex min-w-0 flex-wrap items-center justify-between gap-3 text-sm">
                  <span className="min-w-0 break-words">
                    <span className="block text-xs text-ink-3">{t("doctor.tarHistShort")}</span>
                    <RiskBar value={p.tar_7d_reference?.value ?? p.risk_7d} />
                  </span>
                  <Sparkline values={p.sparkline} width={110} />
                </span>
              </Link>
            </li>
          ))}
        </ul>
        <div className="card hidden overflow-hidden md:block">
          <div className="relative overflow-x-auto">
            <table className="w-full min-w-[920px] border-separate border-spacing-0 text-sm">
              <thead>
                <tr className="text-left text-xs font-semibold text-ink-3">
                  <th scope="col" className="border-b border-line px-5 py-3">
                    {t("doctor.patient")}
                  </th>
                  <th scope="col" className="border-b border-line bg-teal/5 px-3 py-3" colSpan={3}>
                    <span className="inline-flex items-center gap-1.5">
                      {t("doctor.groupOperational")}
                      <EvidenceChip status="estimated" />
                    </span>
                  </th>
                  <th scope="col" className="border-b border-line bg-paper-2/70 px-3 py-3" colSpan={3}>
                    <span className="inline-flex items-center gap-1.5">
                      {t("doctor.groupHistorical")}
                      <InfoTip label={t("doctor.historicalHint")} />
                    </span>
                  </th>
                  <th scope="col" className="border-b border-line px-3 py-3">
                    <span className="sr-only">{t("doctor.open")}</span>
                  </th>
                </tr>
                <tr className="text-left text-xs font-semibold text-ink-3">
                  <th scope="col" className="border-b border-line px-5 py-2" />
                  <th scope="col" className="border-b border-line bg-teal/5 px-3 py-2">{t("doctor.colEstimate")}</th>
                  <th scope="col" className="border-b border-line bg-teal/5 px-3 py-2">{t("doctor.colHigh2h")}</th>
                  <th scope="col" className="border-b border-line bg-teal/5 px-3 py-2">{t("doctor.colLastReading")}</th>
                  <th scope="col" className="border-b border-line bg-paper-2/70 px-3 py-2">{t("doctor.tarHistShort")}</th>
                  <th scope="col" className="border-b border-line bg-paper-2/70 px-3 py-2">
                    <span className="inline-flex items-center gap-1">
                      {t("doctor.tirHistShort")}
                      <InfoTip label={t("glossary.tir")} />
                    </span>
                  </th>
                  <th scope="col" className="border-b border-line bg-paper-2/70 px-3 py-2">{t("doctor.trend")}</th>
                  <th scope="col" className="border-b border-line px-3 py-2" />
                </tr>
              </thead>
              <tbody>
                {q.isLoading &&
                  [0, 1, 2].map((i) => (
                    <tr key={i}>
                      <td colSpan={8} className="px-5 py-3">
                        <div className="skeleton h-12" />
                      </td>
                    </tr>
                  ))}
                {rows.map((p) => {
                  const op = p.operational;
                  return (
                    <tr key={p.id} className="group hover:bg-paper-2/60">
                      <td className="border-b border-line/70 px-5 py-4">
                        <span className="flex items-center gap-3">
                          <Avatar initials={p.avatar_initials} size={40} />
                          <span>
                            <Link to={`/doctor/${encodeURIComponent(p.id)}`} className="font-bold hover:underline">
                              {p.name}
                            </Link>
                            <span className="block text-xs text-ink-3">
                              <span className="num">{p.age}</span> · {p.sex === "F" ? t("common.female") : t("common.male")} · {p.city} · HbA1c <span className="num">{fixed(p.hba1c, 1)}%</span>
                            </span>
                            <span className="mt-1 block">
                              <SyntheticBadge note={p.source_note} />
                            </span>
                          </span>
                        </span>
                      </td>
                      <td className="num border-b border-line/70 bg-teal/5 px-3 py-4">
                        {op ? (
                          <>
                            <span className="font-bold">{Math.round(op.estimate)}</span>{" "}
                            <span className="text-xs text-ink-3">
                              ({Math.round(op.band.lo)}–{Math.round(op.band.hi)})
                            </span>
                          </>
                        ) : (
                          "—"
                        )}
                      </td>
                      <td className="border-b border-line/70 bg-teal/5 px-3 py-4 text-xs">{op?.p_high_2h !== null && op?.p_high_2h !== undefined ? freqText(t, op.p_high_2h) : "—"}</td>
                      <td className="border-b border-line/70 bg-teal/5 px-3 py-4 text-xs">
                        {op ? (
                          <>
                            {op.last_reading_age_h === null ? t("freshness.never") : t("doctor.ageH", { n: fixed(op.last_reading_age_h, 1) })}
                            {op.data_gap && <span className="ml-1.5 rounded-full bg-coral/15 px-2 py-0.5 font-bold text-coral-ink">{t("doctor.dataGap")}</span>}
                          </>
                        ) : (
                          "—"
                        )}
                      </td>
                      <td className="border-b border-line/70 bg-paper-2/40 px-3 py-4">
                        <RiskBar value={p.tar_7d_reference?.value ?? p.risk_7d} />
                      </td>
                      <td className="num border-b border-line/70 bg-paper-2/40 px-3 py-4 font-semibold">{pct(p.tir_7d)}%</td>
                      <td className="border-b border-line/70 bg-paper-2/40 px-3 py-4">
                        <Sparkline values={p.sparkline} />
                      </td>
                      <td className="border-b border-line/70 px-3 py-4 text-right">
                        <Link to={`/doctor/${encodeURIComponent(p.id)}`} className="btn-ghost h-10 min-h-0 px-3.5" aria-label={`${t("doctor.open")}: ${p.name}`}>
                          {t("doctor.open")}
                          <ChevronRight size={16} aria-hidden />
                        </Link>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
        <p className="mt-2 text-xs text-ink-3">{t("doctor.historicalHint")}</p>
      </section>
    </div>
  );
}

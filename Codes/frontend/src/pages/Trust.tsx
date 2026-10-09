import { useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { m as motion } from "framer-motion";
import { AlertTriangle, CircleSlash, CloudOff, Database, ExternalLink, Flag, Scale, ShieldCheck, TriangleAlert } from "lucide-react";
import { useReport, useReportsList } from "@/api/hooks";
import { ForestPlot, MultiLine, RAMP, RefBars, Reliability, ZoneStack } from "@/charts/TrustCharts";
import { InfoTip, PageHeader } from "@/components/ui";
import { formatDateTime, fixed } from "@/lib/format";
import { humanizeKey, isObj } from "@/lib/reports";
import {
  agentMultilingual,
  baselines as readBaselines,
  calibrationLength,
  errorGrid,
  HORIZONS,
  hoursSinceReading,
  ladderLevels,
  ML_LOWER_BETTER,
  ML_METRICS,
  nbp as readNbp,
  recentPrick,
  reliability,
  subgroups as readSubgroups,
  textOf,
  transfer as readTransfer,
  type Frac,
  type HoursBin,
  type Metrics,
  counts as readCounts,
  exploratoryHorizons,
  pairedBaselines,
  pairedWidth,
  protocolChange,
  consolidateLimitations,
} from "@/lib/trust";
import { isEnglish } from "@/lib/langPrefs";
import { formatInt } from "@/lib/format";
import { EvidenceChip } from "@/components/evidence";
import { useAuth } from "@/store/auth";

/* ---------------- formatting (numbers always come from the reports) ---------------- */
const mg = (v: number | null | undefined) => (v === null || v === undefined || !Number.isFinite(v) ? "—" : fixed(v, 1));
const pc = (v: number | null | undefined, d = 0) => (v === null || v === undefined || !Number.isFinite(v) ? "—" : `${fixed((v * 100), d)}%`);
const f2 = (v: number | null | undefined) => (v === null || v === undefined || !Number.isFinite(v) ? "—" : fixed(v, 2));
const signedMg = (v: number) => `${v > 0 ? "+" : v < 0 ? "−" : ""}${fixed(Math.abs(v), 1)}`;
const ciText = (c: { lo: number; hi: number } | null | undefined, f: (v: number) => string) => (c ? `${f(c.lo)}–${f(c.hi)}` : "");

const LADDER_KEY: Record<string, string> = { full: "ladder.full", "4": "ladder.p4", "2": "ladder.p2", "1": "ladder.p1", "0": "ladder.none" };
const DEFAULT_LEVEL = "2";
/** "fixed (07:00 & 22:00)" -> "fixed", "twin-recommended" -> "twin_recommended". */
const armKey = (name: string) => name.split(/[\s(]/)[0].toLowerCase().replace(/[^a-z]/g, "_");

/* ---------------- building blocks ---------------- */
function NotGenerated({ note }: { note?: string }) {
  const { t } = useTranslation();
  return (
    <p className="flex items-center gap-2 rounded-2xl bg-paper-2 px-4 py-3 text-sm text-ink-3">
      <CircleSlash size={16} aria-hidden />
      {note ?? t("common.notGenerated")}
    </p>
  );
}

function RawReport({ data }: { data: unknown }) {
  const { t } = useTranslation();
  if (data === null || data === undefined) return null;
  return (
    <details className="no-print mt-4 text-sm">
      <summary className="cursor-pointer font-semibold text-ink-3 hover:text-ink">{t("trust.raw")}</summary>
      <pre className="mt-2 max-h-64 overflow-auto rounded-2xl bg-paper-2 p-3 text-xs text-ink-2" lang="en">
        {JSON.stringify(data, null, 2)}
      </pre>
    </details>
  );
}

function TrustCard({
  id,
  title,
  caption,
  info,
  children,
  wide,
  loading,
  raw,
  action,
  tone,
}: {
  id?: string;
  title: string;
  caption?: string;
  info?: string;
  children: ReactNode;
  wide?: boolean;
  loading?: boolean;
  raw?: unknown;
  action?: ReactNode;
  tone?: "warn";
}) {
  return (
    <motion.section
      id={id}
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.45 }}
      className={`card min-w-0 scroll-mt-24 p-5 sm:p-6 ${wide ? "lg:col-span-2" : ""} ${tone === "warn" ? "border-marigold-ink/40" : ""}`}
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <h2 className="flex min-w-0 items-center gap-1 break-words text-lg font-bold">
          {title}
          {info && <InfoTip label={info} />}
        </h2>
        {action}
      </div>
      {caption && <p className="mb-4 mt-1 max-w-3xl text-sm leading-relaxed text-ink-2">{caption}</p>}
      {loading ? <div className="skeleton h-48" aria-busy="true" /> : children}
      <RawReport data={raw} />
    </motion.section>
  );
}

function Segmented<T extends string | number>({ value, options, onChange, label }: { value: T; options: { v: T; label: string }[]; onChange: (v: T) => void; label: string }) {
  return (
    <div role="radiogroup" aria-label={label} className="flex flex-wrap rounded-full bg-paper-2 p-1 text-xs font-semibold">
      {options.map((o) => (
        <button
          key={String(o.v)}
          type="button"
          role="radio"
          aria-checked={value === o.v}
          onClick={() => onChange(o.v)}
          className={`min-h-[32px] whitespace-nowrap rounded-full px-3 ${value === o.v ? "bg-card text-ink shadow-soft" : "text-ink-2 hover:text-ink"}`}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

function Table({ head, rows, minW = 520, caption }: { head: ReactNode[]; rows: { key: string; cells: ReactNode[]; tone?: "flag" | "strong" }[]; minW?: number; caption?: string }) {
  return (
    <div className="relative -mx-1 max-w-full overflow-x-auto">
      <table className="w-full border-separate border-spacing-0 text-sm" style={{ minWidth: minW }}>
        {caption && <caption className="sr-only">{caption}</caption>}
        <thead>
          <tr>
            {head.map((h, i) => (
              <th key={i} scope="col" className={`border-b border-line px-2 py-2 text-left align-bottom text-[0.7rem] font-semibold uppercase leading-tight tracking-wide text-ink-3 ${i ? "text-right" : ""}`}>
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.key} className={r.tone === "flag" ? "bg-coral/10" : r.tone === "strong" ? "bg-marigold/10" : ""}>
              {r.cells.map((c, j) => (
                <td key={j} className={`border-b border-line/70 px-2 py-2.5 ${j === 0 ? "font-semibold" : "num text-right"}`}>
                  {c}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function WithCi({ v, c, f = mg }: { v: number | null; c?: { lo: number; hi: number } | null; f?: (v: number) => string }) {
  return (
    <span className="whitespace-nowrap">
      {v === null ? "—" : f(v)}
      {c && <span className="ml-1 text-xs font-normal text-ink-3">({`${f(c.lo)}, ${f(c.hi)}`})</span>}
    </span>
  );
}

function Tile({ value, unit, label, sub }: { value: string; unit?: string; label: string; sub?: string }) {
  return (
    <div className="rounded-3xl bg-night-2/70 p-4 ring-1 ring-night-line/60">
      <p className="num text-3xl font-extrabold text-moon">
        {value}
        {unit && <span className="ml-1 text-sm font-semibold text-moon-2">{unit}</span>}
      </p>
      <p className="mt-1 text-sm leading-snug text-moon-2">{label}</p>
      {sub && <p className="mt-1 text-xs text-moon-3">{sub}</p>}
    </div>
  );
}

/* ---------------- page ---------------- */
export default function TrustPage() {
  const { t, i18n } = useTranslation();
  const lang = i18n.language;
  const mock = useAuth((s) => s.mock);
  const list = useReportsList();
  const summary = useReport("summary");
  const ladder = useReport("sensor_ladder");
  const calLen = useReport("calibration_length");
  const baseQ = useReport("baselines");
  const nbpQ = useReport("nbp_value");
  const transferQ = useReport("transfer");
  const subQ = useReport("subgroups");
  const calCurve = useReport("calibration_curve");
  const grid = useReport("error_grid");
  // Optional report: only fetched once the report list includes it.
  const listed = (n: string) => list.isError || !!list.data?.some((x) => x.name === n);
  const agentQ = useReport("agent_multilingual", listed("agent_multilingual"));

  const [covH, setCovH] = useState<number>(60);
  const [relLevel, setRelLevel] = useState<string>(DEFAULT_LEVEL);
  const [baseMetric, setBaseMetric] = useState<"rmse30" | "rmse60" | "rmse120" | "auroc">("rmse60");
  const [gridKind, setGridKind] = useState<"forecast" | "virtual">("forecast");

  const levelName = (l: string, fallback?: string) => (LADDER_KEY[l] ? t(LADDER_KEY[l]) : (fallback ?? l));
  const levels = ladderLevels(ladder.data, summary.data);
  const lv2 = levels.find((l) => l.level === DEFAULT_LEVEL) ?? levels[0];
  const rel = reliability(calCurve.data);
  const relCur = rel.find((r) => r.level === relLevel) ?? rel[0];
  const base = readBaselines(baseQ.data);
  const nbp = readNbp(nbpQ.data);
  const tr = readTransfer(transferQ.data);
  const sub = readSubgroups(subQ.data);
  const eg = errorGrid(grid.data);
  const cl = calibrationLength(calLen.data);
  const ml = agentMultilingual(agentQ.data);
  const rp = recentPrick(ladder.data);
  const hs = hoursSinceReading(ladder.data);
  const pw = pairedWidth(ladder.data);
  const ex = exploratoryHorizons(ladder.data, summary.data);
  const pchg = protocolChange(summary.data);
  const pbase = pairedBaselines(baseQ.data);
  const sumCounts = readCounts(summary.data);
  const evalProtocol = textOf(summary.data, "evaluation_protocol");
  const [exLevel, setExLevel] = useState<string>(DEFAULT_LEVEL);
  const hoursLabel = (b: HoursBin) =>
    b.lo !== null && b.hi !== null ? t("trust.hoursRange", { lo: b.lo, hi: b.hi }) : b.lo !== null ? t("trust.hoursOpen", { lo: b.lo }) : b.key;
  const msText = (v: number | null) => (v === null ? "—" : v < 1000 ? t("trust.ms", { n: Math.round(v) }) : t("trust.seconds", { n: fixed(v / 1000, 1) }));
  const fracText = (f: Frac) => `${formatInt(f.k, lang)} / ${formatInt(f.n, lang)}`;

  const dataset = textOf(summary.data, "dataset") ?? textOf(ladder.data, "dataset");
  const nEval = isObj(summary.data) && typeof summary.data.n_patients_eval === "number" ? summary.data.n_patients_eval : (lv2?.nPatients ?? null);
  const generated = textOf(summary.data, "generated_at") ?? list.data?.find((x) => x.name === "summary")?.generated_at ?? null;
  // One consolidated list: each qualification once, grouped by the report it comes from.
  const limitGroups = consolidateLimitations(summary.data, agentQ.data);
  const nothing = !summary.isLoading && !ladder.isLoading && !summary.data && !ladder.data && !baseQ.data;

  /* ----- baselines metric ----- */
  const baseVal = (m: Metrics | null) =>
    !m ? null : baseMetric === "auroc" ? m.aurocHigh : (m.rmse.find((p) => p.h === Number(baseMetric.replace("rmse", "")))?.v ?? null);
  const baseBest = (level: string) => {
    const vals = base.methods.map((m) => baseVal(base.cell(m, level))).filter((v): v is number => v !== null);
    if (!vals.length) return null;
    return baseMetric === "auroc" ? Math.max(...vals) : Math.min(...vals);
  };

  const nbpNull = nbp.diffs.length > 0 && nbp.diffs.every((d) => d.lo <= 0 && d.hi >= 0);
  const enOnly = isEnglish(lang) ? undefined : "en";

  return (
    <div className="mx-auto max-w-7xl px-4 py-8 sm:px-6">
      <PageHeader title={t("trust.title")} subtitle={t("trust.subtitle")} />

      {mock && (
        <div role="note" className="mb-6 flex items-start gap-3 rounded-3xl border border-line bg-card p-4 text-sm">
          <CloudOff size={20} className="mt-0.5 shrink-0 text-ink-3" aria-hidden />
          {t("trust.mockNote")}
        </div>
      )}
      {!mock && nothing && (
        <div role="note" className="mb-6 flex items-start gap-3 rounded-3xl border border-line bg-card p-4 text-sm">
          <AlertTriangle size={20} className="mt-0.5 shrink-0 text-ink-3" aria-hidden />
          {t("trust.reportsMissing")}
        </div>
      )}

      {/* ---------------- headline ---------------- */}
      <section className="stage on-night mb-6 rounded-4xl p-5 sm:p-7" aria-label={t("trust.headline")}>
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <p className="eyebrow text-moon-3">{t("trust.headline")}</p>
            <p className="mt-1 flex items-start gap-2 break-words text-lg font-bold text-moon">
              <ShieldCheck size={20} className="mt-1 shrink-0 text-teal" aria-hidden />
              {dataset ? t("trust.dataset", { name: dataset }) : t("common.notGenerated")}
            </p>
          </div>
          <p className="text-sm text-moon-3">{generated ? t("trust.generated", { date: formatDateTime(generated, lang) }) : ""}</p>
        </div>
        {summary.isLoading && ladder.isLoading ? (
          <div className="mt-5 grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
            {[0, 1, 2, 3].map((i) => (
              <div key={i} className="skeleton-night h-24" />
            ))}
          </div>
        ) : lv2 ? (
          <div className="mt-5 grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <Tile
              value={nEval !== null ? String(nEval) : "—"}
              label={t("trust.nPatients", { n: nEval ?? "—" })}
              sub={[
                sumCounts.recordings !== null && sumCounts.people !== null && sumCounts.recordings !== sumCounts.people ? t("trust.peopleRecordings", { p: sumCounts.people, r: sumCounts.recordings }) : null,
                lv2.nForecasts !== null ? t("trust.nForecasts", { n: formatInt(lv2.nForecasts, lang) }) : null,
              ]
                .filter(Boolean)
                .join(" · ") || undefined}
            />
            <Tile value={mg(lv2.rmse60)} unit={t("common.mgdl")} label={t("trust.tileRmse", { level: levelName(lv2.level) })} sub={lv2.rmse60Ci ? t("trust.ci", { range: ciText(lv2.rmse60Ci, mg) }) : undefined} />
            <Tile
              value={pc(lv2.coverage.find((c) => c.h === 60)?.v ?? null)}
              label={t("trust.tileCoverage", { level: levelName(lv2.level) })}
              sub={`${t("trust.target90")} · ${t("trust.widthFull", { n: mg(lv2.width.find((c) => c.h === 60)?.v ?? null) })}`}
            />
            <Tile value={f2(lv2.aurocHigh)} label={t("trust.tileAuroc", { level: levelName(lv2.level) })} sub={lv2.aurocHighCi ? t("trust.ci", { range: ciText(lv2.aurocHighCi, (v) => fixed(v, 2)) }) : undefined} />
          </div>
        ) : null}
        {evalProtocol && (
          <details className="mt-4 text-sm text-moon-2">
            <summary className="cursor-pointer font-semibold text-moon">{t("trust.evalProtocol")}</summary>
            <p className="mt-1 leading-relaxed" lang={enOnly}>
              {evalProtocol}
            </p>
          </details>
        )}
      </section>

      <div className="grid grid-cols-1 gap-5 lg:grid-cols-2">
        {/* ---------------- 0. protocol change: old vs new numbers ---------------- */}
        {pchg && (
          <TrustCard id="protocol-change" title={t("trust.pc.title")} caption={t("trust.pc.caption")} wide raw={isObj(summary.data) ? summary.data.protocol_change : undefined}>
            {pchg.rows.length ? (
              <Table
                minW={480}
                head={[t("trust.col.metric"), t("trust.pc.old"), t("trust.pc.new"), t("trust.pc.delta")]}
                rows={pchg.rows.map((r) => {
                  const isRate = /coverage|auroc/i.test(r.key);
                  const f = (v: number | null) => (v === null ? "—" : /coverage/i.test(r.key) ? pc(v, 1) : isRate ? fixed(v, 3) : fixed(v, 2));
                  return {
                    key: r.key,
                    cells: [
                      <span key="k" lang="en">{humanizeKey(r.key.replace(/\./g, " · "))}</span>,
                      f(r.oldV),
                      <strong key="n">{f(r.newV)}</strong>,
                      r.delta === null ? "—" : /coverage/i.test(r.key) ? `${r.delta > 0 ? "+" : r.delta < 0 ? "−" : ""}${fixed(Math.abs(r.delta * 100), 1)} pts` : `${r.delta > 0 ? "+" : r.delta < 0 ? "−" : ""}${fixed(Math.abs(r.delta), isRate ? 3 : 2)}`,
                    ],
                  };
                })}
              />
            ) : (
              <NotGenerated />
            )}
            {pchg.note && <p className="mt-2 text-xs text-ink-3" lang={enOnly}>{pchg.note}</p>}
            {pchg.description && (
              <details className="mt-3 text-xs text-ink-3">
                <summary className="cursor-pointer font-semibold">{t("trust.protocol")}</summary>
                <p className="mt-1 leading-relaxed" lang={enOnly}>
                  {pchg.description}
                </p>
                {pchg.oldSource && <p className="mt-1 font-mono">{pchg.oldSource}</p>}
              </details>
            )}
          </TrustCard>
        )}
        {/* ---------------- 1. sensor ladder ---------------- */}
        <TrustCard
          id="ladder"
          title={t("trust.ladderTitle")}
          caption={t("trust.ladderCaption")}
          info={t("glossary.rmse")}
          wide
          loading={ladder.isLoading && summary.isLoading}
          raw={ladder.data}
        >
          {levels.some((l) => l.rmse.length) ? (
            <div className="grid grid-cols-1 gap-6 xl:grid-cols-[minmax(0,1fr)_minmax(0,1.1fr)]">
              <div data-tour="trust-ladder" className="min-w-0">
                <MultiLine
                  series={levels
                    .filter((l) => l.rmse.length)
                    .map((l, i) => ({ key: l.level, label: levelName(l.level, l.label), color: RAMP[i % RAMP.length], values: l.rmse.map((p) => ({ x: p.h, y: p.v })) }))}
                  xLabel={(x) => t("trust.horizonShort", { n: x })}
                  yLabel={`RMSE (${t("common.mgdl")})`}
                  yFormat={(v) => (Number.isInteger(v) ? String(v) : fixed(v, 1))}
                  ariaLabel={t("trust.ladderCaption")}
                  height={280}
                  zeroBased={false}
                />
                {lv2?.rmse60Abstained !== null && lv2?.rmse60Confident !== null && lv2 && (
                  <p className="mt-2 text-xs leading-relaxed text-ink-3">
                    {t("trust.abstainNote", { level: levelName(lv2.level), a: mg(lv2.rmse60Abstained), b: mg(lv2.rmse60Confident), rate: pc(lv2.abstainRate, 1) })}
                  </p>
                )}
              </div>
              <Table
                minW={620}
                head={[t("trust.col.level"), t("trust.col.rmse60"), t("trust.col.coverage60"), t("trust.col.width60"), t("trust.col.rmse120"), t("trust.col.auroc"), t("trust.col.recon")]}
                rows={levels.map((l) => ({
                  key: l.level,
                  tone: l.level === DEFAULT_LEVEL ? "strong" : undefined,
                  cells: [
                    levelName(l.level, l.label),
                    <WithCi key="r" v={l.rmse60} c={l.rmse60Ci} />,
                    pc(l.coverage.find((p) => p.h === 60)?.v ?? null, 1),
                    mg(l.width.find((p) => p.h === 60)?.v ?? null),
                    mg(l.rmse.find((p) => p.h === 120)?.v ?? null),
                    <WithCi key="a" v={l.aurocHigh} c={l.aurocHighCi} f={(v) => fixed(v, 2)} />,
                    mg(l.reconRmse),
                  ],
                }))}
              />
            </div>
          ) : (
            <NotGenerated />
          )}
          {textOf(ladder.data, "protocol") && (
            <details className="mt-3 text-xs text-ink-3">
              <summary className="cursor-pointer font-semibold">{t("trust.protocol")}</summary>
              <p className="mt-1 leading-relaxed" lang={enOnly}>
                {textOf(ladder.data, "protocol")}
              </p>
            </details>
          )}
        </TrustCard>

        {/* ---------------- 2. coverage ---------------- */}
        <TrustCard
          id="coverage"
          title={t("trust.coverageTitle")}
          caption={t("trust.coverageCaption")}
          info={t("glossary.coverage")}
          loading={ladder.isLoading && summary.isLoading}
          action={
            levels.some((l) => l.coverage.length > 1) ? (
              <Segmented value={covH} onChange={setCovH} label={t("trust.horizonLabel")} options={HORIZONS.map((h) => ({ v: h, label: t("trust.horizonShort", { n: h }) }))} />
            ) : undefined
          }
        >
          {levels.some((l) => l.coverage.some((c) => c.h === covH)) ? (
            <>
              <RefBars
                bars={levels
                  .filter((l) => l.coverage.some((c) => c.h === covH))
                  .map((l) => {
                    const w = l.width.find((c) => c.h === covH)?.v;
                    return {
                      key: l.level,
                      label: levelName(l.level, l.label),
                      short: i18n.exists(`trust.levelShort.${l.level}`) ? t(`trust.levelShort.${l.level}`) : l.level,
                      value: l.coverage.find((c) => c.h === covH)!.v,
                      sub: w !== undefined ? `${Math.round(w)}` : undefined,
                    };
                  })}
                reference={0.9}
                refLabel={t("trust.nominal")}
                format={(v) => `${Math.round(v * 100)}%`}
                ariaLabel={t("trust.coverageCaption")}
              />
              <p className="mt-1 text-xs text-ink-3">{t("trust.widthNoteFull")}</p>
            </>
          ) : (
            <NotGenerated />
          )}
        </TrustCard>

        {/* ---------------- 3. reliability ---------------- */}
        <TrustCard
          id="reliability"
          title={t("trust.calibrationTitle")}
          caption={t("trust.calibrationCaption")}
          loading={calCurve.isLoading}
          raw={calCurve.data}
          action={rel.length > 1 ? <Segmented value={relCur?.level ?? relLevel} onChange={setRelLevel} label={t("ladder.label")} options={rel.map((r) => ({ v: r.level, label: levelName(r.level) }))} /> : undefined}
        >
          {relCur && relCur.high.length ? (
            <>
              <Reliability
                curves={[
                  ...(relCur.highRaw.length ? [{ key: "raw", label: t("trust.uncalibrated"), points: relCur.highRaw, color: "rgb(var(--ink-3))", dashed: true }] : []),
                  { key: "cal", label: t("trust.calibrated"), points: relCur.high, color: "rgb(var(--coral-ink))" },
                ]}
                xLabel={t("trust.predicted")}
                yLabel={t("trust.observed")}
                ariaLabel={t("trust.calibrationCaption")}
              />
              <div className="mt-2 flex flex-wrap justify-center gap-4 text-xs text-ink-2">
                <span className="inline-flex items-center gap-1.5">
                  <span className="h-2.5 w-2.5 rounded-full bg-coral-ink" aria-hidden />
                  {t("trust.calibrated")} · ECE {f2(relCur.eceHigh)}
                </span>
                {relCur.highRaw.length > 0 && (
                  <span className="inline-flex items-center gap-1.5">
                    <span className="h-2.5 w-2.5 rounded-full border-2 border-ink-3" aria-hidden />
                    {t("trust.uncalibrated")} · ECE {f2(relCur.eceHighRaw)}
                  </span>
                )}
              </div>
              <p className="mt-2 text-xs leading-relaxed text-ink-3">{t("trust.eceNote")}</p>
            </>
          ) : (
            <NotGenerated />
          )}
        </TrustCard>

        {/* ---------------- 4. low events: not validated ---------------- */}
        <TrustCard id="lows" title={t("trust.lowTitle")} tone="warn" loading={ladder.isLoading}>
          {lv2 ? (
            <div className="space-y-3 text-sm leading-relaxed">
              <p className="inline-flex items-center gap-1.5 rounded-full border border-marigold-ink/40 bg-marigold/10 px-3 py-1 text-xs font-bold text-marigold-ink">
                <TriangleAlert size={13} aria-hidden />
                {t("risk.notValidated")}
              </p>
              <p>
                {lv2.low.positiveWindows !== null
                  ? t("trust.lowBody", { pct: pc(lv2.low.prevalence, 1), n: lv2.low.positiveWindows, p: lv2.low.patientsWithLows ?? "—" })
                  : t("trust.lowBodyNoCount", { pct: pc(lv2.low.prevalence, 1) })}
              </p>
              <Table
                minW={300}
                head={[t("trust.col.level"), t("trust.col.lowShare"), t("trust.col.aurocLow")]}
                rows={levels.map((l) => ({ key: l.level, cells: [levelName(l.level, l.label), pc(l.low.prevalence, 1), f2(l.aurocLow)] }))}
              />
              <p className="text-xs text-ink-3">{t("trust.lowAurocNote")}</p>
              {lv2.low.note && (
                <p className="text-xs text-ink-3" lang={enOnly}>
                  {lv2.low.note}
                </p>
              )}
            </div>
          ) : (
            <NotGenerated />
          )}
        </TrustCard>

        {/* ---------------- 9. error grid ---------------- */}
        <TrustCard
          id="grid"
          title={t("trust.errorGridTitle")}
          caption={t("trust.errorGridCaption")}
          loading={grid.isLoading}
          raw={grid.data}
          action={
            eg.levels.length ? (
              <Segmented
                value={gridKind}
                onChange={setGridKind}
                label={t("trust.errorGridTitle")}
                options={[
                  { v: "forecast", label: t("trust.gridForecast") },
                  { v: "virtual", label: t("trust.gridVirtual") },
                ]}
              />
            ) : undefined
          }
        >
          {eg.levels.length ? (
            <>
              <ZoneStack
                rows={eg.levels.map((l) => ({ key: l.level, label: levelName(l.level, l.label), zones: gridKind === "forecast" ? l.forecast : l.virtual }))}
                ariaLabel={t("trust.errorGridTitle")}
                zoneLabel={(z) => t("trust.zone", { z })}
              />
              <p className="mt-3 text-xs text-ink-3">{t("trust.gridNote")}</p>
            </>
          ) : (
            <NotGenerated />
          )}
        </TrustCard>

        {/* ---------------- 9b. value of a recent finger-prick ---------------- */}
        <TrustCard id="recent" title={t("trust.recentTitle")} caption={t("trust.recentCaption")} loading={ladder.isLoading} raw={ladder.data && isObj(ladder.data) ? ladder.data.recent_prick_value : undefined}>
          {rp && rp.rows.length ? (
            <div className="space-y-3">
              <MultiLine
                series={[
                  { key: "with", label: t("trust.withPrick"), values: rp.rows.filter((r) => r.withPrick !== null).map((r) => ({ x: r.h, y: r.withPrick as number })) },
                  { key: "without", label: t("trust.withoutPrick"), dashed: true, values: rp.rows.filter((r) => r.without !== null).map((r) => ({ x: r.h, y: r.without as number })) },
                ]}
                xLabel={(x) => t("trust.horizonShort", { n: x })}
                yLabel={`RMSE (${t("common.mgdl")})`}
                yFormat={(v) => (Number.isInteger(v) ? String(v) : fixed(v, 1))}
                ariaLabel={t("trust.recentTitle")}
                height={240}
                zeroBased={false}
              />
              {rp.nForecasts !== null && <p className="text-xs text-ink-3">{t("trust.recentN", { n: formatInt(rp.nForecasts, lang), p: rp.nPatients ?? "—" })}</p>}
              {rp.diff60 && (
                <p className={`flex items-start gap-2 rounded-2xl p-3 text-sm leading-relaxed ${rp.diff60.hi < 0 ? "bg-teal/10" : "bg-paper-2"}`}>
                  <Scale size={16} className="mt-0.5 shrink-0 text-ink-3" aria-hidden />
                  <span>
                    {t("trust.recentDiff", { d: signedMg(rp.diff60.est), lo: signedMg(rp.diff60.lo), hi: signedMg(rp.diff60.hi) })}{" "}
                    {rp.diff60.hi < 0 ? t("trust.recentHelps") : rp.diff60.lo > 0 ? t("trust.recentHurts") : t("trust.recentUnclear")}
                  </span>
                </p>
              )}
              {rp.definition && (
                <details className="text-xs text-ink-3">
                  <summary className="cursor-pointer font-semibold">{t("trust.protocol")}</summary>
                  <p className="mt-1 leading-relaxed" lang={enOnly}>
                    {rp.definition}
                  </p>
                </details>
              )}
            </div>
          ) : (
            <NotGenerated note={ladder.data ? t("trust.pending") : undefined} />
          )}
        </TrustCard>

        {/* ---------------- 9c. living uncertainty (evidence for the widening band) ---------------- */}
        <TrustCard id="living" title={t("trust.livingTitle")} caption={t("trust.livingCaption")} info={t("glossary.coverage")} loading={ladder.isLoading} raw={ladder.data && isObj(ladder.data) ? ladder.data.by_hours_since_reading : undefined}>
          {hs.length ? (
            <div className="space-y-3">
              <MultiLine
                series={[
                  { key: "rmse", label: t("trust.seriesRmse"), values: hs.flatMap((b, i) => (b.rmse60 !== null ? [{ x: i, y: b.rmse60 }] : [])) },
                  { key: "width", label: t("trust.seriesWidth"), dashed: true, values: hs.flatMap((b, i) => (b.width60 !== null ? [{ x: i, y: b.width60 }] : [])) },
                ]}
                xLabel={(i) => (hs[i] ? hoursLabel(hs[i]) : "")}
                yLabel={t("common.mgdl")}
                yFormat={(v) => (Number.isInteger(v) ? String(v) : fixed(v, 1))}
                ariaLabel={t("trust.livingTitle")}
                height={240}
              />
              <Table
                minW={300}
                head={[t("trust.col.hours"), t("trust.col.forecasts"), t("trust.col.rmse60"), t("trust.col.width60"), t("trust.col.coverage60")]}
                rows={hs.map((b) => ({
                  key: b.key,
                  tone: b.coverage60 !== null && Math.abs(b.coverage60 - 0.9) > 0.05 ? "flag" : undefined,
                  cells: [hoursLabel(b), b.n !== null ? formatInt(b.n, lang) : "—", mg(b.rmse60), mg(b.width60), pc(b.coverage60)],
                }))}
              />
              <p className="flex items-start gap-2 rounded-2xl bg-paper-2 p-3 text-sm leading-relaxed">
                <Scale size={16} className="mt-0.5 shrink-0 text-ink-3" aria-hidden />
                <span>
                  {widthGrows(hs) ? t("trust.livingWidens") : t("trust.livingFlat")}{" "}
                  {hs.some((b) => b.coverage60 !== null && Math.abs(b.coverage60 - 0.9) > 0.05)
                    ? t("trust.livingCoverageOff", { n: hs.filter((b) => b.coverage60 !== null && Math.abs(b.coverage60 - 0.9) > 0.05).length })
                    : t("trust.livingCoverageOk")}
                </span>
              </p>
              <p className="text-xs leading-relaxed text-ink-3">{t("trust.livingNote")}</p>
            </div>
          ) : (
            <NotGenerated note={ladder.data ? t("trust.pending") : undefined} />
          )}
        </TrustCard>

        {/* ---------------- 5. baselines ---------------- */}
        {/* ---------------- 5b. paired band width (controlled living uncertainty) ---------------- */}
        {pw.blocks.length > 0 && (
          <TrustCard id="paired-width" title={t("trust.pw.title")} caption={t("trust.pw.caption")} info={t("glossary.coverage")} wide raw={isObj(ladder.data) ? ladder.data.paired_band_width : undefined}>
            <div className="grid grid-cols-1 gap-5 xl:grid-cols-2">
              {pw.blocks.map((b) => (
                <div key={b.key} className="min-w-0">
                  <h3 className="text-sm font-bold">{i18n.exists(`trust.pw.blocks.${b.key}`) ? t(`trust.pw.blocks.${b.key}`) : (b.subset ?? humanizeKey(b.key))}</h3>
                  <p className="mb-2 text-xs text-ink-3">
                    {[
                      b.people !== null ? t("trust.nPeople", { count: b.people }) : null,
                      b.recordings !== null && b.recordings !== b.people ? t("trust.nRecordings", { count: b.recordings }) : null,
                      b.windows !== null ? t("trust.nForecasts", { n: formatInt(b.windows, lang) }) : null,
                    ]
                      .filter(Boolean)
                      .join(" · ")}
                  </p>
                  <Table
                    minW={520}
                    head={[t("trust.horizonLabel"), t("trust.pw.with"), t("trust.pw.without"), t("trust.pw.diff"), t("trust.pw.cov")]}
                    rows={b.rows.map((r) => ({
                      key: String(r.h),
                      tone: r.ci && r.ci.hi < 0 ? "strong" : undefined,
                      cells: [
                        t("trust.horizonShort", { n: r.h }),
                        mg(r.withPricks),
                        mg(r.without),
                        <span key="d" className="whitespace-nowrap">
                          {r.diff === null ? "—" : signedMg(r.diff)}
                          {r.ci && <span className="ml-1 text-xs font-normal text-ink-3">({signedMg(r.ci.lo)}, {signedMg(r.ci.hi)})</span>}
                        </span>,
                        `${pc(r.covWith)} / ${pc(r.covWithout)}`,
                      ],
                    }))}
                  />
                </div>
              ))}
            </div>
            <p className="mt-2 text-xs text-ink-3">{t("trust.pw.note")}</p>
            {pw.definition && (
              <details className="mt-2 text-xs text-ink-3">
                <summary className="cursor-pointer font-semibold">{t("trust.protocol")}</summary>
                <p className="mt-1 leading-relaxed" lang={enOnly}>
                  {pw.definition}
                </p>
              </details>
            )}
          </TrustCard>
        )}

        {/* ---------------- 5c. exploratory horizons (beyond 120 min) ---------------- */}
        {ex.rows.length > 0 && (
          <TrustCard
            id="exploratory"
            title={t("trust.ex.title")}
            caption={t("trust.ex.caption", { n: ex.validatedMin ?? 120 })}
            wide
            action={
              <span className="flex flex-wrap items-center gap-2">
                <EvidenceChip status="exploratory" />
                {Array.from(new Set(ex.rows.map((r) => r.level))).length > 1 && (
                  <Segmented
                    value={exLevel}
                    onChange={setExLevel}
                    label={t("ladder.label")}
                    options={Array.from(new Set(ex.rows.map((r) => r.level))).map((l) => ({ v: l, label: levelName(l) }))}
                  />
                )}
              </span>
            }
          >
            <Table
              minW={520}
              head={[t("trust.horizonLabel"), t("trust.col.rmse"), t("trust.col.coverage"), t("trust.col.width"), t("trust.col.people")]}
              rows={ex.rows
                .filter((r) => r.level === exLevel || !ex.rows.some((x) => x.level === exLevel))
                .map((r) => ({
                  key: `${r.level}-${r.h}`,
                  cells: [
                    `${t("trust.horizonShort", { n: r.h })}${ex.rows.some((x) => x.level === exLevel) ? "" : ` · ${levelName(r.level)}`}`,
                    <WithCi key="r" v={r.rmse} c={r.rmseCi} />,
                    pc(r.coverage, 1),
                    mg(r.width),
                    r.people ?? "—",
                  ],
                }))}
            />
            {ex.note && (
              <p className="mt-2 text-xs leading-relaxed text-ink-3" lang={enOnly}>
                {ex.note}
              </p>
            )}
          </TrustCard>
        )}

        <TrustCard
          id="baselines"
          title={t("trust.baselinesTitle")}
          caption={t("trust.baselinesCaption")}
          wide
          loading={baseQ.isLoading}
          raw={baseQ.data}
          action={
            base.methods.length ? (
              <Segmented
                value={baseMetric}
                onChange={setBaseMetric}
                label={t("trust.metric")}
                options={[
                  { v: "rmse30", label: t("trust.horizonShort", { n: 30 }) },
                  { v: "rmse60", label: t("trust.horizonShort", { n: 60 }) },
                  { v: "rmse120", label: t("trust.horizonShort", { n: 120 }) },
                  { v: "auroc", label: "AUROC" },
                ]}
              />
            ) : undefined
          }
        >
          {base.methods.length && base.levels.length ? (
            <>
              <Table
                minW={560}
                head={[t("trust.col.method"), ...base.levels.map((l) => levelName(l.level, l.label))]}
                rows={base.methods.map((m) => ({
                  key: m,
                  tone: m === "full_hybrid" ? "strong" : undefined,
                  cells: [
                    <span key="m" className="inline-flex flex-col">
                      {i18n.exists(`trust.methods.${m}`) ? t(`trust.methods.${m}`) : humanizeKey(m)}
                      {m === "full_hybrid" && <span className="text-xs font-normal text-marigold-ink" lang="en">{t("app.name")}</span>}
                    </span>,
                    ...base.levels.map((l) => {
                      const v = baseVal(base.cell(m, l.level));
                      const best = v !== null && v === baseBest(l.level);
                      return (
                        <span key={l.level} className={best ? "inline-flex items-center gap-1 font-bold text-teal-ink" : ""}>
                          {v === null ? "—" : baseMetric === "auroc" ? fixed(v, 2) : fixed(v, 1)}
                          {best && <span className="sr-only">({t("trust.best")})</span>}
                        </span>
                      );
                    }),
                  ],
                }))}
              />
              <p className="mt-2 text-xs text-ink-3">{baseMetric === "auroc" ? t("trust.baselinesAurocNote") : t("trust.baselinesRmseNote")}</p>
              {pbase.length > 0 && (
                <div className="mt-5">
                  <h3 className="text-sm font-bold">{t("trust.pb.title")}</h3>
                  <p className="mb-2 text-xs text-ink-3">{t("trust.pb.caption")}</p>
                  <Table
                    minW={560}
                    head={[t("trust.col.method"), t("trust.pb.hybrid"), t("trust.pb.baseline"), t("trust.pb.diff"), t("trust.col.people")]}
                    rows={pbase.map((r) => ({
                      key: r.method,
                      tone: r.excludesZero && r.diff !== null && r.diff < 0 ? "strong" : undefined,
                      cells: [
                        i18n.exists(`trust.methods.${r.method}`) ? t(`trust.methods.${r.method}`) : humanizeKey(r.method),
                        mg(r.hybrid),
                        mg(r.baseline),
                        <span key="d" className="whitespace-nowrap">
                          {r.diff === null ? "—" : signedMg(r.diff)}
                          {r.ci && <span className="ml-1 text-xs font-normal text-ink-3">({signedMg(r.ci.lo)}, {signedMg(r.ci.hi)})</span>}
                          {r.excludesZero === false && <span className="ml-1 text-xs font-normal text-ink-3">· {t("trust.pb.crossesZero")}</span>}
                        </span>,
                        r.people ?? "—",
                      ],
                    }))}
                  />
                </div>
              )}
            </>
          ) : (
            <NotGenerated />
          )}
        </TrustCard>

        {/* ---------------- 6. next-best-prick (null result) ---------------- */}
        <TrustCard id="nbp" title={t("trust.nbpTitle")} caption={t("trust.nbpCaption")} info={t("glossary.nbp")} wide loading={nbpQ.isLoading} raw={nbpQ.data}>
          {nbp.arms.length ? (
            <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
              <div className="min-w-0">
                <Table
                  minW={380}
                  head={[t("trust.col.arm"), t("trust.col.recon"), t("trust.col.rmse60")]}
                  rows={nbp.arms.map((a) => ({
                    key: a.name,
                    tone: /twin/i.test(a.name) ? "strong" : undefined,
                    cells: [
                      i18n.exists(`trust.arms.${armKey(a.name)}`) ? t(`trust.arms.${armKey(a.name)}`) : a.name,
                      mg(a.reconRmse),
                      <WithCi key="r" v={a.rmse60} c={a.rmse60Ci} />,
                    ],
                  }))}
                />
                {nbp.protocol && (
                  <p className="mt-2 text-xs text-ink-3" lang={enOnly}>
                    {nbp.protocol}
                  </p>
                )}
              </div>
              <div className="min-w-0">
                <p className="text-sm font-semibold">{t("trust.nbpDiffTitle")}</p>
                {nbp.diffs.length ? (
                  <>
                    <ForestPlot
                      items={nbp.diffs.map((d) => ({
                        key: d.key,
                        label: i18n.exists(`trust.diffs.${d.key}`) ? t(`trust.diffs.${d.key}`) : d.key,
                        sub: d.improved !== null && d.n !== null ? t("trust.improvedOf", { k: d.improved, n: d.n }) : undefined,
                        mean: d.mean,
                        lo: d.lo,
                        hi: d.hi,
                      }))}
                      format={(v) => `${v > 0 ? "+" : ""}${fixed(v, 2)}`}
                      ariaLabel={t("trust.nbpDiffTitle")}
                      betterLabel={t("trust.twinBetter")}
                      worseLabel={t("trust.twinWorse")}
                    />
                    <p className={`mt-2 flex items-start gap-2 rounded-2xl p-3 text-sm leading-relaxed ${nbpNull ? "bg-paper-2" : "bg-teal/10"}`}>
                      <Scale size={16} className="mt-0.5 shrink-0 text-ink-3" aria-hidden />
                      {nbpNull ? t("trust.nbpNull") : t("trust.nbpEffect")}
                    </p>
                  </>
                ) : (
                  <NotGenerated />
                )}
              </div>
            </div>
          ) : (
            <NotGenerated />
          )}
        </TrustCard>

        {/* ---------------- 7. transfer ---------------- */}
        <TrustCard id="transfer" title={t("trust.transferTitle")} caption={t("trust.transferCaption")} wide loading={transferQ.isLoading} raw={transferQ.data}>
          {tr.rows.length ? (
            <div className="grid grid-cols-1 gap-6 lg:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)]">
              <Table
                minW={640}
                head={[t("trust.col.test"), t("trust.col.train"), t("trust.col.setting"), t("trust.col.people"), t("trust.col.rmse60"), t("trust.col.coverage60")]}
                rows={tr.rows.map((r, i) => ({
                  key: `${i}`,
                  tone: r.inDomain ? undefined : "strong",
                  cells: [
                    r.test,
                    <span key="tr" className="inline-flex items-center justify-end gap-1.5 font-normal">
                      <span className={`whitespace-nowrap rounded-full px-2 py-0.5 text-[0.68rem] font-semibold ${r.inDomain ? "bg-teal/15 text-teal-ink" : "bg-marigold/20 text-marigold-ink"}`}>
                        {r.inDomain ? t("trust.inDomain") : t("trust.transferred")}
                      </span>
                      <span lang="en">{r.train.replace(/\s*\((in-domain|transfer)\)/i, "")}</span>
                    </span>,
                    <span key="s" className="font-normal" lang={enOnly}>
                      {r.setting}
                    </span>,
                    r.nPeople !== null && r.nRecordings !== null && r.nPeople !== r.nRecordings ? (
                      <span key="n" className="inline-flex flex-col items-end whitespace-nowrap leading-tight">
                        <span>{t("trust.nPeople", { count: r.nPeople })}</span>
                        <span className="text-xs font-normal text-ink-3">{t("trust.nRecordings", { count: r.nRecordings })}</span>
                      </span>
                    ) : (
                      (r.nPeople ?? r.nRecordings ?? r.nPatients ?? "—")
                    ),
                    <WithCi key="r" v={r.rmse60} c={r.rmse60Ci} />,
                    pc(r.coverage.find((c) => c.h === 60)?.v ?? null),
                  ],
                }))}
              />
              <div className="min-w-0 space-y-3">
                {tr.gaps.map((g) => (
                  <div key={g.key} className="rounded-3xl bg-paper-2 p-4">
                    <p className="num text-3xl font-extrabold text-marigold-ink">
                      +{fixed(g.v, 1)}
                      <span className="ml-1 text-sm font-semibold text-ink-3">{t("common.mgdl")}</span>
                    </p>
                    <p className="mt-1 text-sm text-ink-2">{t("trust.gap", { setting: i18n.exists(`trust.gaps.${g.key}`) ? t(`trust.gaps.${g.key}`) : g.key })}</p>
                  </div>
                ))}
                {tr.rows.some((r) => r.nPeople !== null && r.nRecordings !== null && r.nPeople !== r.nRecordings) && (
                  <p className="text-xs leading-relaxed text-ink-3">{t("trust.recordingsNote")}</p>
                )}
                {tr.insulin.length >= 2 && (
                  <p className="text-sm leading-relaxed text-ink-2">
                    {t("trust.insulin", {
                      a: mg(tr.insulin.find((x) => /insulin_users/.test(x.key))?.m.rmse60 ?? null),
                      b: mg(tr.insulin.find((x) => /no_insulin/.test(x.key))?.m.rmse60 ?? null),
                    })}
                  </p>
                )}
              </div>
            </div>
          ) : (
            <NotGenerated />
          )}
        </TrustCard>

        {/* ---------------- 8. subgroups ---------------- */}
        <TrustCard id="subgroups" title={t("trust.subgroupsTitle")} caption={t("trust.subgroupsCaption")} wide loading={subQ.isLoading} raw={subQ.data}>
          {sub.rows.length ? (
            <>
              <Table
                minW={620}
                head={[t("trust.col.group"), t("trust.col.n"), t("trust.col.rmse60"), t("trust.col.coverage60"), "AUROC", "ECE", t("trust.col.flag")]}
                rows={[
                  ...(sub.overall
                    ? [{ key: "overall", tone: "strong" as const, cells: [t("trust.overall"), "", mg(sub.overall.rmse60), pc(sub.overall.coverage60), "", f2(sub.overall.ece), ""] }]
                    : []),
                  ...sub.rows.map((r, i) => ({
                    key: `${i}`,
                    tone: r.flagged ? ("flag" as const) : undefined,
                    cells: [
                      <span key="g" className="inline-flex flex-col" lang="en">
                        <span className="text-[0.7rem] font-semibold uppercase tracking-wide text-ink-3">{r.dimension}</span>
                        {r.group}
                      </span>,
                      r.n ?? "—",
                      mg(r.rmse60),
                      pc(r.coverage60),
                      f2(r.auroc),
                      f2(r.ece),
                      r.flagged ? (
                        <span key="f" className="inline-flex items-center gap-1 rounded-full bg-[rgb(176_56_40)] px-2 py-0.5 text-[0.7rem] font-bold text-white">
                          <Flag size={11} aria-hidden />
                          {t("trust.flagged")}
                        </span>
                      ) : (
                        <span key="f" className="text-ink-3">
                          —
                        </span>
                      ),
                    ],
                  })),
                ]}
              />
              <p className="mt-3 text-xs leading-relaxed text-ink-3">
                {sub.rows.some((r) => r.flagged) ? t("trust.someFlagged", { n: sub.rows.filter((r) => r.flagged).length }) : t("trust.noneFlagged")}{" "}
                {sub.rule && (
                  <>
                    {t("trust.flagRule")}: <span lang={enOnly}>{sub.rule}</span>.
                  </>
                )}
              </p>
            </>
          ) : (
            <NotGenerated />
          )}
        </TrustCard>

        {/* ---------------- 10. calibration length ---------------- */}
        <TrustCard id="callen" title={t("trust.calLengthTitle")} caption={t("trust.calLengthCaption")} loading={calLen.isLoading} raw={calLen.data}>
          {cl.rows.length ? (
            <>
              <Table
                minW={360}
                head={[t("trust.col.days"), t("trust.col.rmse60"), t("trust.col.coverage60"), "AUROC"]}
                rows={cl.rows.map((r) => ({
                  key: String(r.days),
                  cells: [t("trust.days", { count: r.days }), <WithCi key="r" v={r.rmse60} c={r.rmse60Ci} />, pc(r.coverage.find((c) => c.h === 60)?.v ?? null), f2(r.aurocHigh)],
                }))}
              />
              {cl.protocol && (
                <p className="mt-2 text-xs text-ink-3" lang={enOnly}>
                  {cl.protocol}
                </p>
              )}
            </>
          ) : (
            <NotGenerated />
          )}
        </TrustCard>

        {/* ---------------- 11. multilingual agent evaluation (optional) ---------------- */}
        <TrustCard id="agent-multilingual" title={t("trust.ml.title")} caption={t("trust.ml.caption")} wide loading={agentQ.isLoading} raw={agentQ.data}>
          {ml && ml.metrics.pass ? (
            <div className="space-y-6">
              <div className="flex flex-wrap items-center gap-2 text-xs">
                {ml.split && (
                  <span className="rounded-full bg-paper-2 px-2.5 py-1 font-semibold text-ink-2">{ml.split === "heldout" ? t("trust.ml.heldout") : <span lang="en">{ml.split}</span>}</span>
                )}
                {ml.mode && (
                  <span className={`rounded-full px-2.5 py-1 font-semibold ${ml.mode === "live" ? "bg-paper-2 text-ink-2" : "bg-coral/15 text-coral-ink"}`}>
                    {ml.mode === "live" ? t("trust.ml.live") : <span lang="en">{ml.mode}</span>}
                  </span>
                )}
                {ml.guardrails !== null && (
                  <span className="inline-flex items-center gap-1 rounded-full bg-paper-2 px-2.5 py-1 font-semibold text-ink-2">
                    <ShieldCheck size={13} className="shrink-0" aria-hidden />
                    {ml.guardrails ? t("trust.ml.guardrailsOn") : t("trust.ml.guardrailsOff")}
                  </span>
                )}
                {ml.generatedAt && <span className="text-ink-3">{t("trust.generated", { date: formatDateTime(ml.generatedAt, lang) })}</span>}
              </div>
              {ml.mode && ml.mode !== "live" && (
                <p role="note" className="flex items-start gap-2 rounded-2xl bg-coral/10 px-4 py-3 text-sm text-ink">
                  <TriangleAlert size={16} className="mt-0.5 shrink-0 text-coral-ink" aria-hidden />
                  {t("trust.ml.notLive", { mode: ml.mode })}
                </p>
              )}
              <dl className="grid grid-cols-1 gap-x-6 gap-y-1 text-sm sm:grid-cols-2">
                {ml.model && (
                  <div className="flex min-w-0 flex-wrap gap-x-2">
                    <dt className="font-semibold text-ink-3">{t("trust.ml.model")}</dt>
                    <dd className="min-w-0 break-all font-mono text-xs leading-5" lang="en">
                      {ml.model}
                    </dd>
                  </div>
                )}
                {ml.nCases !== null && ml.nRuns !== null && (
                  <div className="flex min-w-0 flex-wrap gap-x-2">
                    <dt className="font-semibold text-ink-3">{t("trust.ml.sizeLabel")}</dt>
                    <dd className="num">{t("trust.ml.size", { cases: formatInt(ml.nCases, lang), langs: ml.perLanguage.length || ml.languages.length, runs: formatInt(ml.nRuns, lang) })}</dd>
                  </div>
                )}
              </dl>

              {/* Overall pass first, with what failed stated as plainly as what passed. */}
              <div className="rounded-3xl border border-line p-4 sm:p-5">
                <p className="text-sm font-semibold text-ink-3">{t("trust.ml.metric.pass")}</p>
                <p className="mt-1 flex flex-wrap items-baseline gap-x-3">
                  <span className="num text-4xl font-extrabold">{pc(ml.metrics.pass.rate)}</span>
                  <span className="num text-sm font-semibold text-ink-2">{t("trust.ml.runsPassed", { k: formatInt(ml.metrics.pass.k, lang), n: formatInt(ml.metrics.pass.n, lang) })}</span>
                </p>
                <RateBar rate={ml.metrics.pass.rate} />
                <p className="mt-2 text-sm leading-relaxed text-ink-2">
                  {t("trust.ml.failed", { k: formatInt(ml.metrics.pass.n - ml.metrics.pass.k, lang), n: formatInt(ml.metrics.pass.n, lang) })}
                </p>
              </div>

              <div>
                <h3 className="text-sm font-semibold">{t("trust.ml.checksTitle")}</h3>
                <p className="mb-1 text-xs text-ink-3">{t("trust.ml.knNote")}</p>
                <Table
                  minW={320}
                  caption={t("trust.ml.checksTitle")}
                  head={[t("trust.col.metric"), t("trust.ml.col.kn"), t("trust.ml.col.rate")]}
                  rows={ML_METRICS.filter((k) => k !== "pass" && ml.metrics[k]).map((k) => {
                    const f = ml.metrics[k] as Frac;
                    return {
                      key: k,
                      cells: [
                        <span key="k" className="inline-flex flex-col">
                          <span>{t(`trust.ml.metric.${k}`)}</span>
                          <span className="text-xs font-normal leading-snug text-ink-3">
                            {t(`trust.ml.hint.${k}`)}
                            {ML_LOWER_BETTER.includes(k) && ` · ${t("trust.lowerBetter")}`}
                          </span>
                        </span>,
                        <span key="n" className="whitespace-nowrap">{fracText(f)}</span>,
                        <span key="r" className="font-bold">{pc(f.rate)}</span>,
                      ],
                    };
                  })}
                />
              </div>

              <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
                {ml.perLanguage.length > 0 && (
                  <div className="min-w-0">
                    <h3 className="mb-1 text-sm font-semibold">{t("trust.ml.byLangTitle")}</h3>
                    <RateTable
                      caption={t("trust.ml.byLangTitle")}
                      head={[t("common.language"), t("trust.ml.col.kn"), t("trust.ml.col.rate")]}
                      rows={ml.perLanguage
                        .filter((r) => r.pass)
                        .map((r) => ({ key: r.lang, label: <span lang={r.lang}>{LANG_NAMES[r.lang] ?? r.lang}</span>, f: r.pass as Frac }))}
                      fracText={fracText}
                    />
                    {ml.perLanguage.every((r) => r.localeOk) && (
                      <p className="mt-2 text-xs leading-relaxed text-ink-3">
                        {t("trust.ml.localeOk", {
                          k: formatInt(ml.perLanguage.reduce((a, r) => a + (r.localeOk?.k ?? 0), 0), lang),
                          n: formatInt(ml.perLanguage.reduce((a, r) => a + (r.localeOk?.n ?? 0), 0), lang),
                        })}
                      </p>
                    )}
                  </div>
                )}
                {ml.perCategory.length > 0 && (
                  <div className="min-w-0">
                    <h3 className="mb-1 text-sm font-semibold">{t("trust.ml.byCatTitle")}</h3>
                    <RateTable
                      caption={t("trust.ml.byCatTitle")}
                      head={[t("trust.ml.col.category"), t("trust.ml.col.kn"), t("trust.ml.col.rate")]}
                      rows={ml.perCategory.map((c) => ({ key: c.key, label: i18n.exists(`trust.ml.cat.${c.key}`) ? t(`trust.ml.cat.${c.key}`) : humanizeKey(c.key), f: c.frac }))}
                      fracText={fracText}
                    />
                  </div>
                )}
              </div>

              {(ml.latency.p50 !== null || ml.latency.p95 !== null) && (
                <div>
                  <h3 className="mb-1 text-sm font-semibold">{t("trust.ml.latencyTitle")}</h3>
                  <dl className="grid grid-cols-2 gap-2.5 sm:max-w-md">
                    <div className="rounded-2xl bg-paper-2 p-3">
                      <dt className="text-xs font-semibold text-ink-3">{t("trust.ml.p50")}</dt>
                      <dd className="num mt-0.5 text-xl font-bold">{msText(ml.latency.p50)}</dd>
                    </div>
                    <div className="rounded-2xl bg-paper-2 p-3">
                      <dt className="text-xs font-semibold text-ink-3">{t("trust.ml.p95")}</dt>
                      <dd className="num mt-0.5 text-xl font-bold">{msText(ml.latency.p95)}</dd>
                    </div>
                  </dl>
                </div>
              )}

              <div className="space-y-2 rounded-2xl border border-line p-4 text-sm">
                {ml.scoring && (
                  <p className="flex items-start gap-2 font-semibold">
                    <Scale size={16} className="mt-0.5 shrink-0 text-ink-3" aria-hidden />
                    {/deterministic/i.test(ml.scoring) ? t("trust.ml.scoring") : <span lang="en">{ml.scoring}</span>}
                  </p>
                )}
                {ml.limitations.length > 0 && (
                  <>
                    <p className="font-semibold text-ink-3">{t("trust.ml.limitationsTitle")}</p>
                    <ul className="list-disc space-y-1 pl-5 leading-relaxed text-ink-2" lang={enOnly}>
                      {ml.limitations.map((x, i) => (
                        <li key={i}>{x}</li>
                      ))}
                    </ul>
                  </>
                )}
              </div>
            </div>
          ) : (
            <NotGenerated note={t("trust.pending")} />
          )}
        </TrustCard>

        {/* ---------------- 12. limitations ---------------- */}
        <TrustCard id="limits" title={t("trust.limitationsTitle")} wide loading={summary.isLoading}>
          {limitGroups.length ? (
            <div className="mt-3 space-y-4">
              {limitGroups.map((g) => (
                <section key={g.source} aria-label={t(`trust.limitSource.${g.source}`)}>
                  <h3 className="eyebrow mb-1.5 text-ink-3">{t(`trust.limitSource.${g.source}`)}</h3>
                  <ul className="grid gap-x-8 gap-y-2.5 md:grid-cols-2">
                    {g.items.map((l, i) => (
                      <li key={i} className="flex gap-2.5 text-[0.95rem] leading-relaxed" lang={enOnly}>
                        <span className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-marigold-ink" aria-hidden />
                        {l}
                      </li>
                    ))}
                  </ul>
                </section>
              ))}
            </div>
          ) : (
            <p className="flex gap-2.5 text-[0.95rem] leading-relaxed">{t("trust.noIndianData")}</p>
          )}
          {!isEnglish(lang) && limitGroups.length > 0 && <p className="mt-3 text-xs text-ink-3">{t("trust.englishOnly")}</p>}
        </TrustCard>

        {/* ---------------- 13. sources ---------------- */}
        <TrustCard id="sources" title={t("trust.sourcesTitle")} wide>
          <ul className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {SOURCES.map((s) => (
              <li key={s.key} className="flex flex-col rounded-2xl border border-line p-4">
                <p className="flex items-center gap-2 font-semibold">
                  <Database size={16} className="shrink-0 text-ink-3" aria-hidden />
                  {s.name}
                </p>
                <p className="mt-1">
                  <span className="rounded-full bg-paper-2 px-2.5 py-0.5 text-xs font-semibold text-ink-2">{s.licence}</span>
                </p>
                <p className="mt-2 flex-1 text-sm text-ink-2">{t(`trust.src.${s.key}`)}</p>
                {s.url && (
                  <a href={s.url} target="_blank" rel="noreferrer" className="link mt-2 inline-flex items-center gap-1 break-all text-sm">
                    {s.url.replace(/^https?:\/\//, "")}
                    <ExternalLink size={13} className="shrink-0" aria-hidden />
                  </a>
                )}
              </li>
            ))}
          </ul>
          <p className="mt-3 text-xs text-ink-3">{t("trust.sourcesFallback")}</p>
        </TrustCard>
      </div>
    </div>
  );
}

/** True when the 90% band width never shrinks from one hours-since-reading group to the next. */
const widthGrows = (bins: HoursBin[]) => {
  const w = bins.map((b) => b.width60).filter((v): v is number => v !== null);
  return w.length > 1 && w.every((v, i) => i === 0 || v >= w[i - 1]);
};

/** Language names in their own script (proper names, same in every UI language). */
const LANG_NAMES: Record<string, string> = {
  "en-US": "English",
  "es-ES": "Español",
  "fr-FR": "Français",
  "de-DE": "Deutsch",
  "it-IT": "Italiano",
  "ja-JP": "日本語",
};

/** A 0..1 rate as a thin bar (decorative: the number and its denominator are always printed next to it). */
function RateBar({ rate }: { rate: number }) {
  const w = Math.max(0, Math.min(1, rate)) * 100;
  return (
    <span className="mt-2 block h-2 w-full overflow-hidden rounded-full bg-paper-2" aria-hidden>
      <span className="block h-full rounded-full bg-violet-ink" style={{ width: `${w}%` }} />
    </span>
  );
}

/** Rates as a real table (k / n and percent per row) with a small bar under each percent. */
function RateTable({ caption, head, rows, fracText }: { caption: string; head: string[]; rows: { key: string; label: ReactNode; f: Frac }[]; fracText: (f: Frac) => string }) {
  return (
    <div className="relative -mx-1 max-w-full overflow-x-auto">
      <table className="w-full border-separate border-spacing-0 text-sm">
        <caption className="sr-only">{caption}</caption>
        <thead>
          <tr>
            {head.map((h, i) => (
              <th key={i} scope="col" className={`border-b border-line px-2 py-2 text-left align-bottom text-[0.7rem] font-semibold uppercase leading-tight tracking-wide text-ink-3 ${i ? "text-right" : ""}`}>
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.key}>
              <th scope="row" className="border-b border-line/70 px-2 py-2 text-left font-semibold">
                {r.label}
              </th>
              <td className="num whitespace-nowrap border-b border-line/70 px-2 py-2 text-right text-ink-2">{fracText(r.f)}</td>
              <td className="num w-[38%] border-b border-line/70 px-2 py-2 text-right font-bold">
                {pc(r.f.rate)}
                <RateBar rate={r.f.rate} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** Dataset and food-table sources with their licences (from backend/data/README.md and data/food/SOURCES.md). */
const SOURCES: { key: string; name: string; licence: string; url?: string }[] = [
  { key: "cgmacros", name: "CGMacros v1.0.0 (PhysioNet)", licence: "CC BY-NC-SA 4.0", url: "https://doi.org/10.13026/3z8q-x658" },
  { key: "shanghai", name: "ShanghaiT2DM (Zhao et al., Sci Data 2023)", licence: "CC BY 4.0", url: "https://doi.org/10.6084/m9.figshare.20444397" },
  { key: "indb", name: "Indian Nutrient Databank (INDB 2024)", licence: "CC BY 4.0", url: "https://doi.org/10.1016/j.cdnut.2024.103790" },
  { key: "usda", name: "USDA FoodData Central", licence: "Public domain (CC0 1.0)", url: "https://fdc.nal.usda.gov/" },
  { key: "ifct", name: "Indian Food Composition Tables 2017 (ICMR-NIN)", licence: "© ICMR-NIN · values used with attribution", url: "https://www.nin.res.in/ifct_book.html" },
  { key: "photos", name: "Sample meal photos (Wikimedia Commons)", licence: "CC BY-SA 4.0 / public domain" },
];

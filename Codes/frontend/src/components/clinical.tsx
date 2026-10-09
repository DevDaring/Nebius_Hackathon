import { useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { AnimatePresence, m as motion } from "framer-motion";
import { AlertTriangle, CheckCircle2, Download, FileUp, Loader2, RotateCcw } from "lucide-react";
import { api } from "@/api";
import { ApiError, mediaUrl } from "@/api/http";
import type { LabConfirm, LabField } from "@/api/types";
import { formatDateTime, fixed } from "@/lib/format";
import { useHealth, useLabSamples, useOutlook } from "@/api/hooks";
import { TwoLineChart } from "@/charts/SmallCharts";
import { useApp } from "@/store/app";
import { toast } from "@/store/toast";
import { ErrorState, InfoTip } from "./ui";
import { isEnglish } from "@/lib/langPrefs";

/* ---------------- 90-day outlook ---------------- */
export function OutlookCard({ patientId }: { patientId: string | null }) {
  const { t, i18n } = useTranslation();
  const ladder = useApp((s) => s.ladder);
  const q = useOutlook(patientId, ladder);
  const [metric, setMetric] = useState<"tir" | "a1c">("tir");
  const o = q.data;
  return (
    <section className="card p-5 sm:p-6" aria-labelledby="outlook-title">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 id="outlook-title" className="flex items-center gap-2 text-lg font-bold">
          {t("outlook.title")}
          <span className="rounded-full border border-marigold-ink/50 bg-marigold/10 px-2.5 py-0.5 text-xs font-bold uppercase tracking-wide text-marigold-ink">{t("outlook.projection")}</span>
          <InfoTip label={t("glossary.projection")} />
        </h2>
        <div role="radiogroup" aria-label={t("outlook.title")} className="flex rounded-full bg-paper-2 p-1 text-xs font-semibold">
          {(["tir", "a1c"] as const).map((m) => (
            <button key={m} type="button" role="radio" aria-checked={metric === m} onClick={() => setMetric(m)} className={`min-h-[34px] rounded-full px-3 ${metric === m ? "bg-card text-ink shadow-soft" : "text-ink-2"}`}>
              {m === "tir" ? t("outlook.tir") : t("outlook.ehba1c")}
            </button>
          ))}
        </div>
      </div>
      <div className="mt-4">
        {q.isLoading ? (
          <div className="skeleton h-[170px]" />
        ) : q.isError || !o ? (
          <ErrorState message={t("errors.generic")} onRetry={() => void q.refetch()} />
        ) : (
          <TwoLineChart
            xs={o.days}
            a={metric === "tir" ? o.tir_current : o.ehba1c_current}
            b={metric === "tir" ? o.tir_scenario : o.ehba1c_scenario}
            format={(v) => (metric === "tir" ? `${Math.round(v * 100)}%` : `${fixed(v, 1)}%`)}
            xLabel={(d) => t("outlook.day", { n: d })}
            ariaLabel={t("outlook.caption", { scenario: o.scenario_label })}
          />
        )}
      </div>
      {o && (
        <>
          <div className="mt-2 flex flex-wrap gap-4 text-xs text-ink-2">
            <span className="inline-flex items-center gap-1.5">
              <span className="w-5 border-t-2 border-dashed border-ink-3" aria-hidden />
              {t("outlook.current")}
            </span>
            <span className="inline-flex items-center gap-1.5">
              <span className="h-1 w-5 rounded bg-marigold" aria-hidden />
              {t("outlook.scenario")}
            </span>
          </div>
          <p className="mt-2 text-sm text-ink-2">{t("outlook.caption", { scenario: o.scenario_label })}</p>
          {isEnglish(i18n.language) && o.note && <p className="mt-1 text-xs text-ink-3">{o.note}</p>}
        </>
      )}
    </section>
  );
}

/* ---------------- Lab report → FHIR ---------------- */
export function LabCard({ patientId }: { patientId: string | null }) {
  const { t } = useTranslation();
  const samples = useLabSamples();
  const health = useHealth();
  const fileRef = useRef<HTMLInputElement>(null);
  const [phase, setPhase] = useState<"pick" | "parsing" | "confirm" | "saved">("pick");
  const [fields, setFields] = useState<LabField[]>([]);
  const [checked, setChecked] = useState<Set<string>>(new Set());
  const [saving, setSaving] = useState(false);
  const [result, setResult] = useState<LabConfirm | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [diagnoses, setDiagnoses] = useState<string[] | null>(null);
  const qc = useQueryClient();
  const { i18n } = useTranslation();

  const parse = async (input: { file: File } | { sample_id: string }) => {
    setPhase("parsing");
    setError(null);
    try {
      const res = await api.labParse(input);
      setFields(res.fields ?? []);
      setDiagnoses(Array.isArray(res.diagnoses) ? res.diagnoses : null);
      setChecked(new Set());
      setPhase("confirm");
    } catch (e) {
      if (e instanceof ApiError && e.status === 413) setError(t("lab.tooLarge"));
      else if (e instanceof ApiError && e.status === 429) setError(t("errors.rateLimited", { s: e.retryAfter ?? 30 }));
      else if (e instanceof ApiError && e.status === 503)
        setError(health.data?.mode === "live" ? t("lab.liveFailed") : "file" in input ? t("lab.liveUnavailable") : t("lab.sampleUnavailable"));
      else setError(t("lab.parseError"));
      setPhase("pick");
    }
  };

  const unchecked = fields.filter((f) => f.implausible && !checked.has(f.code));
  const confirm = async () => {
    if (!patientId || unchecked.length) return;
    setSaving(true);
    try {
      const res = await api.labConfirm(patientId, fields.map((f) => ({ ...f, implausible: false })));
      setResult(res);
      setPhase("saved");
      // A confirmed HbA1c/BMI is a new covariate revision: the twin re-personalises, so refetch everything.
      void qc.invalidateQueries();
    } catch {
      toast(t("errors.generic"), "error");
    } finally {
      setSaving(false);
    }
  };

  const download = async () => {
    if (!patientId) return;
    try {
      const bundle = await api.fhirBundle(patientId);
      const blob = new Blob([JSON.stringify(bundle, null, 2)], { type: "application/fhir+json" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `fhir-bundle-${patientId}.json`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch {
      toast(t("errors.generic"), "error");
    }
  };

  return (
    <section className="card p-5 sm:p-6" aria-labelledby="lab-title">
      <h2 id="lab-title" className="text-lg font-bold">
        {t("lab.title")}
      </h2>
      <p className="mt-1 text-sm text-ink-2">{t("lab.subtitle")}</p>
      <input ref={fileRef} type="file" accept="image/*,application/pdf" className="sr-only" tabIndex={-1} aria-hidden onChange={(e) => {
          const f = e.target.files?.[0];
          e.target.value = ""; // allow picking the same file again after an error
          if (f) void parse({ file: f });
        }} />
      {error && (
        <div className="mt-4">
          <ErrorState message={error} />
        </div>
      )}
      <AnimatePresence mode="wait">
        {phase === "pick" && (
          <motion.div key="pick" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="mt-4">
            <div className="flex flex-wrap items-center gap-3">
              <button type="button" className="btn-primary" onClick={() => fileRef.current?.click()}>
                <FileUp size={17} aria-hidden />
                {t("lab.upload")}
              </button>
              <span className="text-sm text-ink-3">{t("lab.orSample")}</span>
            </div>
            <div className="mt-3 grid gap-2 sm:grid-cols-2">
              {samples.isLoading && [0, 1].map((i) => <span key={i} className="skeleton h-16" />)}
              {samples.data?.map((s) => (
                <button
                  key={s.id}
                  type="button"
                  onClick={() => void parse({ sample_id: s.id })}
                  className="flex items-center gap-3 rounded-2xl border border-line bg-card p-2 pr-3.5 text-left text-sm font-semibold leading-snug transition hover:border-marigold-ink/50 hover:bg-paper-2"
                >
                  {mediaUrl(s.image_url) && <img src={mediaUrl(s.image_url) ?? ""} alt="" className="h-14 w-11 shrink-0 rounded-lg border border-line object-cover" loading="lazy" />}
                  <span>{s.title}</span>
                </button>
              ))}
            </div>
          </motion.div>
        )}
        {phase === "parsing" && (
          <motion.p key="parsing" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="mt-4 flex items-center gap-2 font-semibold" role="status">
            <Loader2 size={18} className="animate-spin text-marigold-ink" aria-hidden />
            {t("lab.parsing")}
          </motion.p>
        )}
        {phase === "confirm" && (
          <motion.div key="confirm" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="mt-4">
            <div className="relative -mx-1 overflow-x-auto">
              <table className="w-full min-w-[680px] border-separate border-spacing-0 text-sm">
                <thead>
                  <tr className="text-left text-xs uppercase tracking-wide text-ink-3">
                    <th scope="col" className="border-b border-line px-2 py-2">
                      {t("lab.test")}
                    </th>
                    <th scope="col" className="border-b border-line px-2 py-2">
                      {t("lab.value")}
                    </th>
                    <th scope="col" className="border-b border-line px-2 py-2">
                      {t("lab.unit")}
                    </th>
                    <th scope="col" className="border-b border-line px-2 py-2">
                      {t("lab.asPrinted")}
                    </th>
                    <th scope="col" className="border-b border-line px-2 py-2">
                      {t("lab.ref")}
                    </th>
                    <th scope="col" className="border-b border-line px-2 py-2">
                      {t("lab.collected")}
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {fields.map((f, i) => {
                    const flag = f.implausible && !checked.has(f.code);
                    return (
                      <tr key={`${f.code}-${i}`} className={flag ? "bg-coral/10" : ""}>
                        <td className="border-b border-line/70 px-2 py-2 font-semibold">
                          {f.name}
                          {f.loinc && <span className="ml-1.5 font-mono text-[0.7rem] font-normal text-ink-3">LOINC {f.loinc}</span>}
                          {flag && (
                            <span className="mt-1 flex items-center gap-1 text-xs font-semibold text-coral-ink">
                              <AlertTriangle size={12} aria-hidden />
                              {t("lab.implausible")}
                            </span>
                          )}
                        </td>
                        <td className="border-b border-line/70 px-2 py-2">
                          <input
                            aria-label={t("lab.editValue", { name: f.name })}
                            value={String(f.value)}
                            onChange={(e) => {
                              const raw = e.target.value;
                              const n = Number(raw);
                              setFields((fs) => fs.map((x, j) => (j === i ? { ...x, value: typeof x.value === "number" && raw.trim() !== "" && Number.isFinite(n) ? n : raw } : x)));
                              if (f.implausible) setChecked((c) => new Set(c).add(f.code));
                            }}
                            className={`num w-full min-w-[90px] rounded-xl border px-2.5 py-1.5 ${flag ? "border-coral-ink bg-card" : "border-line bg-card"}`}
                          />
                          {flag && (
                            <button type="button" className="mt-1 text-xs font-semibold text-ink-2 underline" onClick={() => setChecked((c) => new Set(c).add(f.code))}>
                              <CheckCircle2 size={12} className="mr-1 inline" aria-hidden />
                              {t("common.done")}
                            </button>
                          )}
                        </td>
                        <td className="border-b border-line/70 px-2 py-2 text-ink-2">{f.unit}</td>
                        <td className="num border-b border-line/70 px-2 py-2 text-xs text-ink-3">
                          {f.original_value !== undefined && f.original_value !== null ? `${f.original_value} ${f.original_unit ?? ""}`.trim() : "—"}
                          {f.original_unit && f.original_unit !== f.unit && <span className="block text-[0.65rem] text-teal-ink">{t("lab.converted")}</span>}
                        </td>
                        <td className="num border-b border-line/70 px-2 py-2 text-ink-3">{f.ref_range}</td>
                        <td className="num border-b border-line/70 px-2 py-2 text-xs text-ink-3">{f.collection_date ? formatDateTime(f.collection_date, i18n.language) : "—"}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            <p className="mt-3 text-xs text-ink-3">
              {diagnoses && diagnoses.length > 0 ? t("lab.diagnosesListed", { list: diagnoses.join(", ") }) : t("lab.noDiagnosis")}
            </p>
            <p className="mt-1 text-xs text-ink-3">{t("lab.modelFields")}</p>
            {unchecked.length > 0 && <p className="mt-3 text-sm font-semibold text-coral-ink">{t("lab.checkFlagged")}</p>}
            <div className="mt-4 flex flex-wrap gap-2">
              <button type="button" className="btn-primary" disabled={saving || unchecked.length > 0} onClick={() => void confirm()}>
                {saving && <Loader2 size={16} className="animate-spin" aria-hidden />}
                {saving ? t("lab.saving") : t("lab.confirm")}
              </button>
              <button type="button" className="btn-ghost" onClick={() => setPhase("pick")}>
                {t("common.cancel")}
              </button>
            </div>
          </motion.div>
        )}
        {phase === "saved" && result && (
          <motion.div key="saved" initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="mt-4 flex flex-wrap items-center gap-3">
            <p className="flex items-center gap-2 font-semibold text-teal-ink" role="status">
              <CheckCircle2 size={18} aria-hidden />
              {t("lab.saved", { n: result.resource_count })}
            </p>
            <code className="rounded-lg bg-paper-2 px-2 py-1 text-xs text-ink-2">{result.bundle_id}</code>
            {result.revision !== undefined && result.revision !== null && (
              <p className="w-full text-sm text-ink-2">
                {t("lab.revisionMade", { n: typeof result.revision === "object" ? String((result.revision as { revision?: unknown }).revision ?? "") : String(result.revision) })}
              </p>
            )}
            <button type="button" className="btn-primary" onClick={() => void download()}>
              <Download size={16} aria-hidden />
              {t("lab.download")}
            </button>
            <button type="button" className="btn-ghost" onClick={() => setPhase("pick")}>
              <RotateCcw size={16} aria-hidden />
              {t("lab.again")}
            </button>
          </motion.div>
        )}
      </AnimatePresence>
    </section>
  );
}

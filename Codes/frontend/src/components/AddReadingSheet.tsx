import { useEffect, useRef, useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { Loader2 } from "lucide-react";
import type { Assimilation, GlucoseUnit, Ladder } from "@/api/types";
import { useAssimilate } from "@/api/hooks";
import { ApiError, UnreachableError } from "@/api/http";
import { checkReading, UNIT_RANGE } from "@/lib/units";
import { isoMinusMinutes } from "@/lib/replay";
import { formatClock } from "@/lib/format";
import { isUrgent } from "@/lib/evidence";
import { useApp } from "@/store/app";
import { Modal } from "./ui";

interface Props {
  open: boolean;
  onClose: () => void;
  patientId: string | null;
  ladder: Ladder;
  /** The replay "now" the reading is timed against (never the wall clock). */
  replayNow: string | null;
  onAssimilated: (a: Assimilation, mgdl: number) => void;
}

const WHEN = [0, 15, 30] as const;
/** Optional symptoms, sent as plain English words the shared safety policy reads in any UI language. */
const SYMPTOMS = ["shaky", "sweating", "dizzy", "confused", "vomiting", "drowsy"] as const;
const newKey = () =>
  typeof crypto !== "undefined" && "randomUUID" in crypto ? crypto.randomUUID() : `k-${Date.now()}-${Math.random().toString(36).slice(2)}`;

/**
 * Add a measured reading. Starts EMPTY and needs both a value and an explicit unit: a forecast
 * is never offered as a measurement. The shared safety result takes priority over success.
 */
export function AddReadingSheet({ open, onClose, patientId, ladder, replayNow, onAssimilated }: Props) {
  const { t, i18n } = useTranslation();
  const [value, setValue] = useState("");
  const [unit, setUnit] = useState<GlucoseUnit | null>(null);
  const [ago, setAgo] = useState<number | "custom">(0);
  const [customTime, setCustomTime] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [sym, setSym] = useState<Set<string>>(new Set());
  const key = useRef(newKey());
  const m = useAssimilate(patientId, ladder);
  const showSafety = useApp((s) => s.showSafety);

  useEffect(() => {
    if (open) {
      setValue("");
      setUnit(null);
      setAgo(0);
      setCustomTime("");
      setError(null);
      setSym(new Set());
      key.current = newKey();
    }
  }, [open]);

  const observedAt = (): string | undefined => {
    if (!replayNow) return undefined;
    if (ago === "custom") {
      const hm = /^(\d{1,2}):(\d{2})$/.exec(customTime);
      if (!hm) return undefined;
      return `${replayNow.slice(0, 10)}T${hm[1].padStart(2, "0")}:${hm[2]}:00`;
    }
    return ago === 0 ? replayNow.slice(0, 19) : isoMinusMinutes(replayNow, ago);
  };

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (m.isPending) return; // repeated clicks
    const chk = checkReading(value, unit);
    if (!chk.ok) {
      const r = unit ? UNIT_RANGE[unit] : UNIT_RANGE["mg/dL"];
      setError(chk.reason === "unit" ? t("reading.needUnit") : chk.reason === "empty" ? t("reading.needValue") : t("reading.invalidRange", { min: r.min, max: r.max, unit: unit ?? "mg/dL" }));
      return;
    }
    if (ago === "custom" && !observedAt()) {
      setError(t("reading.needTime"));
      return;
    }
    try {
      const res = await m.mutateAsync({
        value: chk.value,
        unit: unit as GlucoseUnit,
        observed_at: observedAt(),
        idempotency_key: key.current,
        ...(sym.size ? { symptoms: [...sym].join(", ") } : {}),
      });
      onClose();
      // Safety first: a low or high reading is shown before (and instead of) any success message.
      if (res.safety && isUrgent(res.safety.level)) showSafety(res.safety);
      onAssimilated(res, chk.mgdl);
    } catch (err) {
      if (err instanceof ApiError && err.status === 422 && (err.code === "stale_observation" || /stale|30 min/i.test(err.message))) setError(t("reading.stale"));
      else if (err instanceof ApiError && err.status === 429) setError(t("errors.rateLimited", { s: err.retryAfter ?? 30 }));
      else if (err instanceof UnreachableError) setError(t("errors.network"));
      else setError(t("reading.failed"));
    }
  };

  const unitBtn = (u: GlucoseUnit) => (
    <button
      key={u}
      type="button"
      role="radio"
      aria-checked={unit === u}
      onClick={() => {
        setUnit(u);
        setError(null);
      }}
      className={`min-h-[44px] flex-1 rounded-full px-4 text-sm font-bold transition ${unit === u ? "bg-ink text-paper" : "text-ink-2 hover:bg-paper-2"}`}
    >
      {u}
    </button>
  );

  return (
    <Modal open={open} onClose={onClose} title={t("reading.title")} subtitle={t("reading.hint")}>
      <form onSubmit={submit} className="space-y-5 pt-2" noValidate>
        <div>
          <label htmlFor="reading-value" className="block text-sm font-semibold text-ink-2">
            {t("reading.label")}
          </label>
          <input
            id="reading-value"
            data-autofocus
            inputMode="decimal"
            autoComplete="off"
            value={value}
            placeholder={t("reading.placeholder")}
            onChange={(e) => {
              setValue(e.target.value.replace(/[^0-9.,०-९০-৯೦-೯]/g, "").slice(0, 5));
              setError(null);
            }}
            aria-invalid={!!error}
            aria-describedby={error ? "reading-error" : "reading-help"}
            className="num mt-2 w-full rounded-3xl border border-line bg-card py-3 text-center text-5xl font-extrabold tracking-tight text-ink placeholder:text-2xl placeholder:font-semibold placeholder:text-ink-3 focus:border-marigold-ink focus:outline-none focus:ring-4 focus:ring-marigold/30"
          />
          <p id="reading-help" className="mt-1.5 text-xs text-ink-3">
            {t("reading.neverPrefilled")}
          </p>
        </div>

        <div>
          <p id="unit-label" className="text-sm font-semibold text-ink-2">
            {t("reading.unit")}
          </p>
          <div role="radiogroup" aria-labelledby="unit-label" aria-required="true" className="mt-2 flex gap-1 rounded-full border border-line bg-card p-1">
            {unitBtn("mg/dL")}
            {unitBtn("mmol/L")}
          </div>
        </div>

        <fieldset>
          <legend className="text-sm font-semibold text-ink-2">{t("reading.when")}</legend>
          <div className="mt-2 flex flex-wrap gap-2">
            {WHEN.map((w) => (
              <button
                key={w}
                type="button"
                aria-pressed={ago === w}
                onClick={() => setAgo(w)}
                className={`chip ${ago === w ? "border-ink bg-ink text-paper" : "border-line bg-card text-ink hover:bg-paper-2"}`}
              >
                {w === 0 ? t("reading.justNow") : t("reading.minAgo", { n: w })}
              </button>
            ))}
            <button
              type="button"
              aria-pressed={ago === "custom"}
              onClick={() => setAgo("custom")}
              className={`chip ${ago === "custom" ? "border-ink bg-ink text-paper" : "border-line bg-card text-ink hover:bg-paper-2"}`}
            >
              {t("reading.earlier")}
            </button>
          </div>
          {ago === "custom" && (
            <div className="mt-3">
              <label htmlFor="reading-time" className="text-xs font-semibold text-ink-2">
                {t("reading.timeLabel")}
              </label>
              <input id="reading-time" type="time" value={customTime} onChange={(e) => setCustomTime(e.target.value)} className="field mt-1 w-40" />
            </div>
          )}
          {replayNow && <p className="mt-2 text-xs text-ink-3">{t("reading.replayTimeNote", { time: formatClock(replayNow, i18n.language) })}</p>}
        </fieldset>

        <fieldset>
          <legend className="text-sm font-semibold text-ink-2">{t("reading.symptoms")}</legend>
          <div className="mt-2 flex flex-wrap gap-1.5">
            {SYMPTOMS.map((k) => {
              const on = sym.has(k);
              return (
                <button
                  key={k}
                  type="button"
                  aria-pressed={on}
                  onClick={() =>
                    setSym((cur) => {
                      const n = new Set(cur);
                      if (n.has(k)) n.delete(k);
                      else n.add(k);
                      return n;
                    })
                  }
                  className={`chip min-h-[34px] text-xs ${on ? "border-coral-ink bg-coral/15 text-coral-ink" : "border-line bg-card text-ink-2 hover:bg-paper-2"}`}
                >
                  {t(`reading.sym.${k}`)}
                </button>
              );
            })}
          </div>
        </fieldset>

        {error && (
          <p id="reading-error" role="alert" className="rounded-2xl bg-coral/10 px-4 py-2.5 text-sm font-semibold text-coral-ink">
            {error}
          </p>
        )}
        <button type="submit" className="btn-primary h-12 w-full text-base" disabled={m.isPending} aria-busy={m.isPending}>
          {m.isPending && <Loader2 size={18} className="animate-spin" aria-hidden />}
          {m.isPending ? t("reading.submitting") : t("reading.submit")}
        </button>
      </form>
    </Modal>
  );
}

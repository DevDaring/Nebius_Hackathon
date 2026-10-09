import { useEffect, useRef, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { AnimatePresence, m as motion } from "framer-motion";
import { useQueryClient } from "@tanstack/react-query";
import { AlertOctagon, AlertTriangle, BookOpen, Check, CheckCircle2, ClipboardCheck, Droplet, ExternalLink, HelpCircle, Info, Loader2, Phone, Send, ShieldAlert, ShieldOff, Sparkles, X } from "lucide-react";
import { api } from "@/api";
import { ApiError } from "@/api/http";
import type { AgentReply, Clarification, Disclosure, Lang, PendingAction, References, Safety, ToolCall } from "@/api/types";
import { DISCLOSURE_KINDS, LANGS } from "@/api/types";
import { isUrgent } from "@/lib/evidence";
import { samplesFor } from "@/lib/voicePrompts";
import { useActivePatientId, useTwinState, useVoiceSamples } from "@/api/hooks";
import { GlucoseRiver } from "@/charts/GlucoseRiver";
import { LANG_LABELS } from "@/i18n";
import { replySource } from "@/lib/replySource";
import { formatReplayTime } from "@/lib/format";
import { isEnglish } from "@/lib/langPrefs";
import { PoweredBy } from "@/components/PoweredBy";
import { useApp } from "@/store/app";

interface Turn {
  id: number;
  who: "you" | "twin";
  text: string;
  lang: Lang;
  reply?: AgentReply;
}

/** "Log a reading of 150 mg/dL?" card: nothing changes until the user confirms */
function ConfirmCard({ action, busy, done, onConfirm }: { action: PendingAction; busy: boolean; done: "confirmed" | "cancelled" | null; onConfirm: (ok: boolean) => void }) {
  const { t, i18n } = useTranslation();
  const p = action.payload ?? {};
  const value = typeof p.value === "number" || typeof p.value === "string" ? String(p.value) : null;
  const unit = typeof p.unit === "string" ? p.unit : "mg/dL";
  const summary =
    action.kind === "log_reading" && value
      ? t("voice.confirmReading", { value, unit })
      : action.kind === "log_meal"
        ? t("voice.confirmMeal", { name: String(p.name ?? p.meal ?? ""), carbs: p.carbs !== undefined ? String(p.carbs) : "?" })
        : isEnglish(i18n.language)
          ? action.summary_en
          : t("voice.confirmGeneric");
  return (
    <div className="mt-3 rounded-2xl border border-marigold/60 bg-night/60 p-3" role="group" aria-label={t("voice.confirmTitle")}>
      <p className="flex items-center gap-1.5 text-xs font-bold uppercase tracking-wide text-marigold">
        <ClipboardCheck size={13} aria-hidden />
        {t("voice.confirmTitle")}
      </p>
      <p className="mt-1 text-base font-semibold text-moon">{summary}</p>
      <dl className="mt-1 grid grid-cols-[auto_1fr] gap-x-3 text-xs text-moon-2">
        {Object.entries(p)
          .filter(([, v]) => v !== null && v !== undefined && typeof v !== "object")
          .map(([k, v]) => (
            <div key={k} className="contents">
              <dt className="font-mono text-moon-3" lang="en">
                {k}
              </dt>
              <dd className="num">{String(v)}</dd>
            </div>
          ))}
      </dl>
      {done ? (
        <p className="mt-2 text-sm font-semibold text-moon-2">{done === "confirmed" ? t("voice.confirmed") : t("voice.cancelledAction")}</p>
      ) : (
        <div className="mt-3 flex gap-2">
          <button type="button" className="btn-marigold h-10 min-h-0 flex-1 text-sm" disabled={busy} onClick={() => onConfirm(true)}>
            {busy ? <Loader2 size={15} className="animate-spin" aria-hidden /> : <Check size={15} aria-hidden />}
            {t("voice.confirmYes")}
          </button>
          <button type="button" className="btn-night h-10 min-h-0 flex-1 text-sm" disabled={busy} onClick={() => onConfirm(false)}>
            {t("voice.confirmNo")}
          </button>
        </div>
      )}
    </div>
  );
}

/** One short question before simulating: quick replies send their `text` as the next message. */
function ClarificationCard({ c, lang, disabled, onAnswer }: { c: Clarification; lang: Lang; disabled: boolean; onAnswer: (text: string, skipSlots?: string[]) => void }) {
  const { t } = useTranslation();
  return (
    <div className="mt-3 rounded-2xl border border-teal/50 bg-night/50 p-3" role="group" aria-label={t("chat.clarifyTitle")} data-clarification={c.slot}>
      <p className="flex items-center gap-1.5 text-xs font-bold uppercase tracking-wide text-teal">
        <HelpCircle size={13} aria-hidden />
        {t("chat.clarifyTitle")}
      </p>
      <p className="mt-1 text-base font-semibold text-moon" lang={lang}>
        {c.question}
      </p>
      <div className="mt-2.5 flex flex-wrap gap-2">
        {c.options.map((o) => (
          <button key={o.text} type="button" disabled={disabled} onClick={() => onAnswer(o.text)} lang={lang} className="chip min-h-[40px] border-teal/60 bg-teal/10 text-moon hover:bg-teal/20 disabled:opacity-50">
            {o.label}
          </button>
        ))}
        {c.skip && (
          <button type="button" disabled={disabled} onClick={() => onAnswer(c.skip!.text, c.skip!.skip_slots ?? [c.slot])} lang={lang} className="chip min-h-[40px] border-night-line text-moon-2 hover:text-moon disabled:opacity-50" data-clarification-skip>
            {c.skip.label || t("chat.skip")}
          </button>
        )}
      </div>
      {c.skip && <p className="mt-2 text-xs text-moon-3">{t("chat.skipHint")}</p>}
    </div>
  );
}

/** Labelled notes under a reply (stale data, exploratory, ranking uncertain…). Never hidden. */
function Disclosures({ items, lang }: { items: Disclosure[]; lang: Lang }) {
  const { t } = useTranslation();
  if (!items.length) return null;
  return (
    <ul className="mt-2.5 space-y-1.5" aria-label={t("chat.disclosuresTitle")}>
      {items.map((d, i) => {
        const known = (DISCLOSURE_KINDS as string[]).includes(d.kind);
        return (
          <li key={`${d.kind}-${i}`} className="flex items-start gap-2 rounded-xl border border-night-line/80 bg-night/40 px-2.5 py-1.5 text-xs text-moon-2" data-disclosure={d.kind}>
            <Info size={13} className="mt-0.5 shrink-0 text-marigold" aria-hidden />
            <span>
              <span className="font-bold text-moon">{known ? t(`chat.disclosure.${d.kind}`) : t("chat.disclosure.other")}:</span>{" "}
              <span lang={lang}>{d.text}</span>
            </span>
          </li>
        );
      })}
    </ul>
  );
}

/** Further reading from allowlisted public-health sites. Quotations with links; never part of the twin's answer. */
function FurtherReading({ refs }: { refs: References }) {
  const { t } = useTranslation();
  if (!refs.items.length) return null;
  return (
    <section className="mt-2.5 rounded-xl border border-night-line/80 bg-night/40 px-2.5 py-2" aria-label={t("chat.references.title")}>
      <p className="flex items-center gap-1.5 text-xs font-bold text-moon">
        <BookOpen size={13} className="shrink-0 text-teal" aria-hidden />
        {t("chat.references.title")}
      </p>
      <ul className="mt-1.5 space-y-1.5">
        {refs.items.map((r) => (
          <li key={r.url} className="text-xs text-moon-2">
            <a
              href={r.url}
              target="_blank"
              rel="noopener noreferrer nofollow"
              className="inline-flex items-center gap-1 font-semibold text-teal underline-offset-2 hover:underline"
            >
              {r.title}
              <ExternalLink size={11} aria-hidden />
              <span className="sr-only">{t("chat.references.opensNewTab")}</span>
            </a>
            <span className="ml-1 text-moon-3">· {r.domain}</span>
            {r.snippet && <q className="mt-0.5 block text-moon-3">{r.snippet}</q>}
          </li>
        ))}
      </ul>
      <p className="mt-1.5 text-[0.7rem] text-moon-3">{t("chat.references.note")}</p>
    </section>
  );
}

/** A non-ok safety result carried in a reply's tool outputs (logged reading). */
function safetyOf(reply: AgentReply): Safety | null {
  for (const c of reply.tool_calls ?? []) {
    const o = c.output as { safety?: Safety } | null;
    if (o && typeof o === "object" && o.safety && typeof o.safety === "object" && "level" in o.safety) return o.safety;
  }
  return null;
}

/** The forecast an answer is about (tool output), else null. */
function forecastIdOf(calls: ToolCall[] | undefined): string | null {
  for (const c of calls ?? []) {
    const o = c.output as { forecast_id?: unknown } | null;
    if (o && typeof o === "object" && typeof o.forecast_id === "string") return o.forecast_id;
  }
  return null;
}

/* ---------------- page ---------------- */
/**
 * Talk to your twin: text-first chat. There is no microphone, no server speech and no browser Web
 * Speech: Nebius Token Factory has no speech model, and browser recognition would send audio to a
 * third party. Everything is keyboard accessible.
 */
export default function VoicePage() {
  const { t, i18n } = useTranslation();
  const appLang = useApp((s) => s.lang);
  const ladder = useApp((s) => s.ladder);
  const highlight = useApp((s) => s.highlight);
  const setHighlight = useApp((s) => s.setHighlight);
  const setToolCalls = useApp((s) => s.setLastToolCalls);
  const openWhy = useApp((s) => s.openWhy);
  const showSafety = useApp((st) => st.showSafety);
  const pid = useActivePatientId();
  const pidNow = useRef(pid);
  pidNow.current = pid;
  const state = useTwinState(pid, ladder);
  const samples = useVoiceSamples();
  const qc = useQueryClient();

  const [lang, setLang] = useState<Lang>(appLang);
  useEffect(() => setLang(appLang), [appLang]);
  const [turns, setTurns] = useState<Turn[]>([]);
  const [notice, setNotice] = useState<string | null>(null);
  const [typed, setTyped] = useState("");
  const [thinking, setThinking] = useState(false);
  const [confirmBusy, setConfirmBusy] = useState<string | null>(null);
  const [actionDone, setActionDone] = useState<Record<string, "confirmed" | "cancelled">>({});
  const [answered, setAnswered] = useState<Record<number, boolean>>({});
  const abortRef = useRef<AbortController | null>(null);
  const runId = useRef(0);
  const seq = useRef(0);
  const listRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const push = (turn: Omit<Turn, "id">) => setTurns((ts) => [...ts, { ...turn, id: ++seq.current }]);

  useEffect(() => {
    listRef.current?.lastElementChild?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }, [turns]);
  useEffect(() => () => abortRef.current?.abort(), []);

  const cancel = () => {
    runId.current += 1;
    abortRef.current?.abort();
    abortRef.current = null;
    setThinking(false);
  };

  const ask = async (text: string, skipSlots?: string[]) => {
    const q = text.trim();
    if (!q || !pid) return;
    const run = ++runId.current;
    const askedFor = pid;
    push({ who: "you", text: q, lang });
    setThinking(true);
    setNotice(null);
    const ctrl = new AbortController();
    abortRef.current = ctrl;
    try {
      const reply = await api.agentChat({ patient_id: pid, text: q, lang, ladder, ...(skipSlots?.length ? { skip_slots: skipSlots } : {}) }, ctrl.signal);
      if (run !== runId.current || askedFor !== pidNow.current) return; // cancelled or persona switched
      push({ who: "twin", text: reply.reply, lang: reply.lang ?? lang, reply });
      setToolCalls(reply.tool_calls ?? []);
      setHighlight(reply.highlight?.view && reply.highlight.view !== "none" ? reply.highlight : null);
    } catch (e) {
      if (run !== runId.current || (e as Error).name === "AbortError") return;
      setNotice(e instanceof ApiError && e.status === 429 ? t("errors.rateLimited", { s: e.retryAfter ?? 30 }) : t("voice.error"));
    } finally {
      if (run === runId.current) setThinking(false);
      if (abortRef.current === ctrl) abortRef.current = null;
    }
  };

  const confirmAction = async (action: PendingAction, ok: boolean) => {
    if (confirmBusy) return;
    setConfirmBusy(action.id);
    try {
      const reply = await api.agentConfirm({ action_id: action.id, confirm: ok, lang });
      setActionDone((d) => ({ ...d, [action.id]: ok ? "confirmed" : "cancelled" }));
      push({ who: "twin", text: reply.reply, lang: reply.lang ?? lang, reply });
      if (ok) {
        const sft = safetyOf(reply);
        if (sft && isUrgent(sft.level)) showSafety(sft);
        void qc.invalidateQueries();
      }
    } catch {
      setNotice(t("voice.error"));
    } finally {
      setConfirmBusy(null);
    }
  };

  const submitTyped = (e: FormEvent) => {
    e.preventDefault();
    const q = typed;
    setTyped("");
    void ask(q);
  };

  const langSamples = samplesFor(lang, samples.data);
  const lastTwin = [...turns].reverse().find((x) => x.who === "twin")?.reply;
  const hl = highlight;
  const s = state.data;
  const replayNow = s?.replay?.now ?? s?.now ?? null;

  return (
    <div className="stage stage-wave on-night min-h-[calc(100dvh-4rem)]">
      <div className="mx-auto grid max-w-7xl gap-8 px-4 pb-10 pt-6 sm:px-6 lg:grid-cols-[1fr_1.05fr]">
        {/* ---------------- left: ask ---------------- */}
        <section aria-labelledby="voice-title" className="flex flex-col">
          <h1 id="voice-title" className="text-2xl font-extrabold text-moon sm:text-3xl">
            {t("voice.title")}
          </h1>
          <p className="mt-1 max-w-md text-moon-2">{t("chat.subtitle")}</p>

          <div role="radiogroup" aria-label={t("voice.answerLang")} className="mt-5 flex flex-wrap gap-2">
            {LANGS.map((l) => (
              <button
                key={l}
                type="button"
                role="radio"
                aria-checked={lang === l}
                lang={l}
                onClick={() => setLang(l)}
                className={`chip min-h-[40px] px-4 ${lang === l ? "border-marigold bg-marigold text-night" : "border-night-line text-moon-2 hover:text-moon"}`}
              >
                {LANG_LABELS[l].native}
              </button>
            ))}
          </div>

          <form onSubmit={submitTyped} className="mt-5 flex w-full max-w-lg gap-2" data-tour="voice-orb">
            <label htmlFor="typed" className="sr-only">
              {t("voice.typeLabel")}
            </label>
            <input
              id="typed"
              ref={inputRef}
              lang={lang}
              value={typed}
              onChange={(e) => setTyped(e.target.value)}
              placeholder={t("voice.typePlaceholder")}
              autoComplete="off"
              className="min-h-[48px] flex-1 rounded-full border border-night-line bg-night-2 px-5 text-moon placeholder:text-moon-3 focus:border-marigold focus:outline-none focus:ring-2 focus:ring-marigold/40"
            />
            <button type="submit" className="btn-marigold h-12 w-12 p-0" aria-label={t("voice.send")} disabled={!typed.trim() || thinking}>
              <Send size={18} aria-hidden />
            </button>
          </form>
          <div className="mt-2 min-h-[1.75rem]" role="status" aria-live="polite">
            {thinking && (
              <span className="inline-flex items-center gap-2 text-sm font-semibold text-moon-2">
                <Loader2 size={15} className="animate-spin" aria-hidden />
                {t("voice.thinking")}
                <button type="button" onClick={cancel} className="ml-1 inline-flex items-center gap-1 rounded-full border border-coral-night/60 px-2.5 py-0.5 text-xs font-bold text-coral-night hover:bg-coral/10">
                  <X size={12} aria-hidden />
                  {t("common.cancel")}
                </button>
              </span>
            )}
          </div>
          {notice && (
            <p role="alert" className="mt-1 max-w-md rounded-2xl bg-night-2 px-4 py-2.5 text-sm text-moon">
              {notice}
            </p>
          )}

          <div className="mt-5 w-full max-w-lg">
            <p className="eyebrow mb-2 text-moon-3">{t("voice.samples")}</p>
            <div className="flex flex-wrap gap-2">
              {samples.isLoading && <span className="skeleton-night h-10 w-60" />}
              {!samples.isLoading &&
                langSamples.map((sm, i) => (
                  <button
                    key={`${sm.lang}-${i}`}
                    type="button"
                    lang={sm.lang}
                    disabled={thinking}
                    onClick={() => void ask(sm.prompt)}
                    className="chip min-h-[44px] border-night-line bg-night-2/70 text-left text-moon hover:border-marigold/60 disabled:opacity-50"
                  >
                    <Sparkles size={14} className="shrink-0 text-marigold" aria-hidden />
                    {sm.prompt}
                  </button>
                ))}
            </div>
          </div>
          <PoweredBy tone="night" className="mt-6" />
        </section>

        {/* ---------------- right: conversation + chart ---------------- */}
        <section aria-label={t("voice.twin")} className="flex min-w-0 flex-col gap-4">
          <div className="stage-card p-3 sm:p-4">
            {s ? <GlucoseRiver state={s} rangeHours={6} compact highlight={hl && (hl.view === "stage" || hl.view === "forecast") ? hl : null} /> : <div className="skeleton-night h-[210px]" />}
            <AnimatePresence>
              {lastTwin && lastTwin.highlight?.view !== "none" && (
                <motion.div initial={{ opacity: 0, y: 4 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} className="mt-2 flex flex-wrap items-center gap-2 px-1 text-sm">
                  {(lastTwin.highlight.view === "stage" || lastTwin.highlight.view === "forecast") && lastTwin.highlight.from && <span className="text-marigold">{t("voice.showOnChart")}</span>}
                  {lastTwin.highlight.view === "whatif" && (
                    <Link to="/whatif" className="btn-night h-10 min-h-0">
                      <Sparkles size={15} aria-hidden />
                      {t("voice.openWhatIf")}
                    </Link>
                  )}
                  {lastTwin.highlight.view === "nbp" && s && (
                    <Link to="/" className="inline-flex items-center gap-2 rounded-2xl bg-marigold/15 px-3 py-2 font-semibold text-marigold ring-1 ring-marigold/60">
                      <Droplet size={15} aria-hidden />
                      {t("nbp.headline", { time: formatReplayTime(t, s.next_best_prick.time, replayNow, i18n.language) })}
                    </Link>
                  )}
                </motion.div>
              )}
            </AnimatePresence>
          </div>

          <div ref={listRef} className="flex flex-col gap-3" aria-live="polite">
            {turns.length === 0 && <p className="stage-card p-5 text-moon-2">{t("voice.empty")}</p>}
            {turns.map((tu, idx) =>
              tu.who === "you" ? (
                <motion.div key={tu.id} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} className="ml-auto max-w-[85%] rounded-3xl rounded-br-lg bg-moon px-4 py-3 text-night">
                  <p className="text-xs font-semibold text-night/60">{t("voice.you")}</p>
                  <p lang={tu.lang} className="text-[1.05rem]">
                    {tu.text}
                  </p>
                </motion.div>
              ) : (
                <motion.div
                  key={tu.id}
                  initial={{ opacity: 0, y: 6 }}
                  animate={{ opacity: 1, y: 0 }}
                  className={`max-w-[92%] rounded-3xl rounded-bl-lg px-4 py-3 ${tu.reply?.safety.emergency ? "bg-[rgb(176_56_40)] text-white" : "border border-night-line bg-night-2 text-moon"}`}
                >
                  <p className={`flex items-center gap-2 text-xs font-semibold ${tu.reply?.safety.emergency ? "text-white" : "text-marigold"}`}>
                    {tu.reply?.safety.emergency ? <AlertOctagon size={14} aria-hidden /> : null}
                    {tu.reply?.safety.emergency ? t("voice.emergency") : t("voice.twin")}
                  </p>
                  {!(tu.reply?.clarification && tu.reply.clarification.question === tu.text) && (
                    <p lang={tu.lang} className="mt-0.5 text-[1.08rem] leading-relaxed">
                      {tu.text}
                    </p>
                  )}
                  {tu.reply?.clarification && (
                    <ClarificationCard
                      c={tu.reply.clarification}
                      lang={tu.lang}
                      disabled={thinking || !!answered[idx] || idx !== turns.length - 1}
                      onAnswer={(text, skipSlots) => {
                        setAnswered((a) => ({ ...a, [idx]: true }));
                        void ask(text, skipSlots);
                      }}
                    />
                  )}
                  {tu.reply?.pending_action && (
                    <ConfirmCard
                      action={tu.reply.pending_action}
                      busy={confirmBusy === tu.reply.pending_action.id}
                      done={actionDone[tu.reply.pending_action.id] ?? null}
                      onConfirm={(ok) => void confirmAction(tu.reply!.pending_action!, ok)}
                    />
                  )}
                  {tu.reply?.disclosures && <Disclosures items={tu.reply.disclosures} lang={tu.lang} />}
                  {tu.reply?.references && <FurtherReading refs={tu.reply.references} />}
                  {tu.reply?.claims && tu.reply.claims.length > 0 && (
                    <details className="mt-2 text-xs opacity-90">
                      <summary className="cursor-pointer font-semibold">{t("voice.claimsTitle", { n: tu.reply.claims.length })}</summary>
                      <ul className="mt-1 space-y-0.5">
                        {tu.reply.claims.map((c, i) => (
                          <li key={i} className="flex flex-wrap gap-x-2">
                            <span className="num font-semibold">{c.rendered}</span>
                            <span className="font-mono opacity-75" lang="en">
                              ← {c.field}
                            </span>
                          </li>
                        ))}
                      </ul>
                    </details>
                  )}
                  {tu.reply && <ReplyFooter reply={tu.reply} onWhy={() => {
                        const own = forecastIdOf(tu.reply?.tool_calls);
                        // a chat answer's own forecast cannot be re-created; the current state forecast can
                        const refresh = own ? undefined : async () => (await state.refetch()).data?.forecast.forecast_id ?? null;
                        openWhy(own ?? s?.forecast.forecast_id ?? null, tu.reply?.tool_calls ?? [], tu.reply, refresh);
                      }} />}
                </motion.div>
              ),
            )}
          </div>
        </section>
      </div>
    </div>
  );
}

/** Status line under a reply: safety / number check / source, and the "Why this answer?" drawer. */
function ReplyFooter({ reply, onWhy }: { reply: AgentReply; onWhy: () => void }) {
  const { t } = useTranslation();
  const src = replySource(reply);
  const numbers = reply.checks?.numbers;
  return (
    <div className="mt-2.5 flex flex-wrap items-center gap-x-3 gap-y-1.5 text-xs">
      {reply.safety.emergency ? (
        <span className="inline-flex items-center gap-1.5 rounded-full bg-white px-3 py-1.5 font-bold text-[rgb(176_56_40)]">
          <Phone size={14} aria-hidden />
          {t("safety.callLocal")}
        </span>
      ) : reply.safety.blocked ? (
        <span className="inline-flex items-center gap-1 text-moon-2">
          <ShieldOff size={13} aria-hidden />
          {t("voice.blocked")}
        </span>
      ) : numbers === "passed" ? (
        // "All numbers checked" only when the deterministic check reports "passed".
        <span className="inline-flex items-center gap-1 text-teal" title={reply.grounding?.numbers?.length ? reply.grounding.numbers.join(", ") : undefined} data-numbers-checked>
          <CheckCircle2 size={13} aria-hidden />
          {t("voice.grounded")}
        </span>
      ) : numbers === "failed" ? (
        <span className="inline-flex items-center gap-1 text-coral-night">
          <AlertTriangle size={13} aria-hidden />
          {t("voice.notVerified")}
        </span>
      ) : null}
      {reply.safety.injection && (
        <span className="inline-flex items-center gap-1 text-moon-2">
          <ShieldAlert size={13} aria-hidden />
          {t("voice.injection")}
        </span>
      )}
      {(reply.source || reply.source_detail || reply.model) && (
        <span className="rounded-full border border-night-line px-2 py-0.5 text-[0.68rem] text-moon-3" title={src.detail ?? undefined}>
          {t(`voice.source.${reply.model ? (reply.model.live ? "live" : "template") : src.kind}`)}
          {(reply.model?.live ? reply.model.model_id?.split("/").pop() : src.model) && (
            <span lang="en" className="ml-1 opacity-80">
              · {reply.model?.live ? reply.model.model_id?.split("/").pop() : src.model}
            </span>
          )}
        </span>
      )}
      <button type="button" className="inline-flex items-center gap-1 font-semibold opacity-90 hover:opacity-100" onClick={onWhy}>
        <HelpCircle size={13} aria-hidden />
        {t("chat.whyAnswer")}
      </button>
    </div>
  );
}

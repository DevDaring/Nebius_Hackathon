import { useEffect, useLayoutEffect, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { AnimatePresence, m as motion, useReducedMotion } from "framer-motion";
import { ArrowLeft, ArrowRight, RotateCcw, X } from "lucide-react";
import { useTour } from "@/api/hooks";
import { useApp } from "@/store/app";
import { useResetDemo } from "@/hooks/useDemo";

interface Rect {
  top: number;
  left: number;
  width: number;
  height: number;
}

/**
 * Guided demo: steps come from GET /api/demo/tour. Each step navigates to its route and puts a
 * spotlight on the element marked data-tour="<action or id>". Text is localised when a
 * translation exists for the step id, else the backend's English text is shown.
 */
export function Tour() {
  const { t, i18n } = useTranslation();
  const active = useApp((s) => s.tourActive);
  const step = useApp((s) => s.tourStep);
  const setStep = useApp((s) => s.setTourStep);
  const end = useApp((s) => s.endTour);
  const navigate = useNavigate();
  const loc = useLocation();
  const reduce = useReducedMotion();
  const { data, isError } = useTour();
  const reset = useResetDemo();
  const steps = data?.steps ?? [];
  const cur = steps[step];
  const [rect, setRect] = useState<Rect | null>(null);

  useEffect(() => {
    if (active && cur && loc.pathname !== cur.route) navigate(cur.route);
  }, [active, cur, loc.pathname, navigate]);

  useLayoutEffect(() => {
    if (!active || !cur) return;
    setRect(null);
    let raf = 0;
    let tries = 0;
    let el: Element | null = null;
    const measure = () => {
      if (!el) return;
      const r = el.getBoundingClientRect();
      setRect({ top: r.top - 8, left: r.left - 8, width: r.width + 16, height: r.height + 16 });
    };
    const find = () => {
      el = document.querySelector(`[data-tour="${cur.action ?? cur.id}"]`) ?? document.querySelector(`[data-tour="${cur.id}"]`);
      if (el) {
        el.scrollIntoView({ block: "center", behavior: reduce ? "auto" : "smooth" });
        window.setTimeout(measure, reduce ? 0 : 420);
      } else if (tries++ < 90) raf = requestAnimationFrame(find);
    };
    find();
    const onChange = () => measure();
    window.addEventListener("resize", onChange);
    window.addEventListener("scroll", onChange, true);
    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener("resize", onChange);
      window.removeEventListener("scroll", onChange, true);
    };
  }, [active, cur, loc.pathname, reduce]);

  useEffect(() => {
    if (!active) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") end();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [active, end]);

  if (!active) return null;

  const title = cur ? (i18n.exists(`tour.steps.${cur.id}.title`) ? t(`tour.steps.${cur.id}.title`) : cur.title_en) : "";
  const body = cur ? (i18n.exists(`tour.steps.${cur.id}.body`) ? t(`tour.steps.${cur.id}.body`) : cur.body_en) : "";
  const last = step >= steps.length - 1;

  // Place the coachmark below the target if there is room, else above; centre when no target.
  const vh = typeof window !== "undefined" ? window.innerHeight : 800;
  const vw = typeof window !== "undefined" ? window.innerWidth : 1200;
  const cardW = Math.min(360, vw - 32);
  let cardStyle: React.CSSProperties = { left: (vw - cardW) / 2, top: vh / 2 - 110, width: cardW };
  if (rect) {
    const below = rect.top + rect.height + 14;
    const top = below + 230 < vh ? below : Math.max(12, rect.top - 244);
    const left = Math.min(Math.max(16, rect.left + rect.width / 2 - cardW / 2), vw - cardW - 16);
    cardStyle = { left, top, width: cardW };
  }

  return (
    <div className="pointer-events-none fixed inset-0 z-[70]" aria-live="polite">
      {rect ? (
        <motion.div
          className="pointer-events-none fixed rounded-3xl outline outline-[3px] outline-offset-0 outline-marigold"
          initial={false}
          animate={{ ...rect }}
          transition={reduce ? { duration: 0 } : { type: "spring", damping: 28, stiffness: 240 }}
          style={{ boxShadow: "0 0 0 9999px rgb(4 6 18 / 0.7), 0 0 40px 6px rgb(var(--marigold) / 0.35)" }}
        />
      ) : (
        <div className="fixed inset-0 bg-[rgb(4_6_18/0.7)]" />
      )}
      <AnimatePresence mode="wait">
        <motion.div
          key={cur?.id ?? "loading"}
          role="dialog"
          aria-modal="false"
          aria-label={title || t("tour.start")}
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0 }}
          className="pointer-events-auto fixed rounded-3xl bg-paper p-5 text-ink shadow-lift"
          style={cardStyle}
        >
          <div className="mb-2 flex items-center justify-between">
            <span className="eyebrow text-marigold-ink">{steps.length ? t("tour.stepOf", { n: step + 1, total: steps.length }) : t("tour.start")}</span>
            <button type="button" onClick={end} className="-mr-2 rounded-full p-1.5 text-ink-2 hover:bg-paper-2" aria-label={t("tour.exit")}>
              <X size={18} aria-hidden />
            </button>
          </div>
          {isError ? (
            <p className="text-sm">{t("tour.loadError")}</p>
          ) : !cur ? (
            <div className="skeleton h-16" />
          ) : (
            <>
              <h2 className="text-lg font-bold">{title}</h2>
              <p className="mt-1.5 text-sm leading-relaxed text-ink-2">{body}</p>
            </>
          )}
          <div className="mt-4 flex items-center justify-between gap-2">
            <button type="button" className="inline-flex items-center gap-1.5 text-sm font-semibold text-ink-2 hover:text-ink" onClick={() => void reset.run()} disabled={reset.busy}>
              <RotateCcw size={15} aria-hidden />
              {reset.busy ? t("tour.resetting") : t("tour.reset")}
            </button>
            <div className="flex gap-2">
              {step > 0 && (
                <button type="button" className="btn-ghost h-10 min-h-0 px-3" onClick={() => setStep(step - 1)} aria-label={t("tour.back")}>
                  <ArrowLeft size={16} aria-hidden />
                </button>
              )}
              <button type="button" className="btn-primary h-10 min-h-0" onClick={() => (last ? end() : setStep(step + 1))} disabled={!cur}>
                {last ? t("tour.finish") : t("tour.next")}
                {!last && <ArrowRight size={16} aria-hidden />}
              </button>
            </div>
          </div>
        </motion.div>
      </AnimatePresence>
    </div>
  );
}

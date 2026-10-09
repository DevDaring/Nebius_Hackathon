import { useEffect, useId, useRef } from "react";
import { useTranslation } from "react-i18next";
import { AnimatePresence, m as motion, useReducedMotion } from "framer-motion";
import { HeartPulse, Phone, ShieldAlert } from "lucide-react";
import { useApp } from "@/store/app";
import { isUrgent } from "@/lib/evidence";

/**
 * The result of the shared safety policy for a reading (manual entry, chat confirmation or a
 * revealed reference value). It takes priority over every success message: an emergency is a
 * calm full-screen alert with location-neutral emergency guidance in the user's language; other non-ok levels are
 * a prominent dialog. Title, message and actions come from the backend (localised via ?lang=).
 */
export function SafetyAlert() {
  const { t } = useTranslation();
  const s = useApp((st) => st.safetyAlert);
  const close = useApp((st) => st.showSafety);
  const reduce = useReducedMotion();
  const titleId = useId();
  const btn = useRef<HTMLButtonElement>(null);
  const open = !!s && isUrgent(s.level);
  const emergency = !!s?.emergency;

  useEffect(() => {
    if (!open) return;
    const prev = document.activeElement as HTMLElement | null;
    const raf = requestAnimationFrame(() => btn.current?.focus());
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape" && !emergency) close(null);
      if (e.key === "Tab") {
        const root = document.getElementById("safety-alert");
        const f = Array.from(root?.querySelectorAll<HTMLElement>("a[href], button") ?? []);
        if (!f.length) return;
        if (e.shiftKey && document.activeElement === f[0]) {
          e.preventDefault();
          f[f.length - 1].focus();
        } else if (!e.shiftKey && document.activeElement === f[f.length - 1]) {
          e.preventDefault();
          f[0].focus();
        }
      }
    };
    document.addEventListener("keydown", onKey);
    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      cancelAnimationFrame(raf);
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = prevOverflow;
      prev?.focus?.({ preventScroll: true });
    };
  }, [open, emergency, close]);

  return (
    <AnimatePresence>
      {open && s && (
        <motion.div
          id="safety-alert"
          key="safety"
          role="alertdialog"
          aria-modal="true"
          aria-labelledby={titleId}
          aria-describedby={`${titleId}-msg`}
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: reduce ? 0 : 0.25 }}
          className={`fixed inset-0 z-[95] flex items-center justify-center p-4 ${emergency ? "bg-[rgb(46_20_26)]" : "bg-night/70 backdrop-blur-sm"}`}
        >
          <motion.div
            initial={reduce ? false : { y: 16, opacity: 0 }}
            animate={{ y: 0, opacity: 1 }}
            transition={{ duration: reduce ? 0 : 0.3 }}
            className={`w-full max-w-lg rounded-4xl p-6 shadow-lift sm:p-8 ${emergency ? "bg-[rgb(70_28_34)] text-white ring-1 ring-white/20" : "bg-paper text-ink"}`}
          >
            <p className={`flex items-center gap-2 text-sm font-bold uppercase tracking-wide ${emergency ? "text-[rgb(255_200_190)]" : "text-coral-ink"}`}>
              {emergency ? <HeartPulse size={18} aria-hidden /> : <ShieldAlert size={18} aria-hidden />}
              {emergency ? t("safety.emergencyEyebrow") : t("safety.eyebrow")}
            </p>
            <h2 id={titleId} className={`mt-2 font-extrabold leading-tight ${emergency ? "text-3xl sm:text-4xl" : "text-2xl"}`}>
              {s.title}
            </h2>
            <p id={`${titleId}-msg`} className={`mt-3 text-lg leading-relaxed ${emergency ? "text-white/90" : "text-ink-2"}`}>
              {s.message}
            </p>
            {s.actions?.length > 0 && (
              <ul className="mt-4 space-y-2">
                {s.actions.map((a, i) => (
                  <li key={i} className={`flex items-start gap-3 rounded-2xl px-4 py-2.5 text-base font-semibold ${emergency ? "bg-white/10" : "bg-paper-2"}`}>
                    <span className={`num mt-0.5 inline-flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-sm ${emergency ? "bg-white text-[rgb(70_28_34)]" : "bg-ink text-paper"}`}>{i + 1}</span>
                    {a}
                  </li>
                ))}
              </ul>
            )}
            <div className="mt-6 flex flex-col gap-3 sm:flex-row">
              {(emergency || s.level === "very_high" || s.level === "very_low") && (
                // Location-neutral: the UI language says nothing about the user's country, so no number is dialled.
                <p className="inline-flex min-h-[52px] flex-1 items-center justify-center gap-2 rounded-full bg-white px-6 text-center text-lg font-extrabold text-[rgb(150_30_20)] ring-2 ring-[rgb(176_56_40)]">
                  <Phone size={20} aria-hidden />
                  {t("safety.callLocal")}
                </p>
              )}
              <button
                ref={btn}
                type="button"
                onClick={() => close(null)}
                className={`inline-flex min-h-[52px] flex-1 items-center justify-center rounded-full px-6 text-base font-bold ${emergency ? "border border-white/50 text-white hover:bg-white/10" : "bg-ink text-paper hover:bg-ink/90"}`}
              >
                {t("safety.understood")}
              </button>
            </div>
            <p className={`mt-4 text-xs leading-relaxed ${emergency ? "text-white/70" : "text-ink-3"}`}>{t("safety.footer")}</p>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}

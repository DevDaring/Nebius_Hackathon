import { useState } from "react";
import { useTranslation } from "react-i18next";
import { AnimatePresence, m as motion, useReducedMotion } from "framer-motion";
import { ArrowRight } from "lucide-react";
import { useApp } from "@/store/app";
import { useAuth } from "@/store/auth";

/** Small night-sky illustrations, one per card. */
function Art({ i }: { i: number }) {
  const reduce = useReducedMotion();
  const breathe = reduce ? {} : { animate: { opacity: [0.5, 1, 0.5] }, transition: { duration: 5, repeat: Infinity } };
  return (
    <svg viewBox="0 0 320 150" preserveAspectRatio="xMidYMid slice" className="h-full w-full" aria-hidden>
      <rect width="320" height="150" fill="rgb(var(--night))" />
      <rect y="52" width="320" height="56" fill="rgb(var(--teal))" opacity="0.08" />
      {i === 0 && (
        <>
          <path d="M0 110 C40 108 60 60 100 62 S150 110 190 100 S250 50 320 58" fill="none" stroke="rgb(var(--moon))" strokeOpacity="0.5" strokeWidth="2" />
          <motion.path d="M190 100 S250 50 320 58" fill="none" stroke="rgb(var(--marigold))" strokeWidth="4" strokeLinecap="round" initial={{ pathLength: reduce ? 1 : 0 }} animate={{ pathLength: 1 }} transition={{ duration: 1.4 }} />
          <circle cx="190" cy="100" r="6" fill="rgb(var(--marigold))" />
        </>
      )}
      {i === 1 && (
        <>
          <motion.path d="M60 90 C120 40 200 40 300 30 L300 110 C200 100 120 110 60 92 Z" fill="rgb(var(--marigold))" opacity="0.22" {...breathe} />
          <path d="M20 92 C40 92 50 91 60 91 C120 70 200 60 300 70" fill="none" stroke="rgb(var(--marigold))" strokeWidth="3.5" />
          <circle cx="60" cy="91" r="6" fill="rgb(var(--marigold))" />
        </>
      )}
      {i === 2 && (
        <>
          <path d="M120 80 C170 60 230 62 300 64 L300 92 C230 96 170 98 120 82 Z" fill="rgb(var(--marigold))" opacity="0.22" />
          <path d="M120 81 C170 79 230 78 300 78" fill="none" stroke="rgb(var(--marigold))" strokeWidth="3.5" />
          {[0, 0.4, 0.8].map((d) => (
            <motion.circle key={d} cx="120" cy="81" fill="none" stroke="rgb(var(--marigold))" strokeWidth="2" initial={{ r: 4, opacity: 0.9 }} animate={reduce ? {} : { r: 46, opacity: 0 }} transition={{ duration: 2, delay: d, repeat: Infinity }} />
          ))}
          <circle cx="120" cy="81" r="7" fill="rgb(var(--night))" stroke="rgb(var(--moon))" strokeWidth="3" />
        </>
      )}
      {i === 3 && (
        <>
          <circle cx="160" cy="75" r="34" fill="rgb(var(--marigold))" opacity="0.9" />
          {Array.from({ length: 22 }, (_, k) => {
            const h = 8 + Math.abs(Math.sin(k * 1.7)) * 34;
            const x = k < 11 ? 30 + k * 8 : 220 + (k - 11) * 8;
            return <motion.rect key={k} x={x} width="4" rx="2" y={75 - h / 2} height={h} fill="rgb(var(--moon))" opacity="0.6" animate={reduce ? {} : { scaleY: [1, 0.4, 1] }} transition={{ duration: 1.2, repeat: Infinity, delay: k * 0.05 }} style={{ transformOrigin: `${x}px 75px` }} />;
          })}
        </>
      )}
    </svg>
  );
}

export function Onboarding() {
  const { t } = useTranslation();
  const onboarded = useApp((s) => s.onboarded);
  const setOnboarded = useApp((s) => s.setOnboarded);
  const token = useAuth((s) => s.token);
  const [i, setI] = useState(0);
  if (onboarded || !token) return null;
  const keys = ["c1", "c2", "c3", "c4"];
  const last = i === keys.length - 1;
  return (
    <div className="fixed inset-0 z-[75] flex items-end justify-center bg-night/70 backdrop-blur-sm sm:items-center" role="dialog" aria-modal="true" aria-labelledby="onb-title">
      <div className="w-full max-w-md overflow-hidden rounded-t-4xl bg-paper shadow-lift sm:rounded-4xl">
        <div className="h-40">
          <AnimatePresence mode="wait">
            <motion.div key={i} className="h-full" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
              <Art i={i} />
            </motion.div>
          </AnimatePresence>
        </div>
        <div className="p-6">
          <p className="eyebrow text-marigold-ink">
            {t("onboarding.label")} · {t("onboarding.stepOf", { n: i + 1, total: keys.length })}
          </p>
          <h2 id="onb-title" className="mt-2 text-2xl font-extrabold">
            {t(`onboarding.${keys[i]}.title`)}
          </h2>
          <p className="mt-2 leading-relaxed text-ink-2">{t(`onboarding.${keys[i]}.body`)}</p>
          <div className="mt-6 flex items-center justify-between">
            <div className="flex gap-1.5" aria-hidden>
              {keys.map((k, n) => (
                <span key={k} className={`h-1.5 rounded-full transition-all ${n === i ? "w-6 bg-marigold" : "w-1.5 bg-line"}`} />
              ))}
            </div>
            <div className="flex gap-2">
              {!last && (
                <button type="button" className="btn text-ink-2 hover:text-ink" onClick={() => setOnboarded(true)}>
                  {t("common.skip")}
                </button>
              )}
              <button type="button" className="btn-primary" autoFocus onClick={() => (last ? setOnboarded(true) : setI(i + 1))}>
                {last ? t("onboarding.start") : t("common.next")}
                <ArrowRight size={16} aria-hidden />
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

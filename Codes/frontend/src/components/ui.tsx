import { useEffect, useId, useRef, useState, type ReactNode } from "react";
import { AnimatePresence, m as motion, useReducedMotion } from "framer-motion";
import { useTranslation } from "react-i18next";
import { AlertTriangle, CloudOff, Info, RefreshCw, X } from "lucide-react";
import { useToasts } from "@/store/toast";
import { useAuth } from "@/store/auth";
import { ClownfishSvg } from "./Clownfish";

/* ---------------- Brand ---------------- */
/** NemoTwins mark: the original blue clownfish on a deep marine tile (same drawing as favicon.svg). */
export function LogoMark({ size = 32, className = "" }: { size?: number; className?: string }) {
  return (
    <span className={`inline-flex shrink-0 items-center justify-center rounded-[28%] bg-[#081B33] ${className}`} style={{ width: size, height: size }} aria-hidden>
      <ClownfishSvg style={{ width: size * 0.86, height: size * 0.46 }} body="#56B0FF" shade="#2F7FE0" band="#EAF4FF" outline="#EAF4FF" />
    </span>
  );
}

export function Wordmark({ tone = "ink", compact = false, tagline = false }: { tone?: "ink" | "moon"; compact?: boolean; tagline?: boolean }) {
  const { t } = useTranslation();
  return (
    <span className="inline-flex items-center gap-2.5">
      <LogoMark size={compact ? 30 : 36} />
      <span className="leading-none">
        <span className={`block text-[1.15rem] font-extrabold tracking-tight ${tone === "moon" ? "text-moon" : "text-ink"}`} lang="en">
          {t("app.name")}
        </span>
        {tagline && (
          <span className={`mt-0.5 hidden max-w-[17rem] truncate text-[0.68rem] font-medium sm:block xl:hidden 2xl:block ${tone === "moon" ? "text-moon-3" : "text-ink-3"}`}>{t("app.tagline")}</span>
        )}
        {!compact && <span className={`mt-0.5 block text-[0.7rem] font-medium ${tone === "moon" ? "text-moon-3" : "text-ink-3"}`}>{t("app.descriptor")}</span>}
      </span>
    </span>
  );
}

/* ---------------- Offline mock pill ---------------- */
export function MockPill({ tone = "paper" }: { tone?: "paper" | "night" }) {
  const { t } = useTranslation();
  const mock = useAuth((s) => s.mock);
  if (!mock) return null;
  return (
    <InfoTip label={t("common.offlineMockHint")} tone={tone}>
      <span
        className={`inline-flex items-center gap-1.5 whitespace-nowrap rounded-full border px-2.5 py-1 text-xs font-semibold ${
          tone === "night" ? "border-marigold/50 bg-marigold/10 text-marigold" : "border-marigold-ink/40 bg-marigold/10 text-marigold-ink"
        }`}
      >
        <CloudOff size={13} aria-hidden />
        {t("common.offlineMock")}
      </span>
    </InfoTip>
  );
}

/* ---------------- Info tip (tooltip on hover/focus, toggles on tap) ---------------- */
export function InfoTip({ label, children, tone = "paper" }: { label: string; children?: ReactNode; tone?: "paper" | "night" }) {
  const [open, setOpen] = useState(false);
  const id = useId();
  const descId = `${id}-desc`;
  return (
    <span className="relative inline-flex" onMouseEnter={() => setOpen(true)} onMouseLeave={() => setOpen(false)}>
      <button
        type="button"
        // The explanation is always available to assistive tech (and as a native title), not only while the tip is open.
        aria-describedby={children ? descId : undefined}
        title={children ? label : undefined}
        aria-label={children ? undefined : label}
        onFocus={() => setOpen(true)}
        onBlur={() => setOpen(false)}
        onClick={() => setOpen((o) => !o)}
        className={`inline-flex items-center rounded-full ${children ? "" : `p-1 ${tone === "night" ? "text-moon-3 hover:text-moon" : "text-ink-3 hover:text-ink"}`}`}
      >
        {children ?? <Info size={15} aria-hidden />}
      </button>
      {children && (
        <span id={descId} className="sr-only">
          {label}
        </span>
      )}
      <AnimatePresence>
        {open && (
          <motion.span
            id={id}
            role="tooltip"
            initial={{ opacity: 0, y: 4 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 4 }}
            transition={{ duration: 0.15 }}
            className="absolute left-1/2 top-full z-50 mt-2 w-64 max-w-[80vw] -translate-x-1/2 rounded-2xl bg-ink px-3 py-2 text-left text-xs font-normal normal-case leading-relaxed tracking-normal text-paper shadow-lift"
          >
            {label}
          </motion.span>
        )}
      </AnimatePresence>
    </span>
  );
}

/* ---------------- Modal: sheet (bottom on mobile) or drawer (right on desktop) ---------------- */
export function Modal({
  open,
  onClose,
  title,
  subtitle,
  children,
  variant = "sheet",
  footer,
}: {
  open: boolean;
  onClose: () => void;
  title: string;
  subtitle?: string;
  children: ReactNode;
  variant?: "sheet" | "drawer";
  footer?: ReactNode;
}) {
  const { t } = useTranslation();
  const reduce = useReducedMotion();
  const panel = useRef<HTMLDivElement>(null);
  const titleId = useId();
  const restore = useRef<HTMLElement | null>(null);

  useEffect(() => {
    if (!open) return;
    restore.current = document.activeElement as HTMLElement;
    const el = panel.current;
    const focusables = () =>
      Array.from(el?.querySelectorAll<HTMLElement>('button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])') ?? []).filter(
        (n) => !n.hasAttribute("disabled"),
      );
    const raf = requestAnimationFrame(() => {
      const first = el?.querySelector<HTMLElement>("[data-autofocus]") ?? focusables()[0];
      first?.focus();
    });
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.stopPropagation();
        onClose();
      }
      if (e.key === "Tab") {
        const f = focusables();
        if (f.length === 0) return;
        const first = f[0];
        const last = f[f.length - 1];
        if (e.shiftKey && document.activeElement === first) {
          e.preventDefault();
          last.focus();
        } else if (!e.shiftKey && document.activeElement === last) {
          e.preventDefault();
          first.focus();
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
      restore.current?.focus?.({ preventScroll: true });
    };
  }, [open, onClose]);

  const drawer = variant === "drawer";
  return (
    <AnimatePresence>
      {open && (
        <div className="fixed inset-0 z-[60] flex items-end justify-center sm:items-center" style={drawer ? { justifyContent: "flex-end" } : undefined}>
          <motion.div
            className="absolute inset-0 bg-night/55 backdrop-blur-[2px]"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={onClose}
            aria-hidden
          />
          <motion.div
            ref={panel}
            role="dialog"
            aria-modal="true"
            aria-labelledby={titleId}
            initial={reduce ? { opacity: 0 } : drawer ? { x: 40, opacity: 0 } : { y: 60, opacity: 0 }}
            animate={{ x: 0, y: 0, opacity: 1 }}
            exit={reduce ? { opacity: 0 } : drawer ? { x: 40, opacity: 0 } : { y: 60, opacity: 0 }}
            transition={{ type: "spring", damping: 30, stiffness: 320 }}
            className={
              drawer
                ? "relative flex max-h-[92dvh] w-full flex-col rounded-t-4xl bg-paper text-ink shadow-lift sm:h-[100dvh] sm:max-h-none sm:w-[460px] sm:rounded-none sm:rounded-l-4xl"
                : "relative flex max-h-[92dvh] w-full flex-col rounded-t-4xl bg-paper text-ink shadow-lift sm:w-[480px] sm:rounded-4xl"
            }
          >
            <div className="mx-auto mt-2.5 h-1.5 w-12 rounded-full bg-line sm:hidden" aria-hidden />
            <header className="flex items-start justify-between gap-4 px-6 pb-2 pt-4 sm:pt-6">
              <div>
                <h2 id={titleId} className="text-xl font-bold">
                  {title}
                </h2>
                {subtitle && <p className="mt-1 text-sm text-ink-2">{subtitle}</p>}
              </div>
              <button type="button" onClick={onClose} className="-mr-2 rounded-full p-2 text-ink-2 hover:bg-paper-2" aria-label={t("common.close")}>
                <X size={20} aria-hidden />
              </button>
            </header>
            <div className="min-h-0 flex-1 overflow-y-auto px-6 pb-6">{children}</div>
            {footer && <div className="border-t border-line px-6 py-4">{footer}</div>}
          </motion.div>
        </div>
      )}
    </AnimatePresence>
  );
}

/* ---------------- Toasts ---------------- */
export function Toaster() {
  const toasts = useToasts((s) => s.toasts);
  const dismiss = useToasts((s) => s.dismiss);
  return (
    <div className="pointer-events-none fixed inset-x-0 bottom-24 z-[80] flex flex-col items-center gap-2 px-4 sm:bottom-8" aria-live="polite" role="status">
      <AnimatePresence>
        {toasts.map((tt) => (
          <motion.button
            key={tt.id}
            type="button"
            onClick={() => dismiss(tt.id)}
            initial={{ opacity: 0, y: 16, scale: 0.96 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 8, scale: 0.98 }}
            className={`pointer-events-auto flex max-w-md items-center gap-3 rounded-full px-5 py-3 text-sm font-semibold shadow-lift ${
              tt.tone === "success"
                ? "bg-night text-moon ring-1 ring-marigold/50"
                : tt.tone === "error"
                  ? "bg-[rgb(176_56_40)] text-white"
                  : tt.tone === "warn"
                    ? "bg-marigold text-night"
                    : "bg-ink text-paper"
            }`}
          >
            {tt.tone === "success" && <span className="h-2.5 w-2.5 rounded-full bg-marigold" aria-hidden />}
            {tt.text}
          </motion.button>
        ))}
      </AnimatePresence>
    </div>
  );
}

/* ---------------- Frequency pictogram: N of 10 ---------------- */
export function FreqDots({ p, tone }: { p: number; tone: "coral" | "violet" | "marigold" }) {
  const { t } = useTranslation();
  const n = Math.round(Math.max(0, Math.min(1, p)) * 10);
  const fill = { coral: "bg-coral", violet: "bg-violet", marigold: "bg-marigold" }[tone];
  return (
    <span className="flex gap-1" role="img" aria-label={t("risk.dots", { n })}>
      {Array.from({ length: 10 }, (_, i) => (
        <span key={i} className={`h-2.5 w-2.5 rounded-full transition-colors duration-500 ${i < n ? fill : "bg-line"}`} />
      ))}
    </span>
  );
}

/* ---------------- States ---------------- */
export function ErrorState({ message, onRetry, tone = "paper" }: { message: string; onRetry?: () => void; tone?: "paper" | "night" }) {
  const { t } = useTranslation();
  return (
    <div
      role="alert"
      className={`flex flex-col items-start gap-3 rounded-3xl border p-5 text-sm ${
        tone === "night" ? "border-night-line bg-night-2 text-moon" : "border-line bg-card text-ink"
      }`}
    >
      <span className="inline-flex items-center gap-2 font-semibold">
        <AlertTriangle size={18} className={tone === "night" ? "text-coral-night" : "text-coral-ink"} aria-hidden />
        {message}
      </span>
      {onRetry && (
        <button type="button" onClick={onRetry} className={tone === "night" ? "btn-night" : "btn-ghost"}>
          <RefreshCw size={16} aria-hidden />
          {t("common.retry")}
        </button>
      )}
    </div>
  );
}

export function SyntheticBadge({ tone = "paper", note }: { tone?: "paper" | "night"; note?: string }) {
  const { t } = useTranslation();
  return (
    <InfoTip label={note ?? t("common.syntheticHint")} tone={tone}>
      <span
        className={`inline-flex items-center rounded-full border px-2 py-0.5 text-[0.68rem] font-semibold ${
          tone === "night" ? "border-moon-3/40 text-moon-2" : "border-line text-ink-2"
        }`}
      >
        {t("common.synthetic")}
      </span>
    </InfoTip>
  );
}

export function SectionTitle({ eyebrow, title, info, action }: { eyebrow?: string; title: string; info?: string; action?: ReactNode }) {
  return (
    <div className="mb-3 flex items-end justify-between gap-3">
      <div>
        {eyebrow && <p className="eyebrow text-ink-3">{eyebrow}</p>}
        <h2 className="flex items-center gap-1 text-lg font-bold">
          {title}
          {info && <InfoTip label={info} />}
        </h2>
      </div>
      {action}
    </div>
  );
}

export function Caption({ children, tone = "paper" }: { children: ReactNode; tone?: "paper" | "night" }) {
  return <p className={`mt-2 text-sm leading-relaxed ${tone === "night" ? "text-moon-2" : "text-ink-2"}`}>{children}</p>;
}

export function Avatar({ initials, size = 40, active }: { initials: string; size?: number; active?: boolean }) {
  return (
    <span
      className={`inline-flex shrink-0 items-center justify-center rounded-full font-bold ${
        active ? "bg-marigold text-night" : "bg-night-3 text-moon"
      }`}
      style={{ width: size, height: size, fontSize: size * 0.36 }}
      aria-hidden
    >
      {initials}
    </span>
  );
}

export function PageHeader({ title, subtitle, right }: { title: string; subtitle?: string; right?: ReactNode }) {
  return (
    <div className="mb-6 flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
      <div>
        <h1 className="text-2xl font-extrabold sm:text-3xl">{title}</h1>
        {subtitle && <p className="mt-1.5 max-w-2xl text-ink-2">{subtitle}</p>}
      </div>
      {right}
    </div>
  );
}

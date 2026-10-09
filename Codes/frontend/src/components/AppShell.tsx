import { lazy, Suspense, useEffect, useRef, useState, type ReactNode } from "react";
import { NavLink, useLocation, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useQueryClient } from "@tanstack/react-query";
import { AnimatePresence, m as motion } from "framer-motion";
import {
  Activity,
  Check,
  Compass,
  Languages,
  LogOut,
  Menu,
  MonitorPlay,
  MessageCircle,
  Monitor,
  Moon,
  RotateCcw,
  ServerCog,
  ShieldCheck,
  Sparkles,
  Stethoscope,
  Sun,
  User,
  UtensilsCrossed,
} from "lucide-react";
import type { Lang } from "@/api/types";
import { LANGS } from "@/api/types";
import { useApplyTheme, useResetDemo } from "@/hooks/useDemo";
import { LANG_LABELS } from "@/i18n";
import { useApp, type ThemePref } from "@/store/app";
import { useAuth } from "@/store/auth";
import { LogoMark, MockPill, Modal, Toaster, Wordmark } from "./ui";
import { SafetyAlert } from "./SafetyAlert";
import { ClownfishLayer } from "./ClownfishLayer";
import { PoweredBy } from "./PoweredBy";
import { PresentationBar, PresentationButton } from "./Presentation";
import { togglePresentation, usePresentationClass } from "@/lib/presentation";

// Overlays are separate chunks (the "Why?" drawer pulls in the chart code).
const WhyDrawer = lazy(() => import("./WhyDrawer").then((m) => ({ default: m.WhyDrawer })));
const Tour = lazy(() => import("./Tour").then((m) => ({ default: m.Tour })));
// First-run cards: only fetched for people who have not seen them yet (keeps the main bundle small).
const Onboarding = lazy(() => import("./Onboarding").then((m) => ({ default: m.Onboarding })));

const NAV = [
  { to: "/", key: "twin", icon: Activity, end: true },
  { to: "/meal", key: "meal", icon: UtensilsCrossed },
  { to: "/whatif", key: "whatif", icon: Sparkles },
  { to: "/talk", key: "talk", icon: MessageCircle },
  { to: "/trust", key: "trust", icon: ShieldCheck },
  { to: "/doctor", key: "doctor", icon: Stethoscope },
  { to: "/me", key: "me", icon: User },
] as const;
/** Shown only to users whose roles include "admin" (GET /api/auth/me). */
const ADMIN_NAV = { to: "/admin", key: "admin", icon: ServerCog } as const;

/** Report / print views: the decorative fish stays off there. */
const REPORT_ROUTE = /^\/doctor\/[^/]+/;

/** Pages whose top is the indigo "night" stage get a night header for a seamless look. */
const NIGHT_ROUTES = ["/", "/talk"];

export function LangSwitch({ tone = "paper" }: { tone?: "paper" | "night" }) {
  const { t } = useTranslation();
  const lang = useApp((s) => s.lang);
  const setLang = useApp((s) => s.setLang);
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent) => {
      if (!ref.current?.contains(e.target as Node)) setOpen(false);
    };
    const esc = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    document.addEventListener("mousedown", close);
    document.addEventListener("keydown", esc);
    return () => {
      document.removeEventListener("mousedown", close);
      document.removeEventListener("keydown", esc);
    };
  }, [open]);
  return (
    <div className="relative" ref={ref}>
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        aria-haspopup="true"
        aria-label={t("common.language")}
        className={`inline-flex h-10 items-center gap-1.5 whitespace-nowrap rounded-full px-2.5 text-sm font-semibold sm:px-3 ${
          tone === "night" ? "text-moon hover:bg-night-2" : "text-ink hover:bg-paper-2"
        }`}
      >
        <Languages size={17} aria-hidden />
        <span className="hidden sm:inline">{LANG_LABELS[lang].native}</span>
        <span className="sm:hidden">{LANG_LABELS[lang].short}</span>
      </button>
      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ opacity: 0, y: -4 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -4 }}
            className="absolute right-0 z-50 mt-2 w-48 rounded-2xl border border-line bg-card p-1.5 shadow-lift"
          >
            {LANGS.map((l: Lang) => (
              <button
                key={l}
                type="button"
                lang={l}
                aria-pressed={l === lang}
                onClick={() => {
                  setLang(l);
                  setOpen(false);
                }}
                className="flex w-full items-center justify-between rounded-xl px-3 py-2.5 text-left text-sm text-ink hover:bg-paper-2"
              >
                <span>
                  <span className="font-semibold">{LANG_LABELS[l].native}</span>
                  {l !== "en-US" && <span className="ml-2 text-xs text-ink-3">{LANG_LABELS[l].english}</span>}
                </span>
                {l === lang && <Check size={16} className="text-marigold-ink" aria-hidden />}
              </button>
            ))}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

function ThemeToggle({ tone }: { tone: "paper" | "night" }) {
  const { t } = useTranslation();
  const theme = useApp((s) => s.theme);
  const setTheme = useApp((s) => s.setTheme);
  const next: Record<ThemePref, ThemePref> = { system: "light", light: "dark", dark: "system" };
  const Icon = theme === "light" ? Sun : theme === "dark" ? Moon : Monitor;
  const label = t(theme === "light" ? "common.themeLight" : theme === "dark" ? "common.themeDark" : "common.themeSystem");
  return (
    <button
      type="button"
      onClick={() => setTheme(next[theme])}
      aria-label={`${t("common.theme")}: ${label}`}
      title={`${t("common.theme")}: ${label}`}
      className={`inline-flex h-10 w-10 items-center justify-center rounded-full ${tone === "night" ? "text-moon hover:bg-night-2" : "text-ink hover:bg-paper-2"}`}
    >
      <Icon size={18} aria-hidden />
    </button>
  );
}

export function AppShell({ children }: { children: ReactNode }) {
  const { t } = useTranslation();
  const loc = useLocation();
  const navigate = useNavigate();
  const user = useAuth((s) => s.user);
  const logout = useAuth((s) => s.logout);
  const startTour = useApp((s) => s.startTour);
  const onboarded = useApp((s) => s.onboarded);
  const qc = useQueryClient();
  const [menu, setMenu] = useState(false);
  const night = NIGHT_ROUTES.includes(loc.pathname);
  // A new page starts at the top (the browser would keep the previous page's scroll position).
  useEffect(() => {
    window.scrollTo({ top: 0, left: 0, behavior: "instant" as ScrollBehavior });
  }, [loc.pathname]);
  const tone = night ? "night" : "paper";
  const reset = useResetDemo();
  const presentation = useApp((s) => s.presentation);
  const isAdmin = !!user?.roles?.includes("admin");
  const nav = isAdmin ? [...NAV, ADMIN_NAV] : NAV;
  useApplyTheme();
  usePresentationClass();

  useEffect(() => setMenu(false), [loc.pathname]);

  const signOut = () => {
    logout();
    qc.clear();
    navigate("/login", { replace: true });
  };

  const linkCls = (active: boolean) =>
    `inline-flex h-10 items-center gap-2 whitespace-nowrap rounded-full px-3 text-sm font-semibold transition ${
      night
        ? active
          ? "bg-moon text-night"
          : "text-moon-2 hover:bg-night-2 hover:text-moon"
        : active
          ? "bg-ink text-paper"
          : "text-ink-2 hover:bg-paper-2 hover:text-ink"
    }`;

  return (
    <div className={`flex min-h-[100dvh] flex-col ${night ? "bg-night" : "bg-paper"}`}>
      <a href="#main" className="sr-only z-[90] rounded-full bg-marigold px-4 py-2 font-semibold text-night focus:not-sr-only focus:fixed focus:left-4 focus:top-4">
        {t("a11y.skip")}
      </a>
      <header className={`no-print sticky top-0 z-40 ${night ? "on-night bg-night/85" : "bg-paper/85"} backdrop-blur-md`}>
        <div className="mx-auto flex h-16 max-w-7xl items-center justify-between gap-3 px-4 sm:px-6">
          <NavLink to="/" aria-label={t("app.name")} className="shrink-0 rounded-xl">
            <Wordmark tone={night ? "moon" : "ink"} compact tagline />
          </NavLink>
          <nav aria-label={t("nav.mainNav")} className="hidden items-center gap-1 xl:flex">
            {NAV.filter((n) => n.key !== "me").map(({ to, key, icon: Icon, ...rest }) => (
              <NavLink key={to} to={to} end={"end" in rest} className={({ isActive }) => linkCls(isActive)}>
                <Icon size={16} aria-hidden />
                {t(`nav.${key}`)}
              </NavLink>
            ))}
          </nav>
          <div className="flex items-center gap-1">
            <MockPill tone={tone} />
            <button
              type="button"
              onClick={startTour}
              aria-label={t("tour.start")}
              title={t("tour.start")}
              className={`hidden h-10 items-center gap-2 whitespace-nowrap rounded-full px-3 text-sm font-semibold md:inline-flex ${
                night ? "text-marigold hover:bg-night-2" : "text-marigold-ink hover:bg-paper-2"
              }`}
            >
              <Compass size={17} aria-hidden />
              <span className="hidden 2xl:inline">{t("tour.start")}</span>
            </button>
            <PresentationButton tone={tone} />
            <LangSwitch tone={tone} />
            <span className="hidden sm:inline-flex">
              <ThemeToggle tone={tone} />
            </span>
            <button
              type="button"
              onClick={() => setMenu(true)}
              aria-label={t("a11y.openMenu")}
              className={`inline-flex h-10 w-10 items-center justify-center rounded-full ${night ? "text-moon hover:bg-night-2" : "text-ink hover:bg-paper-2"}`}
            >
              <Menu size={20} aria-hidden />
            </button>
          </div>
        </div>
      </header>

      <Modal open={menu} onClose={() => setMenu(false)} title={t("nav.menu")} subtitle={user?.display_name} variant="drawer">
        <nav aria-label={t("nav.mainNav")} className="grid gap-1.5">
          {nav.map(({ to, key, icon: Icon, ...rest }) => (
            <NavLink
              key={to}
              to={to}
              end={"end" in rest}
              className={({ isActive }) =>
                `flex min-h-[48px] items-center gap-3 rounded-2xl px-4 text-base font-semibold ${isActive ? "bg-ink text-paper" : "text-ink hover:bg-paper-2"}`
              }
            >
              <Icon size={19} aria-hidden />
              {t(`nav.${key}`)}
            </NavLink>
          ))}
        </nav>
        <div className="mt-5 grid gap-2 border-t border-line pt-5">
          <button
            type="button"
            className="btn-ghost justify-start"
            onClick={() => {
              setMenu(false);
              startTour();
            }}
          >
            <Compass size={18} aria-hidden />
            {t("tour.start")}
          </button>
          <button
            type="button"
            className="btn-ghost justify-start"
            aria-pressed={presentation}
            onClick={() => {
              setMenu(false);
              togglePresentation(!presentation);
            }}
          >
            <MonitorPlay size={18} aria-hidden />
            {presentation ? t("presentation.exit") : t("presentation.toggle")}
          </button>
          <button type="button" className="btn-ghost justify-start" onClick={() => void reset.run()} disabled={reset.busy}>
            <RotateCcw size={18} aria-hidden />
            {reset.busy ? t("tour.resetting") : t("tour.reset")}
          </button>
          <div className="flex items-center justify-between rounded-full border border-line bg-card pl-5">
            <span className="text-sm font-semibold">{t("common.theme")}</span>
            <ThemeToggle tone="paper" />
          </div>
          <button type="button" className="btn-ghost justify-start" onClick={signOut}>
            <LogOut size={18} aria-hidden />
            {t("common.signOut")}
          </button>
        </div>
      </Modal>

      <main id="main" className="flex-1" tabIndex={-1}>
        {children}
      </main>

      <div className={night ? "bg-night" : "bg-paper"}>
        <ClownfishLayer tone={tone} suppressed={REPORT_ROUTE.test(loc.pathname)} />
      </div>

      <footer className={`no-print presentation-hide px-4 pb-8 pt-6 ${night ? "bg-night text-moon-3" : "bg-paper text-ink-3"}`}>
        <div className={`mx-auto flex max-w-3xl flex-col items-center gap-2 border-t pt-5 text-center ${night ? "border-night-line/50" : "border-line"}`}>
          <p className="inline-flex flex-wrap items-center justify-center gap-x-2 gap-y-1 text-xs">
            <LogoMark size={18} />
            <span className={`font-bold ${night ? "text-moon-2" : "text-ink-2"}`} lang="en">
              {t("app.name")}
            </span>
            <span aria-hidden className="hidden sm:inline">
              ·
            </span>
            <span className="w-full italic sm:w-auto">{t("app.tagline")}</span>
          </p>
          <p className="text-xs leading-relaxed">{t("footer.disclaimer")}</p>
          <PoweredBy tone={tone} />
        </div>
      </footer>
      <p className="print-only px-2 text-[9px] text-ink-3">{t("footer.disclaimer")}</p>

      <Toaster />
      <SafetyAlert />
      <PresentationBar />
      <Suspense fallback={null}>
        <WhyDrawer />
        <Tour />
        {!onboarded && <Onboarding />}
      </Suspense>
    </div>
  );
}

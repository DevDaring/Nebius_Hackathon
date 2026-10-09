import { useTranslation } from "react-i18next";
import { Maximize2, Minimize2, MonitorPlay, RotateCcw } from "lucide-react";
import { useActivePatientId, useHealth, useTwinState } from "@/api/hooks";
import { useResetDemo } from "@/hooks/useDemo";
import { replayLabel } from "@/lib/replay";
import { useApp } from "@/store/app";
import { useAuth } from "@/store/auth";
import { togglePresentation } from "@/lib/presentation";
import { LogoMark } from "./ui";

export function PresentationButton({ tone }: { tone: "paper" | "night" }) {
  const { t } = useTranslation();
  const on = useApp((s) => s.presentation);
  return (
    <button
      type="button"
      onClick={() => togglePresentation(!on)}
      aria-pressed={on}
      title={t("presentation.toggle")}
      aria-label={t("presentation.toggle")}
      className={`hidden h-10 items-center gap-2 whitespace-nowrap rounded-full px-3 text-sm font-semibold md:inline-flex ${
        on ? "bg-marigold text-night" : tone === "night" ? "text-moon hover:bg-night-2" : "text-ink hover:bg-paper-2"
      }`}
    >
      {on ? <Minimize2 size={17} aria-hidden /> : <MonitorPlay size={17} aria-hidden />}
      <span className="hidden 2xl:inline">{t("presentation.short")}</span>
    </button>
  );
}

/**
 * Status bar shown in presentation mode: the replay clock, where the data and answers come from
 * (recorded fixtures, live AI or the offline mock) and a deterministic reset.
 */
export function PresentationBar() {
  const { t, i18n } = useTranslation();
  const on = useApp((s) => s.presentation);
  const ladder = useApp((s) => s.ladder);
  const pid = useActivePatientId();
  const state = useTwinState(on ? pid : null, ladder);
  const health = useHealth();
  const mock = useAuth((s) => s.mock);
  const reset = useResetDemo();
  if (!on) return null;
  const mode = mock ? t("presentation.modeMock") : health.data?.mode === "live" ? t("presentation.modeLive") : health.data?.mode === "demo" ? t("presentation.modeFixtures") : "…";
  return (
    <div className="no-print fixed bottom-3 left-3 z-[70] hidden max-w-[calc(100vw-1.5rem)] items-center gap-2 rounded-full border border-marigold/50 bg-night/95 py-1.5 pl-3 pr-1.5 text-sm text-moon shadow-lift backdrop-blur md:flex" role="status">
      <LogoMark size={20} />
      <span className="font-bold" lang="en">
        {t("app.name")}
      </span>
      <span className="text-moon-3">·</span>
      <span className="font-semibold">{t("presentation.short")}</span>
      <span className="text-moon-3">·</span>
      <span className="num">{replayLabel(t, i18n.language, state.data?.replay ?? null, state.data?.now)}</span>
      <span className="text-moon-3">·</span>
      <span>{mode}</span>
      <button type="button" className="ml-1 inline-flex h-8 items-center gap-1.5 rounded-full bg-night-3 px-3 text-xs font-semibold hover:bg-night-2" onClick={() => void reset.run()} disabled={reset.busy}>
        <RotateCcw size={13} aria-hidden />
        {reset.busy ? t("tour.resetting") : t("presentation.reset")}
      </button>
      <button type="button" className="inline-flex h-8 items-center gap-1.5 rounded-full bg-marigold px-3 text-xs font-bold text-night" onClick={() => togglePresentation(false)}>
        <Maximize2 size={13} aria-hidden />
        {t("presentation.exit")}
      </button>
    </div>
  );
}

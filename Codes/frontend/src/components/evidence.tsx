import { useTranslation } from "react-i18next";
import { AlertTriangle, BadgeCheck, Compass, FlaskConical, Ruler, Sigma } from "lucide-react";
import type { ClaimStatus } from "@/api/types";
import { STATUS_META } from "@/lib/evidence";
import { InfoTip } from "./ui";

const ICON = { ruler: Ruler, sigma: Sigma, flask: FlaskConical, check: BadgeCheck, compass: Compass, alert: AlertTriangle };

const TONE_NIGHT: Record<string, string> = {
  teal: "border-teal/60 text-teal",
  ink: "border-moon-3/60 text-moon-2",
  violet: "border-violet-night/70 text-violet-night",
  marigold: "border-marigold/60 text-marigold",
  slate: "border-moon-3/50 text-moon-3",
  coral: "border-coral-night/70 text-coral-night",
};
const TONE_PAPER: Record<string, string> = {
  teal: "border-teal-ink/50 bg-teal/10 text-teal-ink",
  ink: "border-ink-3/40 bg-paper-2 text-ink-2",
  violet: "border-violet-ink/40 bg-violet/10 text-violet-ink",
  marigold: "border-marigold-ink/40 bg-marigold/10 text-marigold-ink",
  slate: "border-ink-3/40 bg-paper-2 text-ink-3",
  coral: "border-coral-ink/40 bg-coral/10 text-coral-ink",
};

/**
 * Evidence-status chip next to a number: measured, estimated, simulated, retrospectively evaluated
 * ("validated" in the API), exploratory or not validated. The short label never says just
 * "Validated"; the full explanation is always exposed (aria-describedby + title), and tapping or
 * focusing it shows the explanation as a tooltip.
 */
export function EvidenceChip({ status, tone = "paper", explain = true, label }: { status: ClaimStatus; tone?: "paper" | "night"; explain?: boolean; label?: string }) {
  const { t } = useTranslation();
  const meta = STATUS_META[status];
  const Icon = ICON[meta.icon];
  const cls = (tone === "night" ? TONE_NIGHT : TONE_PAPER)[meta.tone];
  const chip = (
    <span
      className={`inline-flex items-center gap-1 whitespace-nowrap rounded-full border px-2 py-0.5 text-[0.7rem] font-semibold leading-tight ${cls}`}
      title={explain ? undefined : t(`evidence.explain.${status}`)}
      data-evidence={status}
    >
      <Icon size={11} aria-hidden />
      {label ?? t(`evidence.status.${status}`)}
    </span>
  );
  if (!explain) return chip;
  return (
    <InfoTip label={`${label ?? t(`evidence.status.${status}`)}: ${t(`evidence.explain.${status}`)}`} tone={tone}>
      {chip}
    </InfoTip>
  );
}

/** "Model simulation — not a proven effect" label for every what-if result. */
export function SimulationLabel({ tone = "night" }: { tone?: "paper" | "night" }) {
  const { t } = useTranslation();
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-bold ${
        tone === "night" ? "border-violet-night/60 bg-violet/15 text-violet-night" : "border-violet-ink/40 bg-violet/10 text-violet-ink"
      }`}
    >
      <FlaskConical size={13} aria-hidden />
      {t("futures.simulationLabel")}
    </span>
  );
}

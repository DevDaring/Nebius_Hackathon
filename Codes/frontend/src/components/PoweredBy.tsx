import { useTranslation } from "react-i18next";
import { useCapabilities } from "@/api/hooks";
import { capFlags } from "@/lib/capabilities";

/**
 * "Powered by NVIDIA Nemotron on Nebius Token Factory" plus the chat model id from
 * GET /api/capabilities. The model id is a proper name and is never translated.
 */
export function PoweredBy({ tone = "paper", className = "" }: { tone?: "paper" | "night"; className?: string }) {
  const { t } = useTranslation();
  const caps = useCapabilities();
  const f = capFlags(caps.data);
  return (
    <p className={`text-xs ${tone === "night" ? "text-moon-3" : "text-ink-3"} ${className}`} data-powered-by>
      {t("about.poweredBy")}
      {f.chatModel && (
        <>
          {" · "}
          <span className="font-mono" lang="en" translate="no">
            {f.chatModel}
          </span>
        </>
      )}
      {f.known && !f.inferenceAvailable && <> · {t("about.inferenceOffline")}</>}
    </p>
  );
}

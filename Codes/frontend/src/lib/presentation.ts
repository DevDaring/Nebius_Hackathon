import { useEffect } from "react";
import { useApp } from "@/store/app";

/** Turn presentation mode on/off. Fullscreen needs a user gesture, so it is requested here. */
export function togglePresentation(on: boolean) {
  useApp.getState().setPresentation(on);
  try {
    if (on && !document.fullscreenElement) void document.documentElement.requestFullscreen?.().catch(() => undefined);
    if (!on && document.fullscreenElement) void document.exitFullscreen?.().catch(() => undefined);
  } catch {
    /* fullscreen not allowed: large-label mode still applies */
  }
}

/** Applies the presentation class (large labels, clean composition) to the document. */
export function usePresentationClass() {
  const on = useApp((s) => s.presentation);
  useEffect(() => {
    document.documentElement.classList.toggle("presentation", on);
  }, [on]);
}

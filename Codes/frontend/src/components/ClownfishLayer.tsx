import { useEffect, useRef, useState } from "react";
import { useReducedMotion } from "framer-motion";
import { useCapabilities } from "@/api/hooks";
import { capFlags } from "@/lib/capabilities";
import { createFishScheduler, fishAllowed, isConstrainedDevice, MAX_FISH, type PassPlan } from "@/lib/fishSchedule";
import { useApp } from "@/store/app";
import { ClownfishSvg } from "./Clownfish";
import { useMedia } from "@/hooks/useMedia";


function useDocumentHidden(): boolean {
  const [hidden, setHidden] = useState(() => typeof document !== "undefined" && document.hidden);
  useEffect(() => {
    const f = () => setHidden(document.hidden);
    document.addEventListener("visibilitychange", f);
    return () => document.removeEventListener("visibilitychange", f);
  }, []);
  return hidden;
}

/** Only animate while the band is on screen (it sits in the page flow, above the footer). */
function useInView(ref: React.RefObject<HTMLElement>): boolean {
  const [inView, setInView] = useState(true);
  useEffect(() => {
    const el = ref.current;
    if (!el || typeof IntersectionObserver === "undefined") return;
    const io = new IntersectionObserver((entries) => setInView(entries.some((e) => e.isIntersecting)), { threshold: 0 });
    io.observe(el);
    return () => io.disconnect();
  }, [ref]);
  return inView;
}

/**
 * Decorative blue clownfish. It swims through its own reserved, empty band near the bottom of the
 * page (this element; no content is ever placed inside it), so it cannot cross forecasts, safety
 * banners, inputs, tooltips or chart legends. Behind content, aria-hidden, pointer-events none,
 * transform/opacity only, at most three fish, softly blurred, low opacity. Off for reduced motion,
 * the Profile setting, the backend flag, safety alerts, presentation/report views, print, hidden
 * tabs, small screens and constrained devices. It never signals anything clinical.
 */
export function ClownfishLayer({ suppressed = false, tone = "paper" }: { suppressed?: boolean; tone?: "paper" | "night" }) {
  const band = useRef<HTMLDivElement>(null);
  const userEnabled = useApp((s) => s.fish);
  const safetyAlert = useApp((s) => !!s.safetyAlert);
  const presentation = useApp((s) => s.presentation);
  const caps = useCapabilities();
  const reducedMotion = !!useReducedMotion();
  const smallScreen = useMedia("(max-width: 767px)");
  const hidden = useDocumentHidden();
  const inView = useInView(band);
  const [constrained] = useState(() => typeof navigator !== "undefined" && isConstrainedDevice(navigator as Navigator & { connection?: { saveData?: boolean } }));
  const [pass, setPass] = useState<(PassPlan & { key: number }) | null>(null);
  const seq = useRef(0);

  const allowed = fishAllowed({
    userEnabled,
    backendEnabled: capFlags(caps.data).fish,
    reducedMotion,
    safetyAlert,
    presentationOrReport: presentation || suppressed,
    hidden,
    smallScreen,
    constrained,
  });
  const run = allowed && inView;

  // One scheduler per mount; paused/resumed as conditions change, stopped on unmount.
  const sched = useRef<ReturnType<typeof createFishScheduler> | null>(null);
  useEffect(() => {
    const s = createFishScheduler({
      rand: Math.random,
      onPass: (p) => {
        seq.current += 1;
        setPass({ ...p, key: seq.current });
      },
    });
    sched.current = s;
    return () => {
      s.stop();
      sched.current = null;
    };
  }, []);
  useEffect(() => {
    const s = sched.current;
    if (!s) return;
    if (run) s.resume();
    else {
      s.pause();
      setPass(null); // a disabling condition (e.g. a safety alert) removes a fish mid-pass at once
    }
  }, [run]);

  if (!allowed) return <div ref={band} className="fish-band no-print presentation-hide" aria-hidden="true" data-fish-band="off" />;

  return (
    <div ref={band} className="fish-band no-print presentation-hide" aria-hidden="true" data-fish-band="on">
      {pass && <FishPass key={pass.key} plan={pass} tone={tone} onDone={() => setPass(null)} />}
    </div>
  );
}

function FishPass({ plan, tone, onDone }: { plan: PassPlan; tone: "paper" | "night"; onDone: () => void }) {
  const refs = useRef<(HTMLDivElement | null)[]>([]);
  const done = useRef(onDone);
  done.current = onDone;
  useEffect(() => {
    const anims: Animation[] = [];
    const flip = plan.direction === "rtl" ? " scaleX(-1)" : "";
    const width = refs.current[0]?.parentElement?.clientWidth ?? (typeof window !== "undefined" ? window.innerWidth : 1200);
    const left = -80;
    const right = width + 20;
    const [from, to] = plan.direction === "ltr" ? [left, right] : [right, left];
    const at = (f: number) => Math.round(from + (to - from) * f);
    plan.fish.slice(0, MAX_FISH).forEach((f, i) => {
      const el = refs.current[i];
      if (!el || typeof el.animate !== "function") return;
      const tf = (x: number) => `translate3d(${x}px, 0, 0)${flip} scale(${f.scale})`;
      anims.push(
        el.animate(
          [
            { transform: tf(from), opacity: 0 },
            { transform: tf(at(0.12)), opacity: 1, offset: 0.12 },
            { transform: tf(at(0.88)), opacity: 1, offset: 0.88 },
            { transform: tf(to), opacity: 0 },
          ],
          { duration: plan.durationMs, delay: f.delayMs, easing: "linear", fill: "both" },
        ),
      );
    });
    if (anims.length === 0) {
      done.current();
      return;
    }
    let cancelled = false;
    void Promise.allSettled(anims.map((a) => a.finished)).then(() => !cancelled && done.current());
    return () => {
      cancelled = true;
      anims.forEach((a) => a.cancel());
    };
  }, [plan]);
  return (
    <>
      {plan.fish.slice(0, MAX_FISH).map((f, i) => (
        <div
          key={i}
          ref={(el) => {
            refs.current[i] = el;
          }}
          className={`fish ${tone === "night" ? "fish-night" : ""}`}
          style={{ top: `calc(${f.lane * 100}% - 14px)` }}
        >
          <ClownfishSvg className="h-7 w-[52px]" />
        </div>
      ))}
    </>
  );
}

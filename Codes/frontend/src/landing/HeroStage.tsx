// Mounts the sign-in animation (its own lazy chunk) only where WebGL works; otherwise nothing is
// drawn and the page keeps its static night scene. Decorative: hidden from assistive technology.
import { Component, Suspense, lazy, useEffect, useRef, useState, type ReactNode, type RefObject } from "react";
import { useReducedMotion } from "framer-motion";
import { hasWebGL } from "@/lib/stageRender";
import type { StageBox } from "./TwinHero";

const TwinHero = lazy(() => import("./TwinHero"));

/** `?heroAt=9.5` freezes the animation at that moment of the loop (screenshots, reviews). */
function stillFromUrl(): number | null {
  if (typeof window === "undefined") return null;
  const v = Number.parseFloat(new URLSearchParams(window.location.search).get("heroAt") ?? "");
  return Number.isFinite(v) ? v : null;
}

class Quiet extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() {
    return { failed: true };
  }
  render() {
    return this.state.failed ? null : this.props.children;
  }
}

/**
 * `measure` turns the canvas rectangle into the figure's box (canvas pixels): horizontal centre,
 * top of the head and the soles. It is re-run on resize and when `anchor` changes size.
 */
export function HeroStage({
  className,
  measure,
  anchor,
}: {
  className?: string;
  measure: (canvas: DOMRect) => StageBox;
  anchor?: RefObject<HTMLElement>;
}) {
  const reduce = useReducedMotion() ?? false;
  const [webgl] = useState(hasWebGL);
  const [ready, setReady] = useState(false);
  const [lost, setLost] = useState(false);
  const [boxKey, setBoxKey] = useState(0);
  const [stillAt] = useState(stillFromUrl);
  const wrap = useRef<HTMLDivElement>(null);
  const box = useRef<StageBox | null>(null);
  const measureRef = useRef(measure);
  measureRef.current = measure;

  useEffect(() => {
    const el = wrap.current;
    if (!el) return;
    const update = () => {
      box.current = measureRef.current(el.getBoundingClientRect());
      setBoxKey((k) => k + 1);
    };
    update();
    const ro = new ResizeObserver(update);
    ro.observe(el);
    if (anchor?.current) ro.observe(anchor.current);
    window.addEventListener("resize", update);
    return () => {
      ro.disconnect();
      window.removeEventListener("resize", update);
    };
  }, [anchor, webgl]);

  if (!webgl || lost) return null;
  return (
    <div
      ref={wrap}
      aria-hidden
      data-testid="hero-stage"
      className={`pointer-events-none transition-opacity duration-500 ease-out ${ready ? "opacity-100" : "opacity-0"} ${className ?? ""}`}
    >
      <Quiet>
        <Suspense fallback={null}>
          <TwinHero box={box} boxKey={boxKey} reducedMotion={reduce} stillAt={stillAt} onReady={() => setReady(true)} onLost={() => setLost(true)} />
        </Suspense>
      </Quiet>
    </div>
  );
}

import { useId } from "react";
import { FISH_BANDS, FISH_BODY, FISH_DORSAL, FISH_PECTORAL, FISH_TAIL, FISH_VIEWBOX } from "./fishShape";

/** The NemoTwins clownfish as an inline SVG (shape in ./fishShape). Purely decorative. */
export function ClownfishSvg({
  className,
  style,
  body = "#3A86E8",
  shade = "#1F5DB8",
  band = "#EAF4FF",
  outline = "#0B2547",
}: {
  className?: string;
  style?: React.CSSProperties;
  body?: string;
  shade?: string;
  band?: string;
  outline?: string;
}) {
  const id = useId().replace(/:/g, "");
  return (
    <svg viewBox={FISH_VIEWBOX} className={className} style={style} aria-hidden="true" focusable="false">
      <defs>
        <clipPath id={`fb-${id}`}>
          <path d={FISH_BODY} />
        </clipPath>
        <linearGradient id={`fg-${id}`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor={body} />
          <stop offset="1" stopColor={shade} />
        </linearGradient>
      </defs>
      <path d={FISH_TAIL} fill={shade} stroke={outline} strokeWidth="1.2" strokeLinejoin="round" />
      <path d={FISH_DORSAL} fill={shade} stroke={outline} strokeWidth="1.2" strokeLinejoin="round" />
      <path d={FISH_BODY} fill={`url(#fg-${id})`} />
      <g clipPath={`url(#fb-${id})`}>
        {FISH_BANDS.map((d) => (
          <path key={d} d={d} fill={band} stroke={outline} strokeWidth="1.6" />
        ))}
      </g>
      <path d={FISH_BODY} fill="none" stroke={outline} strokeWidth="1.4" />
      <path d={FISH_PECTORAL} fill={shade} stroke={outline} strokeWidth="1" strokeLinejoin="round" />
      <circle cx="103" cy="27" r="3.4" fill={outline} />
      <circle cx="104.2" cy="25.9" r="1" fill={band} />
    </svg>
  );
}

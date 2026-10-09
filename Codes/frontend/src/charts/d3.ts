// The few d3 pieces the charts use, imported from the d3 submodules. Importing the "d3" umbrella
// package also pulls in d3-selection, d3-transition and friends (side-effectful, not tree-shaken).
export { scaleBand, scaleLinear, scalePoint, scaleSqrt, scaleTime } from "d3-scale";
export type { ScaleLinear, ScaleTime } from "d3-scale";
export { area, curveMonotoneX, line } from "d3-shape";
export { bisector, extent, max, min } from "d3-array";
export { timeHour } from "d3-time";

/** How full the trust-ramp meter is, 0 to 100. A target of 0 (or a value that isn't a finite number) is an empty
 *  meter, never NaN % or Infinity % in the meter's width. */
export function rampPercent(count: number, target: number): number {
  if (!Number.isFinite(count) || !Number.isFinite(target) || target <= 0 || count <= 0) return 0;
  return Math.min(100, Math.round((count / target) * 100));
}

/** Visual height for a building footprint. Measured values stay untouched. */

export function buildingHeight(properties, rule) {
  const measured = Number(properties.height);
  if (Number.isFinite(measured) && measured > 0) return { meters: measured, source: "measured" };
  const levels = Number(properties.levels);
  if (Number.isFinite(levels) && levels > 0) {
    return { meters: levels * rule.metersPerLevel, source: "estimated" };
  }
  return { meters: null, source: "provisional" };
}

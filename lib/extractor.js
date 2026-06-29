export function extractIndicators(text, indicatorDefs){
  if(!text || !Array.isArray(indicatorDefs) || indicatorDefs.length === 0){
    return [];
  }

  const defs = indicatorDefs
    .filter(def => def && typeof def.name === "string" && def.name.trim())
    .map(def => ({
      id: def.id || "",
      name: def.name.trim(),
      match_name: String(def.match_name || def.name || "").trim(),
      unit_default: def.unit_default || ""
    }));

  if(defs.length === 0) return [];

  const bestByName = new Map();
  const numberRegex = /-?\d+(?:\.\d+)?%?/g;

  let match;
  while((match = numberRegex.exec(text)) !== null){
    const rawValue = match[0];
    const numberStart = match.index;
    const numberEnd = numberStart + rawValue.length;
    const contextStart = Math.max(0, numberStart - 10);
    const context = text.slice(contextStart, numberStart);

    let bestDef = null;
    let bestDistance = Infinity;

    for(const def of defs){
      const pos = context.lastIndexOf(def.match_name || def.name);
      if(pos === -1) continue;
      const distance = context.length - (pos + (def.match_name || def.name).length);
      if(distance < bestDistance){
        bestDistance = distance;
        bestDef = def;
      }
    }

    if(!bestDef) continue;

    const evidenceStart = Math.max(0, numberStart - 24);
    const evidenceEnd = Math.min(text.length, numberEnd + 12);
    const evidence = text.slice(evidenceStart, evidenceEnd).replace(/\s+/g, " ").trim();
    const confidence = Number((0.95 - (bestDistance / 10) * 0.35).toFixed(2));

    const candidate = {
      indicator_id: bestDef.id || "",
      name: bestDef.name,
      suggested_value: rawValue,
      unit_default: rawValue.endsWith("%") ? "%" : bestDef.unit_default,
      confidence: Math.max(0.5, confidence),
      evidence
    };

    const prev = bestByName.get(bestDef.name);
    if(!prev){
      bestByName.set(bestDef.name, { ...candidate, _distance: bestDistance });
      continue;
    }

    if(bestDistance < prev._distance){
      bestByName.set(bestDef.name, { ...candidate, _distance: bestDistance });
    }
  }

  return Array.from(bestByName.values()).map(item => {
    return {
      indicator_id: item.indicator_id || "",
      name: item.name,
      suggested_value: item.suggested_value,
      unit_default: item.unit_default,
      confidence: item.confidence,
      evidence: item.evidence
    };
  });
}

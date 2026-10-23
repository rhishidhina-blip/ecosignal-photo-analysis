export type ModelComponent = {
  status: 'available' | 'rejected_low_confidence' | 'failed' | 'unavailable';
  value?: { coverage_percent?: number; growth_form?: string; raw_prediction?: string; decision?: string } | null;
  confidence?: number;
  version: string;
  warnings?: string[];
};
export type PhotoAnalysis = {
  status: string;
  coverage: ModelComponent;
  growth_form: ModelComponent;
  media: { coverage_mask?: string; coverage_overlay?: string };
  warnings: string[];
  image_sha256: string;
  coverage_basis: string;
};

export function validateAnalysis(value: unknown): PhotoAnalysis {
  const j = value as PhotoAnalysis;
  if (!j || !j.coverage || !j.growth_form || !j.media || !Array.isArray(j.warnings)) throw Error('Invalid analysis response');
  for (const c of [j.coverage, j.growth_form]) {
    if (!['available','rejected_low_confidence','failed','unavailable'].includes(c.status) || typeof c.version !== 'string') throw Error('Invalid model status');
    if (c.confidence !== undefined && (!Number.isFinite(c.confidence) || c.confidence < 0 || c.confidence > 1)) throw Error('Invalid model confidence');
  }
  const coverage = j.coverage.value?.coverage_percent;
  if (coverage !== undefined && (!Number.isFinite(coverage) || coverage < 0 || coverage > 100)) throw Error('Invalid coverage');
  if (j.coverage.status === 'available' && coverage === undefined) throw Error('Coverage is missing');
  const form = j.growth_form.value?.growth_form;
  if (j.growth_form.status === 'available' && !['crustose','foliose','fruticose'].includes(form || '')) throw Error('Invalid growth form');
  for (const src of Object.values(j.media)) if (src && !/^data:image\/png;base64,[A-Za-z0-9+/=]+$/.test(src)) throw Error('Invalid image output');
  return j;
}

export async function analyzePhoto(image: File, signal: AbortSignal): Promise<PhotoAnalysis> {
  const body = new FormData();
  body.append('image', image);
  const r = await fetch('/api/analyze', { method: 'POST', body, signal });
  const j = await r.json().catch(() => null);
  if (!r.ok) throw Error(typeof j?.detail === 'string' ? j.detail : `Analysis unavailable (${r.status}). Please retry.`);
  return validateAnalysis(j);
}

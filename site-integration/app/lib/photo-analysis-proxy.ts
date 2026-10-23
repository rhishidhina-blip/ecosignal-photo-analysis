type PhotoEnv = { ECOSIGNAL_ANALYSIS_URL?: string; ECOSIGNAL_ANALYSIS_TOKEN?: string };
const MAX_BYTES = 8 * 1024 * 1024 + 65536;

export async function handlePhotoAnalysis(request: Request, env: PhotoEnv): Promise<Response> {
  const error = (detail: string, status: number) => Response.json({ detail }, { status, headers: { 'Cache-Control': 'no-store' } });
  if (request.method !== 'POST') return error('Use POST to analyze a photograph.', 405);
  // Browser requests must originate from this site. This is not a substitute for site access control.
  const origin = request.headers.get('origin');
  if (origin && origin !== new URL(request.url).origin) return error('Cross-site request rejected.', 403);
  if (!env.ECOSIGNAL_ANALYSIS_URL || !env.ECOSIGNAL_ANALYSIS_TOKEN) return error('Photo analysis is not configured yet.', 503);
  let url: URL;
  try {
    url = new URL('/analyze', env.ECOSIGNAL_ANALYSIS_URL);
    if (url.protocol !== 'https:') throw Error();
  } catch { return error('The analysis service URL is invalid.', 503); }
  if (!request.headers.get('content-type')?.startsWith('multipart/form-data;')) return error('Upload a photograph using multipart/form-data.', 415);
  if (Number(request.headers.get('content-length') || 0) > MAX_BYTES) return error('Choose a photograph under 8 MB.', 413);
  const reader = request.body?.getReader();
  if (!reader) return error('Choose a photograph.', 422);
  const chunks: Uint8Array[] = []; let bytes = 0;
  try {
    for (;;) {
      const next = await reader.read();
      if (next.done) break;
      bytes += next.value.byteLength;
      if (bytes > MAX_BYTES) { await reader.cancel(); return error('Choose a photograph under 8 MB.', 413); }
      chunks.push(next.value);
    }
  } finally { reader.releaseLock(); }
  const body = new Uint8Array(bytes); let offset = 0;
  for (const chunk of chunks) { body.set(chunk, offset); offset += chunk.byteLength; }
  try {
    const upstream = await fetch(url, {
      method: 'POST', body,
      headers: { 'Content-Type': request.headers.get('content-type')!, 'Authorization': `Bearer ${env.ECOSIGNAL_ANALYSIS_TOKEN}` },
      signal: AbortSignal.timeout(120000), redirect: 'error'
    });
    // Avoid exposing proxy secrets or host error pages to the browser.
    if (!upstream.headers.get('content-type')?.includes('application/json')) return error('Analysis service did not return results. Please retry.', 502);
    if (upstream.status === 401) return error('The analysis service token needs updating.', 503);
    return new Response(upstream.body, { status: upstream.status, headers: { 'Content-Type': 'application/json', 'Cache-Control': 'no-store' } });
  } catch { return error('Photo analysis timed out or could not connect. Please retry.', 504); }
}

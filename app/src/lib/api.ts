/**
 * The sidecar client.
 *
 * Two methods on purpose, mirroring memopop-native's transport seam whose
 * CLAUDE.md warns against adding a third casually. Everything the app does is
 * `get` or `post` against the Python sidecar on localhost.
 */

const BASE = 'http://127.0.0.1:8787';

export interface SourceRow {
  path: string;
  domain: string;
  title: string;
  status: string;
  content_pulled: boolean;
  published_at: string;
  fetched_at: string;
  excerpt: string;
  url: string;
  error: string;
}

export interface Meta {
  label: string;
  total: number;
  domains: string[];
  writable: boolean;
}

export interface CaptureResult {
  path: string;
  created: boolean;
  duplicate_of: string;
  title: string;
  status: string;
  content_pulled: boolean;
  machine_verdict: string;
}

async function get<T>(path: string, params: Record<string, string> = {}): Promise<T> {
  const qs = new URLSearchParams(params).toString();
  const res = await fetch(`${BASE}${path}${qs ? `?${qs}` : ''}`);
  if (!res.ok) throw new Error(`${res.status} ${await res.text()}`);
  return res.headers.get('content-type')?.includes('json')
    ? ((await res.json()) as T)
    : ((await res.text()) as unknown as T);
}

async function post<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(body)
  });
  if (!res.ok) {
    const detail = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(detail.detail ?? `${res.status}`);
  }
  return (await res.json()) as T;
}

export const api = {
  meta: () => get<Meta>('/api/meta'),
  sources: (prefix = '', search = '') =>
    get<{ rows: SourceRow[]; total: number; domains: string[] }>('/api/sources', {
      prefix,
      search
    }),
  source: (path: string) => get<string>('/api/source', { path }),
  capture: (url: string, domain: string, full: boolean) =>
    post<CaptureResult>('/api/capture', { url, domain: domain || null, full })
};

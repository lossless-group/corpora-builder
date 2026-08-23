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
  /** The content-addressed object this source's PDF lives in. Empty for
   *  text-only sources, which are most of them. */
  binary_key: string;
  /** '' | 'present' | 'not_downloaded'. Absent is a state with an affordance,
   *  never an error and never a silent fetch. */
  binary_state: string;
  binary_bytes: number;
  binary_optimized: boolean;
}

/** One unit of work against the corpus. Engine-agnostic by design — git today,
 *  possibly a Kopia repository later, without this shape changing. */
export interface Change {
  id: string;
  when: string;
  who: string;
  subject: string;
  verb: string | null;
  scope: string | null;
  sentence: string;
  added: string[];
  changed: string[];
  removed: string[];
  renamed: { old: string; new: string }[];
  counts: { added: number; changed: number; removed: number; renamed: number };
  bytes: number;
}

export interface ChangePage {
  truncated: boolean;
  count: number;
  changes: Change[];
}

export interface Meta {
  label: string;
  total: number;
  domains: string[];
  focuses: FocusDef[];
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

/** A domain's own declaration, read from its index.md. The `type` is open —
 *  `strategy`, `topic`, `thesis`, whatever a client's corpus declares. */
export interface FocusDef {
  value: string;
  label: string;
  type: string;
  folder: string;
  path: string;
}

export interface TreeNode {
  name: string;
  path: string;
  is_dir: boolean;
  count: number;
  children: TreeNode[];
}

export const api = {
  meta: () => get<Meta>('/api/meta'),
  // `domain` is a folder name, not a key prefix — the server maps it through
  // `_domain_of`, so the client never learns which storage layout it is talking
  // to. Sending `<domain>/` as a raw prefix worked for reach-edu and silently
  // matched nothing in a corpus this tool wrote.
  sources: (domain = '', search = '', focus = '') =>
    get<{ rows: SourceRow[]; total: number; domains: string[]; focused_total: number }>(
      '/api/sources',
      { domain, search, focus }
    ),
  source: (path: string) => get<string>('/api/source', { path }),
  capture: (url: string, domain: string, full: boolean) =>
    post<CaptureResult>('/api/capture', { url, domain: domain || null, full }),

  /** The whole corpus as a folder tree. One key listing, no file bodies. */
  tree: () => get<{ total: number; tree: TreeNode[] }>('/api/tree'),

  changes: (repo: string, prefix = '', limit = 20) =>
    get<ChangePage>('/api/changes', { repo, prefix, limit: String(limit) }),

  /** The URL a binary can be opened or downloaded from. Not a `get` because the
   *  browser fetches it directly — handing an <a href> to the viewer is the
   *  whole point, and streaming it through JS would only add a copy. */
  binaryUrl: (key: string) => `${BASE}/api/binary?key=${encodeURIComponent(key)}`
};

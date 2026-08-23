/**
 * What the workspace trigger says — `context-v/specs/Header-Chrome.md`.
 *
 * Pure, so the degradation rule can be tested without a Svelte runtime. It is
 * the rule rather than the rendering that went wrong: the trigger rendered an
 * em dash for a client holding a `meta` payload from a sidecar that predated the
 * `workspace` field, while `label` — the name the server has always sent — sat
 * unused beside it.
 */
import type { WorkspaceInfo } from './api';

/** Never blank while any name is available. */
export function workspaceLabel(ws: WorkspaceInfo | null, label = ''): string {
  return ws?.display_name || label || '—';
}

/**
 * Where the bytes live, or `''` when we were not told.
 *
 * A missing `workspace` is not the same as a local folder, and saying "local
 * folder" because a field was absent is a confident wrong answer about somebody
 * else's corpus.
 */
export function workspaceStorage(ws: WorkspaceInfo | null): string {
  if (!ws) return '';
  return ws.bucket ? `bucket ${ws.bucket}` : 'local folder';
}

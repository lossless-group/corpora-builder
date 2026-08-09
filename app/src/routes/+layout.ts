// Static adapter: no SSR, prerender the shell. The Tauri webview loads a file,
// not a server.
export const prerender = true;
export const ssr = false;

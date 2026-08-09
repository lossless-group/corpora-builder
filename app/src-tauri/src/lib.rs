//! The Tauri shell. Spawns the Python sidecar, waits for it, kills it on exit.
//!
//! Deliberately smaller than memopop-native's equivalent, for two reasons.
//!
//! **The webview talks to the sidecar directly** over `127.0.0.1`, rather than
//! through a Rust dispatcher. memopop routes every call through an
//! `api_dispatch` allowlist whose fallback is `not_found` — a real trap its own
//! handoff notes warn about, because every new endpoint needs a matching Rust
//! entry or it silently 404s. Since this app has no per-call logic to add on
//! the Rust side, forwarding would be pure ceremony. The cost is that the
//! sidecar's CORS list is now part of the contract (see `src/server/app.py`).
//!
//! **There is nothing to anchor.** memopop's sidecar lives in a separate repo
//! the operator must locate before anything works — the first step of its
//! onboarding and the first thing that goes wrong. corpora-builder's Python is
//! in this repo, so the path is derived, not asked for.
//!
//! The self-healing entry is copied verbatim in spirit: ALWAYS probe `/healthz`
//! before trusting a tracked child. A dead-but-still-tracked process routes
//! requests into the void until the app restarts.

use std::path::{Path, PathBuf};
use std::sync::Mutex;
use std::time::{Duration, Instant};

use tauri::Manager;
use tauri_plugin_shell::process::CommandChild;
use tauri_plugin_shell::ShellExt;

const SIDECAR_HOST: &str = "127.0.0.1";
const SIDECAR_PORT: u16 = 8787;
const HEALTHZ_TIMEOUT_SECS: u64 = 20;
const HEALTHZ_POLL_MS: u64 = 250;

#[derive(Default)]
struct Sidecar {
    child: Mutex<Option<CommandChild>>,
}

fn sidecar_url(path: &str) -> String {
    format!("http://{SIDECAR_HOST}:{SIDECAR_PORT}{path}")
}

/// The repo root, from the compiled binary's location or the dev cwd.
///
/// `CARGO_MANIFEST_DIR` is `app/src-tauri`, so the repo is two levels up. In a
/// bundled app that constant still points at the build machine, so the env
/// override exists for the packaging work that has not happened yet.
fn repo_root() -> PathBuf {
    if let Ok(explicit) = std::env::var("CORPORA_REPO") {
        return PathBuf::from(explicit);
    }
    Path::new(env!("CARGO_MANIFEST_DIR"))
        .parent()
        .and_then(|p| p.parent())
        .map(Path::to_path_buf)
        .unwrap_or_else(|| PathBuf::from("."))
}

fn venv_python(repo: &Path) -> Option<PathBuf> {
    for candidate in [".venv/bin/python", ".venv/Scripts/python.exe"] {
        let path = repo.join(candidate);
        if path.exists() {
            return Some(path);
        }
    }
    None
}

async fn healthz_ok() -> bool {
    let client = match reqwest::Client::builder()
        .timeout(Duration::from_secs(2))
        .build()
    {
        Ok(c) => c,
        Err(_) => return false,
    };
    matches!(client.get(sidecar_url("/healthz")).send().await, Ok(r) if r.status().is_success())
}

async fn ensure_sidecar<R: tauri::Runtime>(app: &tauri::AppHandle<R>) -> Result<(), String> {
    // Probe first, always. A tracked handle proves nothing about a live process.
    if healthz_ok().await {
        return Ok(());
    }

    if let Some(state) = app.try_state::<Sidecar>() {
        if let Ok(mut guard) = state.child.lock() {
            if let Some(child) = guard.take() {
                let _ = child.kill();
            }
        }
    }

    let repo = repo_root();
    let python = venv_python(&repo).ok_or_else(|| {
        format!(
            "No Python venv at {}/.venv — run `uv sync --extra dev` in the repo first.",
            repo.display()
        )
    })?;

    let (mut rx, child) = app
        .shell()
        .command(python.to_string_lossy().as_ref())
        .args(["-m", "src.server"])
        .current_dir(repo.clone())
        .env("CORPORA_PORT", SIDECAR_PORT.to_string())
        .spawn()
        .map_err(|e| format!("Failed to spawn the sidecar: {e}"))?;

    // Drain the child's pipes so they cannot fill and block it.
    tauri::async_runtime::spawn(async move { while rx.recv().await.is_some() {} });

    let deadline = Instant::now() + Duration::from_secs(HEALTHZ_TIMEOUT_SECS);
    while Instant::now() < deadline {
        tokio::time::sleep(Duration::from_millis(HEALTHZ_POLL_MS)).await;
        if healthz_ok().await {
            if let Some(state) = app.try_state::<Sidecar>() {
                if let Ok(mut guard) = state.child.lock() {
                    *guard = Some(child);
                }
            }
            return Ok(());
        }
    }

    // Timed out. Kill what we started rather than leaking it.
    let _ = child.kill();
    Err(format!(
        "The sidecar did not become healthy on {SIDECAR_HOST}:{SIDECAR_PORT} within {HEALTHZ_TIMEOUT_SECS}s"
    ))
}

/// What the frontend calls on mount to learn whether the backend is up.
#[tauri::command]
async fn sidecar_status(app: tauri::AppHandle) -> Result<serde_json::Value, String> {
    ensure_sidecar(&app).await?;
    Ok(serde_json::json!({ "ok": true, "base": sidecar_url("") }))
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_opener::init())
        .manage(Sidecar::default())
        .invoke_handler(tauri::generate_handler![sidecar_status])
        .setup(|app| {
            let handle = app.handle().clone();
            // Eagerly, not lazily: this app does exactly one thing, and making
            // the operator wait for a first request to discover the backend is
            // broken is worse than waiting two seconds at launch.
            tauri::async_runtime::spawn(async move {
                if let Err(err) = ensure_sidecar(&handle).await {
                    eprintln!("[corpora] sidecar: {err}");
                }
            });
            Ok(())
        })
        .on_window_event(|window, event| {
            if let tauri::WindowEvent::Destroyed = event {
                if let Some(state) = window.try_state::<Sidecar>() {
                    if let Ok(mut guard) = state.child.lock() {
                        if let Some(child) = guard.take() {
                            let _ = child.kill();
                        }
                    }
                }
            }
        })
        .run(tauri::generate_context!())
        .expect("error while running corpora");
}

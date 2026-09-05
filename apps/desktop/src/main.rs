// Prevents additional console window on Windows in release, DO NOT REMOVE!!
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::ffi::OsStr;
use std::path::PathBuf;

fn main() {
    let mut args = std::env::args_os().skip(1);
    let first = args.next();
    if first.as_deref() == Some(OsStr::new("--diagnostics-file")) {
        let Some(output_path) = args.next().map(PathBuf::from) else {
            std::process::exit(2);
        };
        if args.next().is_some()
            || !output_path.is_absolute()
            || output_path.parent().is_none_or(|parent| !parent.is_dir())
        {
            std::process::exit(2);
        }
        std::process::exit(run_diagnostics(output_path));
    }
    xagent_desktop_lib::run();
}

fn run_diagnostics(output_path: PathBuf) -> i32 {
    let backend_url = std::env::var("XAGENT_DESKTOP_API_URL")
        .unwrap_or_else(|_| "http://127.0.0.1:8000".to_string());
    let runtime = match tokio::runtime::Runtime::new() {
        Ok(runtime) => runtime,
        Err(_) => return 1,
    };
    let result = runtime.block_on(xagent_desktop_lib::diagnose_backend(&backend_url));
    let (document, exit_code) = match result {
        Ok(health) => (
            serde_json::json!({
                "desktop_version": env!("CARGO_PKG_VERSION"),
                "backend_url": backend_url,
                "backend_status": health.get("status").and_then(|value| value.as_str()).unwrap_or("ok"),
                "backend_version": health.get("version").and_then(|value| value.as_str()).unwrap_or(""),
            }),
            0,
        ),
        Err(error) => (
            serde_json::json!({
                "desktop_version": env!("CARGO_PKG_VERSION"),
                "backend_url": backend_url,
                "backend_status": "failed",
                "backend_version": "",
                "error": error,
            }),
            1,
        ),
    };
    let payload = match serde_json::to_vec_pretty(&document) {
        Ok(mut payload) => {
            payload.push(b'\n');
            payload
        }
        Err(_) => return 1,
    };
    if std::fs::write(output_path, payload).is_err() {
        return 1;
    }
    exit_code
}

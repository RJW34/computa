// Prevents additional console window on Windows in release
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::process::Command;
use std::path::PathBuf;
use tauri::Manager;

/// Get the path to the bundled abso.exe sidecar
fn get_sidecar_path(app_handle: Option<&tauri::AppHandle>) -> PathBuf {
    // In production: use the bundled sidecar
    if let Some(handle) = app_handle {
        if let Ok(resource_dir) = handle.path().resource_dir() {
            let sidecar = resource_dir.join("binaries").join("abso.exe");
            if sidecar.exists() {
                return sidecar;
            }
        }
    }

    // Fallback for development: look for dist/abso.exe in project root
    let dev_paths = [
        PathBuf::from("../../dist/abso.exe"),        // From src-tauri
        PathBuf::from("../dist/abso.exe"),           // From gui
        PathBuf::from("dist/abso.exe"),              // From project root
    ];

    for path in &dev_paths {
        if path.exists() {
            return path.clone();
        }
    }

    // Ultimate fallback: assume it's in PATH or use python
    PathBuf::from("abso.exe")
}

/// Check if the bundled CLI exists, otherwise fall back to Python
fn should_use_python() -> bool {
    let dev_paths = [
        PathBuf::from("../../dist/abso.exe"),
        PathBuf::from("../dist/abso.exe"),
        PathBuf::from("dist/abso.exe"),
    ];

    for path in &dev_paths {
        if path.exists() {
            return false;
        }
    }

    // No bundled exe found, use Python
    true
}

/// Run an ABSO CLI command and return the output
#[tauri::command]
async fn run_abso_command(
    app_handle: tauri::AppHandle,
    command: String,
    args: Vec<String>,
) -> Result<String, String> {
    let output = if should_use_python() {
        // Development mode: use Python
        Command::new("python")
            .args(["-m", "abso", &command])
            .args(&args)
            .current_dir(get_project_root())
            .output()
            .map_err(|e| format!("Failed to execute Python command: {}", e))?
    } else {
        // Production mode: use bundled sidecar
        let sidecar_path = get_sidecar_path(Some(&app_handle));
        Command::new(&sidecar_path)
            .arg(&command)
            .args(&args)
            .output()
            .map_err(|e| format!("Failed to execute sidecar: {} (path: {:?})", e, sidecar_path))?
    };

    if output.status.success() {
        Ok(String::from_utf8_lossy(&output.stdout).to_string())
    } else {
        let stderr = String::from_utf8_lossy(&output.stderr).to_string();
        let stdout = String::from_utf8_lossy(&output.stdout).to_string();
        Err(format!(
            "Command failed (exit code {:?}):\nstderr: {}\nstdout: {}",
            output.status.code(),
            stderr,
            stdout
        ))
    }
}

/// Run an ABSO CLI command with JSON output
#[tauri::command]
async fn run_abso_json(
    app_handle: tauri::AppHandle,
    command: String,
    args: Vec<String>,
) -> Result<String, String> {
    let mut full_args = args;
    full_args.push("--json".to_string());

    run_abso_command(app_handle, command, full_args).await
}

/// Check if running as administrator
#[tauri::command]
fn is_admin() -> bool {
    #[cfg(windows)]
    {
        // Simple check: try to read a protected registry key
        use std::process::Command;
        let output = Command::new("net")
            .args(["session"])
            .output();

        match output {
            Ok(o) => o.status.success(),
            Err(_) => false,
        }
    }

    #[cfg(not(windows))]
    {
        false
    }
}

/// Get the path to the ABSO Python project root (for dev mode)
fn get_project_root() -> PathBuf {
    // Go up from src-tauri to gui, then up to project root
    std::env::current_dir()
        .map(|p| {
            p.parent() // gui
                .and_then(|p| p.parent()) // project root
                .map(|p| p.to_path_buf())
                .unwrap_or_else(|| p.clone())
        })
        .unwrap_or_else(|_| PathBuf::from("."))
}

/// Get info about the CLI backend being used
#[tauri::command]
fn get_backend_info(app_handle: tauri::AppHandle) -> serde_json::Value {
    let using_python = should_use_python();
    let sidecar_path = get_sidecar_path(Some(&app_handle));

    serde_json::json!({
        "mode": if using_python { "python" } else { "bundled" },
        "sidecar_path": sidecar_path.to_string_lossy(),
        "sidecar_exists": sidecar_path.exists(),
    })
}

fn main() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .invoke_handler(tauri::generate_handler![
            run_abso_command,
            run_abso_json,
            is_admin,
            get_backend_info,
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}

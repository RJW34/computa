// Prevents additional console window on Windows in release
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::process::Command;
use std::path::PathBuf;
use std::sync::Mutex;
use tauri::{
    Emitter,
    Manager,
    menu::{Menu, MenuItem, PredefinedMenuItem, Submenu},
    tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent},
    image::Image,
};

/// Available profiles for quick switching
const PROFILES: &[(&str, &str)] = &[
    ("rivals2", "Rivals of Aether 2"),
    ("rivals2-oled", "Rivals 2 (OLED)"),
    ("slippi-melee", "Slippi Melee"),
    ("slippi-melee-oled", "Slippi Melee (OLED)"),
    ("cod-bo7", "CoD: Black Ops 7"),
    ("cod-bo7-oled", "CoD: BO7 (OLED)"),
    ("diablo4", "Diablo 4"),
    ("diablo4-oled", "Diablo 4 (OLED)"),
    ("pacdeluxe", "PAC Deluxe"),
    ("pacdeluxe-oled", "PAC Deluxe (OLED)"),
];

/// State to track the currently active profile
struct AppState {
    active_profile: Mutex<Option<String>>,
}

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

/// Check if we should use Python (development) or bundled exe (production)
fn should_use_python() -> bool {
    // In debug builds, always use Python for consistent data paths
    #[cfg(debug_assertions)]
    {
        return true;
    }

    // In release builds, check for bundled sidecar
    #[cfg(not(debug_assertions))]
    {
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

/// Get the currently active profile
#[tauri::command]
fn get_active_profile(state: tauri::State<AppState>) -> Option<String> {
    // Handle poisoned mutex gracefully - return None instead of panicking
    state.active_profile.lock().ok().and_then(|guard| guard.clone())
}

/// Set the active profile (called from frontend after applying)
#[tauri::command]
fn set_active_profile(state: tauri::State<AppState>, profile_id: Option<String>) {
    // Handle poisoned mutex gracefully - log error instead of panicking
    if let Ok(mut guard) = state.active_profile.lock() {
        *guard = profile_id;
    } else {
        eprintln!("Failed to set active profile: mutex poisoned");
    }
}

/// Apply a profile via CLI (used by tray menu)
fn apply_profile_sync(app_handle: &tauri::AppHandle, profile_id: &str) -> Result<String, String> {
    let output = if should_use_python() {
        Command::new("python")
            .args(["-m", "abso", "apply", profile_id, "--json"])
            .current_dir(get_project_root())
            .output()
            .map_err(|e| format!("Failed to execute Python command: {}", e))?
    } else {
        let sidecar_path = get_sidecar_path(Some(app_handle));
        Command::new(&sidecar_path)
            .args(["apply", profile_id, "--json"])
            .output()
            .map_err(|e| format!("Failed to execute sidecar: {}", e))?
    };

    if output.status.success() {
        Ok(String::from_utf8_lossy(&output.stdout).to_string())
    } else {
        Err(String::from_utf8_lossy(&output.stderr).to_string())
    }
}

/// Create the tray menu
fn create_tray_menu(app: &tauri::AppHandle, active_profile: Option<&str>) -> Result<Menu<tauri::Wry>, tauri::Error> {
    let menu = Menu::new(app)?;

    // Add "Show Window" item
    let show_item = MenuItem::with_id(app, "show", "Show A.B.S.O.", true, None::<&str>)?;
    menu.append(&show_item)?;

    menu.append(&PredefinedMenuItem::separator(app)?)?;

    // Create profiles submenu
    let profiles_submenu = Submenu::with_id(app, "profiles", "Quick Apply Profile", true)?;

    for (id, name) in PROFILES {
        let is_active = active_profile.map_or(false, |p| p == *id);
        let label = if is_active {
            format!("✓ {}", name)
        } else {
            format!("  {}", name)
        };
        let item = MenuItem::with_id(app, format!("profile_{}", id), &label, true, None::<&str>)?;
        profiles_submenu.append(&item)?;
    }

    menu.append(&profiles_submenu)?;

    menu.append(&PredefinedMenuItem::separator(app)?)?;

    // Add quit item
    let quit_item = MenuItem::with_id(app, "quit", "Quit", true, None::<&str>)?;
    menu.append(&quit_item)?;

    Ok(menu)
}

/// Update the tray menu to reflect the active profile
fn update_tray_menu(app: &tauri::AppHandle, active_profile: Option<&str>) {
    if let Some(tray) = app.tray_by_id("main-tray") {
        if let Ok(menu) = create_tray_menu(app, active_profile) {
            let _ = tray.set_menu(Some(menu));
        }
    }
}

fn main() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .manage(AppState {
            active_profile: Mutex::new(None),
        })
        .setup(|app| {
            // Load tray icon
            let icon = Image::from_path("icons/icon.png")
                .or_else(|_| Image::from_path("icons/32x32.png"))
                .unwrap_or_else(|_| {
                    // Fallback: create a simple icon from bytes
                    Image::from_bytes(include_bytes!("../icons/icon.png"))
                        .expect("Failed to load embedded icon")
                });

            // Create initial tray menu
            let menu = create_tray_menu(app.handle(), None)?;

            // Build tray icon
            let _tray = TrayIconBuilder::with_id("main-tray")
                .icon(icon)
                .menu(&menu)
                .tooltip("A.B.S.O. - Adaptive Battle Station Optimizer")
                .on_menu_event(|app, event| {
                    let id = event.id.as_ref();

                    if id == "show" {
                        // Show main window
                        if let Some(window) = app.get_webview_window("main") {
                            let _ = window.show();
                            let _ = window.set_focus();
                        }
                    } else if id == "quit" {
                        app.exit(0);
                    } else if id.starts_with("profile_") {
                        // Extract profile ID
                        let profile_id = id.strip_prefix("profile_").unwrap();

                        // Apply profile using tauri's async runtime for proper lifecycle management
                        let app_clone = app.clone();
                        let profile_id_owned = profile_id.to_string();

                        tauri::async_runtime::spawn(async move {
                            // Run the blocking CLI call in a blocking thread pool
                            let result = tauri::async_runtime::spawn_blocking({
                                let app = app_clone.clone();
                                let profile_id = profile_id_owned.clone();
                                move || apply_profile_sync(&app, &profile_id)
                            }).await;

                            match result {
                                Ok(Ok(_)) => {
                                    // Update state with proper error handling
                                    let state: tauri::State<AppState> = app_clone.state();
                                    if let Ok(mut guard) = state.active_profile.lock() {
                                        *guard = Some(profile_id_owned.clone());
                                    }

                                    // Update tray menu
                                    update_tray_menu(&app_clone, Some(&profile_id_owned));

                                    // Emit event to frontend
                                    let _ = app_clone.emit("profile-applied", &profile_id_owned);
                                }
                                Ok(Err(e)) => {
                                    eprintln!("Failed to apply profile: {}", e);
                                }
                                Err(e) => {
                                    eprintln!("Profile apply task panicked: {}", e);
                                }
                            }
                        });
                    }
                })
                .on_tray_icon_event(|tray, event| {
                    match event {
                        TrayIconEvent::Click {
                            button: MouseButton::Left,
                            button_state: MouseButtonState::Up,
                            ..
                        } => {
                            // Left click: show main window
                            let app = tray.app_handle();
                            if let Some(window) = app.get_webview_window("main") {
                                let _ = window.show();
                                let _ = window.set_focus();
                            }
                        }
                        _ => {}
                    }
                })
                .build(app)?;

            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            run_abso_command,
            run_abso_json,
            is_admin,
            get_backend_info,
            get_active_profile,
            set_active_profile,
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}

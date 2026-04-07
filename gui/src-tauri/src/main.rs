// Prevents additional console window on Windows in release
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use serde::{Deserialize, Serialize};
#[cfg(windows)]
use std::ffi::{c_void, OsStr};
use std::fs;
#[cfg(windows)]
use std::os::windows::ffi::OsStrExt;
use std::path::PathBuf;
use std::process::Command;
use std::sync::Mutex;
use tauri::{
    image::Image,
    menu::{Menu, MenuItem, PredefinedMenuItem, Submenu},
    tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent},
    Emitter, Manager,
};

#[derive(Clone, Debug)]
struct TrayProfile {
    id: String,
    name: String,
}

#[derive(Deserialize)]
struct CliResponse<T> {
    success: bool,
    data: T,
    #[allow(dead_code)]
    error: Option<String>,
}

#[derive(Deserialize)]
struct CliProfile {
    id: String,
    display_name: String,
}

#[derive(Deserialize)]
struct ApplyCliData {
    success: bool,
    #[allow(dead_code)]
    profile: Option<String>,
    #[allow(dead_code)]
    backup_id: Option<String>,
    #[serde(default)]
    failed_settings: Vec<String>,
    #[allow(dead_code)]
    #[serde(default)]
    warnings: Vec<String>,
    #[serde(default)]
    notices: Vec<String>,
    error: Option<String>,
}

#[derive(Clone, Debug, Serialize)]
struct ApplyTrayEvent {
    profile_id: String,
    warnings: Vec<String>,
    notices: Vec<String>,
}

#[derive(Clone, Debug, Deserialize)]
struct StateCliData {
    current_profile: Option<String>,
    #[allow(dead_code)]
    applied_at: Option<String>,
    #[allow(dead_code)]
    reboot_pending: bool,
    #[allow(dead_code)]
    reboot_reasons: Vec<String>,
}

#[derive(Deserialize)]
struct TrayProfileCache {
    profiles: Vec<CliProfile>,
}

/// State to track the currently active profile
struct AppState {
    active_profile: Mutex<Option<String>>,
    tray_profiles: Mutex<Vec<TrayProfile>>,
}

#[cfg(windows)]
#[link(name = "shell32")]
unsafe extern "system" {
    fn ShellExecuteW(
        hwnd: *mut c_void,
        lp_operation: *const u16,
        lp_file: *const u16,
        lp_parameters: *const u16,
        lp_directory: *const u16,
        n_show_cmd: i32,
    ) -> isize;
}

#[cfg(windows)]
#[link(name = "user32")]
unsafe extern "system" {
    fn MessageBoxW(
        hwnd: *mut c_void,
        lp_text: *const u16,
        lp_caption: *const u16,
        u_type: u32,
    ) -> i32;
}

#[cfg(windows)]
fn to_wide(value: &OsStr) -> Vec<u16> {
    value.encode_wide().chain(std::iter::once(0)).collect()
}

#[cfg(windows)]
fn quote_windows_arg(arg: &OsStr) -> String {
    let arg = arg.to_string_lossy();
    if arg.is_empty() || arg.chars().any(|c| c.is_whitespace() || c == '"') {
        let mut result = String::from("\"");
        let mut backslashes = 0usize;

        for ch in arg.chars() {
            match ch {
                '\\' => backslashes += 1,
                '"' => {
                    result.push_str(&"\\".repeat(backslashes * 2 + 1));
                    result.push('"');
                    backslashes = 0;
                }
                _ => {
                    if backslashes > 0 {
                        result.push_str(&"\\".repeat(backslashes));
                        backslashes = 0;
                    }
                    result.push(ch);
                }
            }
        }

        if backslashes > 0 {
            result.push_str(&"\\".repeat(backslashes * 2));
        }
        result.push('"');
        result
    } else {
        arg.into_owned()
    }
}

#[cfg(windows)]
fn relaunch_self_elevated() -> Result<(), String> {
    let exe = std::env::current_exe().map_err(|e| format!("current_exe failed: {}", e))?;
    let exe_dir = exe
        .parent()
        .ok_or_else(|| "Could not resolve executable directory".to_string())?;

    let args = std::env::args_os()
        .skip(1)
        .map(|arg| quote_windows_arg(&arg))
        .collect::<Vec<_>>()
        .join(" ");

    let operation = to_wide(OsStr::new("runas"));
    let file = to_wide(exe.as_os_str());
    let directory = to_wide(exe_dir.as_os_str());
    let parameters = if args.is_empty() {
        None
    } else {
        Some(to_wide(OsStr::new(&args)))
    };

    let result = unsafe {
        ShellExecuteW(
            std::ptr::null_mut(),
            operation.as_ptr(),
            file.as_ptr(),
            parameters.as_ref().map_or(std::ptr::null(), |value| value.as_ptr()),
            directory.as_ptr(),
            1,
        )
    };

    if result <= 32 {
        return Err(format!("ShellExecuteW returned {}", result));
    }

    Ok(())
}

#[cfg(windows)]
fn show_elevation_error(message: &str) {
    let title = to_wide(OsStr::new("A.B.S.O."));
    let body = to_wide(OsStr::new(message));
    unsafe {
        let _ = MessageBoxW(
            std::ptr::null_mut(),
            body.as_ptr(),
            title.as_ptr(),
            0x00000010,
        );
    }
}

#[cfg(windows)]
fn ensure_gui_admin() {
    if is_admin() {
        return;
    }

    if let Err(error) = relaunch_self_elevated() {
        show_elevation_error(&format!(
            "A.B.S.O. GUI requires administrator privileges to manage system settings.\n\n{}",
            error
        ));
        std::process::exit(1);
    }

    std::process::exit(0);
}

#[cfg(not(windows))]
fn ensure_gui_admin() {}

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
        PathBuf::from("../../dist/abso.exe"), // From src-tauri
        PathBuf::from("../dist/abso.exe"),    // From gui
        PathBuf::from("dist/abso.exe"),       // From project root
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
            .map_err(|e| {
                format!(
                    "Failed to execute sidecar: {} (path: {:?})",
                    e, sidecar_path
                )
            })?
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
        let output = Command::new("net").args(["session"]).output();

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
    state
        .active_profile
        .lock()
        .ok()
        .and_then(|guard| guard.clone())
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
fn apply_profile_sync(
    app_handle: &tauri::AppHandle,
    profile_id: &str,
) -> Result<ApplyTrayEvent, String> {
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
        let stdout = String::from_utf8_lossy(&output.stdout).to_string();
        let parsed: CliResponse<ApplyCliData> = serde_json::from_str(&stdout)
            .map_err(|e| format!("Failed to parse apply response: {}. stdout: {}", e, stdout))?;

        if parsed.success && parsed.data.success && parsed.data.failed_settings.is_empty() {
            Ok(ApplyTrayEvent {
                profile_id: profile_id.to_string(),
                warnings: parsed.data.warnings,
                notices: parsed.data.notices,
            })
        } else {
            let mut parts: Vec<String> = Vec::new();
            if let Some(error) = parsed.error.or(parsed.data.error) {
                if !error.trim().is_empty() {
                    parts.push(error);
                }
            }
            if !parsed.data.failed_settings.is_empty() {
                parts.push(format!(
                    "Failed handlers: {}",
                    parsed.data.failed_settings.join("; ")
                ));
            }

            Err(if parts.is_empty() {
                "Profile apply failed without an error message from backend".to_string()
            } else {
                parts.join(" | ")
            })
        }
    } else {
        Err(String::from_utf8_lossy(&output.stderr).to_string())
    }
}

fn load_backend_active_profile(app_handle: &tauri::AppHandle) -> Option<String> {
    let output = if should_use_python() {
        Command::new("python")
            .args(["-m", "abso", "state", "--json"])
            .current_dir(get_project_root())
            .output()
    } else {
        let sidecar_path = get_sidecar_path(Some(app_handle));
        Command::new(&sidecar_path).args(["state", "--json"]).output()
    };

    let output = match output {
        Ok(o) => o,
        Err(e) => {
            eprintln!("Failed to load backend active profile: {}", e);
            return None;
        }
    };

    if !output.status.success() {
        let stderr = String::from_utf8_lossy(&output.stderr);
        eprintln!("state --json failed for tray startup: {}", stderr);
        return None;
    }

    let stdout = String::from_utf8_lossy(&output.stdout);
    match serde_json::from_str::<CliResponse<StateCliData>>(&stdout) {
        Ok(payload) if payload.success => payload.data.current_profile,
        Ok(_) => None,
        Err(e) => {
            eprintln!("Failed to parse backend active profile state: {}", e);
            None
        }
    }
}

fn fallback_tray_profiles(app_handle: &tauri::AppHandle) -> Vec<TrayProfile> {
    let mut candidate_paths = vec![get_project_root()
        .join("abso")
        .join("tray")
        .join("profile-catalog-cache.json")];

    if let Ok(resource_dir) = app_handle.path().resource_dir() {
        candidate_paths.push(resource_dir.join("profile-catalog-cache.json"));
        candidate_paths.push(
            resource_dir
                .join("abso")
                .join("tray")
                .join("profile-catalog-cache.json"),
        );
    }

    for path in candidate_paths {
        if !path.exists() {
            continue;
        }

        let Ok(raw) = fs::read_to_string(&path) else {
            continue;
        };

        let Ok(cache) = serde_json::from_str::<TrayProfileCache>(&raw) else {
            continue;
        };

        if !cache.profiles.is_empty() {
            return cache
                .profiles
                .into_iter()
                .map(|profile| TrayProfile {
                    id: profile.id,
                    name: profile.display_name,
                })
                .collect();
        }
    }

    Vec::new()
}

/// Load tray profile menu entries from CLI metadata.
fn load_tray_profiles(app_handle: &tauri::AppHandle) -> Vec<TrayProfile> {
    let output = if should_use_python() {
        Command::new("python")
            .args(["-m", "abso", "profiles", "--json"])
            .current_dir(get_project_root())
            .output()
    } else {
        let sidecar_path = get_sidecar_path(Some(app_handle));
        Command::new(&sidecar_path)
            .args(["profiles", "--json"])
            .output()
    };

    let output = match output {
        Ok(o) => o,
        Err(e) => {
            eprintln!("Failed to load profiles for tray menu: {}", e);
            return fallback_tray_profiles(app_handle);
        }
    };

    if !output.status.success() {
        let stderr = String::from_utf8_lossy(&output.stderr);
        eprintln!("profiles --json failed for tray menu: {}", stderr);
        return fallback_tray_profiles(app_handle);
    }

    let stdout = String::from_utf8_lossy(&output.stdout);
    let parsed: Result<CliResponse<Vec<CliProfile>>, _> = serde_json::from_str(&stdout);
    match parsed {
        Ok(payload) if payload.success && !payload.data.is_empty() => payload
            .data
            .into_iter()
            .map(|profile| TrayProfile {
                id: profile.id,
                name: profile.display_name,
            })
            .collect(),
        Ok(_) => fallback_tray_profiles(app_handle),
        Err(e) => {
            eprintln!("Failed to parse profile metadata for tray menu: {}", e);
            fallback_tray_profiles(app_handle)
        }
    }
}

/// Create the tray menu
fn create_tray_menu(
    app: &tauri::AppHandle,
    profiles: &[TrayProfile],
    active_profile: Option<&str>,
) -> Result<Menu<tauri::Wry>, tauri::Error> {
    let menu = Menu::new(app)?;

    // Add "Show Window" item
    let show_item = MenuItem::with_id(app, "show", "Show A.B.S.O.", true, None::<&str>)?;
    menu.append(&show_item)?;

    menu.append(&PredefinedMenuItem::separator(app)?)?;

    // Create profiles submenu
    let profiles_submenu = Submenu::with_id(app, "profiles", "Quick Apply Profile", true)?;

    if profiles.is_empty() {
        let unavailable = MenuItem::with_id(
            app,
            "profiles_unavailable",
            "No profiles available",
            false,
            None::<&str>,
        )?;
        profiles_submenu.append(&unavailable)?;
    } else {
        for profile in profiles {
            let is_active = active_profile.map_or(false, |p| p == profile.id);
            let label = if is_active {
                format!("* {}", profile.name)
            } else {
                format!("  {}", profile.name)
            };
            let item = MenuItem::with_id(
                app,
                format!("profile_{}", profile.id),
                &label,
                true,
                None::<&str>,
            )?;
            profiles_submenu.append(&item)?;
        }
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
    let mut profiles = app
        .state::<AppState>()
        .tray_profiles
        .lock()
        .ok()
        .map(|guard| guard.clone())
        .unwrap_or_default();

    if profiles.is_empty() {
        profiles = load_tray_profiles(app);
        if let Ok(mut guard) = app.state::<AppState>().tray_profiles.lock() {
            *guard = profiles.clone();
        }
    }

    if let Some(tray) = app.tray_by_id("main-tray") {
        if let Ok(menu) = create_tray_menu(app, &profiles, active_profile) {
            let _ = tray.set_menu(Some(menu));
        }
    }
}

fn main() {
    ensure_gui_admin();

    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .manage(AppState {
            active_profile: Mutex::new(None),
            tray_profiles: Mutex::new(Vec::new()),
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

            let tray_profiles = load_tray_profiles(app.handle());
            if let Ok(mut guard) = app.state::<AppState>().tray_profiles.lock() {
                *guard = tray_profiles.clone();
            }

            let initial_active_profile = load_backend_active_profile(app.handle());
            if let Ok(mut guard) = app.state::<AppState>().active_profile.lock() {
                *guard = initial_active_profile.clone();
            }

            // Create initial tray menu
            let menu =
                create_tray_menu(app.handle(), &tray_profiles, initial_active_profile.as_deref())?;

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
                            })
                            .await;

                            match result {
                                Ok(Ok(apply_event)) => {
                                    // Update state with proper error handling
                                    let state: tauri::State<AppState> = app_clone.state();
                                    if let Ok(mut guard) = state.active_profile.lock() {
                                        *guard = Some(apply_event.profile_id.clone());
                                    }

                                    // Update tray menu
                                    update_tray_menu(&app_clone, Some(&apply_event.profile_id));

                                    // Emit event to frontend
                                    let _ = app_clone.emit("profile-applied", &apply_event);
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

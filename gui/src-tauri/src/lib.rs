use chrono::Local;
use serde::{Deserialize, Serialize};
use std::path::PathBuf;
use std::sync::Mutex;

// ---------------------------------------------------------------------------
// Path helpers
// ---------------------------------------------------------------------------

fn project_root() -> PathBuf {
    // Prefer the EXE's parent directory (so the release/ folder works standalone).
    // Fall back to CARGO_MANIFEST_DIR/../.. for dev mode (cargo run / tauri dev).
    if let Ok(exe) = std::env::current_exe() {
        if let Some(parent) = exe.parent() {
            let proxy = parent.join("proxy_server.py");
            if proxy.exists() {
                return parent.to_path_buf();
            }
        }
    }
    let manifest = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
    manifest.join("..").join("..")
}

fn log_dir() -> PathBuf {
    project_root().join("Communication-Logs")
}

fn config_path() -> PathBuf {
    project_root().join("config.json")
}


// ---------------------------------------------------------------------------
// Command 1: Health check
// ---------------------------------------------------------------------------

#[derive(Serialize)]
pub struct HealthResponse {
    status: String,
    upstream: String,
}

#[tauri::command]
async fn check_health() -> Result<HealthResponse, String> {
    let client = reqwest::Client::builder()
        .timeout(std::time::Duration::from_secs(5))
        .build()
        .map_err(|e| e.to_string())?;

    match client
        .get("http://127.0.0.1:4000/health")
        .send()
        .await
    {
        Ok(resp) => {
            let json: serde_json::Value =
                resp.json().await.map_err(|e| e.to_string())?;
            Ok(HealthResponse {
                status: json["status"]
                    .as_str()
                    .unwrap_or("unknown")
                    .into(),
                upstream: json["upstream"]
                    .as_str()
                    .unwrap_or("")
                    .into(),
            })
        }
        Err(_) => Ok(HealthResponse {
            status: "unreachable".into(),
            upstream: "".into(),
        }),
    }
}

// ---------------------------------------------------------------------------
// Command 2: Check API key
// ---------------------------------------------------------------------------

#[tauri::command]
fn check_api_key() -> Result<bool, String> {
    Ok(std::env::var("DEEPSEEK_API_KEY").is_ok())
}

// ---------------------------------------------------------------------------
// Command 3: Set API key as environment variable
// ---------------------------------------------------------------------------

#[tauri::command]
fn set_env_api_key(key: String) -> Result<(), String> {
    let trimmed = key.trim().to_string();

    // Persist to user environment variable (survives app restart)
    // setx doesn't affect the current process, so we also call set_var below
    let output = std::process::Command::new("setx")
        .args(["DEEPSEEK_API_KEY", &trimmed])
        .output()
        .map_err(|e| format!("Failed to run setx: {}", e))?;

    if !output.status.success() {
        let stderr = String::from_utf8_lossy(&output.stderr);
        return Err(format!("setx failed: {}", stderr));
    }

    // Also set for current process (setx only affects new processes)
    std::env::set_var("DEEPSEEK_API_KEY", &trimmed);

    Ok(())
}

// ---------------------------------------------------------------------------
// Command 3b: Port 4000 process
// ---------------------------------------------------------------------------

#[derive(Serialize)]
pub struct PortProcessInfo {
    pid: String,
    raw_output: String,
}

#[tauri::command]
fn get_port_4000_process() -> Result<PortProcessInfo, String> {
    let output = std::process::Command::new("cmd")
        .args(["/C", "netstat -ano | findstr :4000"])
        .output()
        .map_err(|e| e.to_string())?;

    let stdout = String::from_utf8_lossy(&output.stdout).to_string();

    // Extract PID from LISTENING line (5th whitespace-delimited token)
    let pid = stdout
        .lines()
        .find(|line| line.to_uppercase().contains("LISTENING"))
        .and_then(|line| {
            line.split_whitespace().nth(4).map(|s| s.to_string())
        })
        .unwrap_or_default();

    Ok(PortProcessInfo {
        pid,
        raw_output: stdout,
    })
}

// ---------------------------------------------------------------------------
// Command 4: Read config
// ---------------------------------------------------------------------------

#[derive(Serialize, Deserialize)]
pub struct GatewayConfigResponse {
    model_map: std::collections::HashMap<String, String>,
    visible_models: Vec<String>,
    default_model: String,
    force_anthropic_version: Option<String>,
    enable_cors: bool,
    upstream_url: String,
}

#[tauri::command]
fn read_config() -> Result<GatewayConfigResponse, String> {
    let path = config_path();
    let content = std::fs::read_to_string(&path)
        .map_err(|e| format!("Cannot read config.json: {}", e))?;
    let cfg: GatewayConfigResponse =
        serde_json::from_str(&content).map_err(|e| format!("Invalid JSON: {}", e))?;
    Ok(cfg)
}

// ---------------------------------------------------------------------------
// Command 5: Read latest log
// ---------------------------------------------------------------------------

#[derive(Serialize)]
pub struct LogFile {
    filename: String,
    content: String,
    line_count: usize,
}

#[tauri::command]
fn read_latest_log() -> Result<LogFile, String> {
    let dir = log_dir();

    if !dir.exists() {
        return Ok(LogFile {
            filename: String::new(),
            content: String::new(),
            line_count: 0,
        });
    }

    let mut entries: Vec<_> = std::fs::read_dir(&dir)
        .map_err(|e| format!("Cannot read log dir: {}", e))?
        .filter_map(|e| e.ok())
        .filter(|e| {
            let name = e.file_name();
            let name = name.to_string_lossy();
            name.starts_with("proxy-") && name.ends_with(".log")
        })
        .collect();

    // Sort by filename descending (ISO dates = chronological order)
    entries.sort_by(|a, b| b.file_name().cmp(&a.file_name()));

    let latest = match entries.first() {
        Some(entry) => entry,
        None => {
            return Ok(LogFile {
                filename: String::new(),
                content: String::new(),
                line_count: 0,
            });
        }
    };

    let filename = latest.file_name().to_string_lossy().to_string();
    let bytes =
        std::fs::read(latest.path()).map_err(|e| format!("Cannot read log file: {}", e))?;

    // Try UTF-8 first, then fall back to Shift-JIS (for Japanese Windows)
    let content = match String::from_utf8(bytes.clone()) {
        Ok(s) => s,
        Err(_) => {
            let (decoded, _, had_errors) = encoding_rs::SHIFT_JIS.decode(&bytes);
            if had_errors {
                String::from_utf8_lossy(&bytes).to_string()
            } else {
                decoded.into_owned()
            }
        }
    };
    let line_count = content.lines().count();

    Ok(LogFile {
        filename,
        content,
        line_count,
    })
}

// ---------------------------------------------------------------------------
// Command 6: Open logs folder in Explorer
// ---------------------------------------------------------------------------

#[tauri::command]
fn open_logs_folder() -> Result<(), String> {
    let dir = log_dir();
    if !dir.exists() {
        std::fs::create_dir_all(&dir).map_err(|e| format!("Cannot create log dir: {}", e))?;
    }
    std::process::Command::new("explorer")
        .arg(&dir)
        .spawn()
        .map_err(|e| format!("Cannot open folder: {}", e))?;
    Ok(())
}

// ---------------------------------------------------------------------------
// Command 7: Open any path in Explorer
// ---------------------------------------------------------------------------

fn expand_env_vars(path: &str) -> String {
    let mut result = path.to_string();
    let mut start = 0;
    while let Some(pct) = result[start..].find('%') {
        let abs = start + pct;
        if let Some(end) = result[abs + 1..].find('%') {
            let var_name = &result[abs + 1..abs + 1 + end];
            if let Ok(val) = std::env::var(var_name) {
                result.replace_range(abs..abs + end + 2, &val);
                start = abs + val.len();
            } else {
                start = abs + end + 2;
            }
        } else {
            break;
        }
    }
    result
}

#[tauri::command]
fn open_path(path: String) -> Result<(), String> {
    let resolved = expand_env_vars(&path);
    std::process::Command::new("explorer")
        .arg(&resolved)
        .spawn()
        .map_err(|e| format!("Cannot open path: {}", e))?;
    Ok(())
}

// ---------------------------------------------------------------------------
// Command 8: Read config raw (with encoding detection)
// ---------------------------------------------------------------------------

#[derive(Serialize)]
pub struct RawConfigResponse {
    content: String,
    encoding_used: String,
}

#[tauri::command]
fn read_config_raw() -> Result<RawConfigResponse, String> {
    let path = config_path();
    let bytes =
        std::fs::read(&path).map_err(|e| format!("Cannot read config.json: {}", e))?;

    match String::from_utf8(bytes.clone()) {
        Ok(s) => Ok(RawConfigResponse {
            content: s,
            encoding_used: "UTF-8".into(),
        }),
        Err(_) => {
            let (decoded, _, had_errors) = encoding_rs::SHIFT_JIS.decode(&bytes);
            if had_errors {
                Err("Cannot decode config.json as UTF-8 or Shift-JIS".into())
            } else {
                Ok(RawConfigResponse {
                    content: decoded.into_owned(),
                    encoding_used: "Shift-JIS".into(),
                })
            }
        }
    }
}

// ---------------------------------------------------------------------------
// Command 9: Write config
// ---------------------------------------------------------------------------

#[tauri::command]
fn write_config(content: String, encoding: String) -> Result<(), String> {
    let path = config_path();
    let bytes: Vec<u8> = match encoding.as_str() {
        "Shift-JIS" => {
            let (encoded, _, had_errors) = encoding_rs::SHIFT_JIS.encode(&content);
            if had_errors {
                return Err("Cannot encode content as Shift-JIS".into());
            }
            encoded.into_owned()
        }
        _ => content.into_bytes(),
    };
    std::fs::write(&path, &bytes).map_err(|e| format!("Cannot write config.json: {}", e))?;
    Ok(())
}

// ---------------------------------------------------------------------------
// Command 13: Find Claude Desktop config files
// ---------------------------------------------------------------------------

#[derive(Serialize)]
pub struct ClaudeConfigCandidate {
    path: String,
    exists: bool,
    likely_config: bool,
}

#[tauri::command]
fn find_claude_configs() -> Result<Vec<ClaudeConfigCandidate>, String> {
    let mut candidates: Vec<ClaudeConfigCandidate> = Vec::new();

    // Build search directories from environment variables
    let mut dirs: Vec<PathBuf> = Vec::new();
    let mut seen: std::collections::HashSet<PathBuf> = std::collections::HashSet::new();

    let vars: &[(&str, &str)] = &[
        ("APPDATA", "Claude"),
        ("LOCALAPPDATA", "Claude"),
        ("LOCALAPPDATA", "Claude-3p\\configLibrary"),
        ("USERPROFILE", ".claude"),
    ];

    for (env_var, subdir) in vars {
        if let Ok(base) = std::env::var(env_var) {
            let dir = PathBuf::from(&base).join(subdir);
            if seen.insert(dir.clone()) {
                dirs.push(dir);
            }
        }
    }

    // Claude-specific keys that indicate a real config file
    let claude_keys = [
        "inferenceProvider",
        "claude_desktop_config",
        "inferenceGatewayBaseUrl",
        "inferenceModels",
        "inferenceGatewayApiKey",
    ];

    for dir in &dirs {
        if !dir.exists() {
            continue;
        }
        let entries = match std::fs::read_dir(dir) {
            Ok(e) => e,
            Err(_) => continue,
        };
        for entry in entries.flatten() {
            let path = entry.path();
            let name = path
                .file_name()
                .map(|n| n.to_string_lossy().to_string())
                .unwrap_or_default();
            if name.ends_with(".json") {
                // Check if file content suggests it's a Claude config
                let likely_config = std::fs::read(&path)
                    .ok()
                    .and_then(|bytes| String::from_utf8(bytes).ok())
                    .map(|content| {
                        claude_keys
                            .iter()
                            .any(|key| content.contains(key))
                    })
                    .unwrap_or(false);

                candidates.push(ClaudeConfigCandidate {
                    path: path.to_string_lossy().to_string(),
                    exists: true,
                    likely_config,
                });
            }
        }
    }

    // Sort: likely configs first, then by path
    candidates.sort_by(|a, b| {
        b.likely_config
            .cmp(&a.likely_config)
            .then(a.path.cmp(&b.path))
    });
    candidates.dedup_by(|a, b| a.path == b.path);
    Ok(candidates)
}

// ---------------------------------------------------------------------------
// Command 14: List log files
// ---------------------------------------------------------------------------

#[derive(Serialize)]
pub struct LogListEntry {
    filename: String,
    size: u64,
}

#[tauri::command]
fn list_logs() -> Result<Vec<LogListEntry>, String> {
    let dir = log_dir();
    if !dir.exists() {
        return Ok(Vec::new());
    }

    let mut entries: Vec<LogListEntry> = std::fs::read_dir(&dir)
        .map_err(|e| format!("Cannot read log dir: {}", e))?
        .filter_map(|e| e.ok())
        .filter(|e| {
            let name = e.file_name();
            let name = name.to_string_lossy();
            name.starts_with("proxy-") && name.ends_with(".log")
        })
        .map(|e| {
            let filename = e.file_name().to_string_lossy().to_string();
            let size = e.metadata().map(|m| m.len()).unwrap_or(0);
            LogListEntry { filename, size }
        })
        .collect();

    entries.sort_by(|a, b| b.filename.cmp(&a.filename));
    Ok(entries)
}

// ---------------------------------------------------------------------------
// Command 15: Read a specific log file
// ---------------------------------------------------------------------------

#[tauri::command]
fn read_log(filename: String) -> Result<LogFile, String> {
    let dir = log_dir();
    let path = dir.join(&filename);

    // Security: ensure the resolved path stays inside log_dir
    let canonical_dir = dir
        .canonicalize()
        .map_err(|e| format!("Cannot resolve log dir: {}", e))?;
    let canonical_path = path
        .canonicalize()
        .map_err(|_| format!("Log file not found: {}", filename))?;
    if !canonical_path.starts_with(&canonical_dir) {
        return Err("Invalid log filename".into());
    }

    let bytes =
        std::fs::read(&canonical_path).map_err(|e| format!("Cannot read log file: {}", e))?;

    let content = match String::from_utf8(bytes.clone()) {
        Ok(s) => s,
        Err(_) => {
            let (decoded, _, had_errors) = encoding_rs::SHIFT_JIS.decode(&bytes);
            if had_errors {
                String::from_utf8_lossy(&bytes).to_string()
            } else {
                decoded.into_owned()
            }
        }
    };
    let line_count = content.lines().count();

    Ok(LogFile {
        filename,
        content,
        line_count,
    })
}

// ---------------------------------------------------------------------------
// Command 16: Create new log file
// ---------------------------------------------------------------------------

#[tauri::command]
fn create_new_log() -> Result<String, String> {
    let dir = log_dir();
    if !dir.exists() {
        std::fs::create_dir_all(&dir)
            .map_err(|e| format!("Cannot create log dir: {}", e))?;
    }

    let now = Local::now();
    let filename = format!("proxy-{}.log", now.format("%Y%m%d-%H%M%S"));
    let path = dir.join(&filename);

    std::fs::write(&path, "").map_err(|e| format!("Cannot create log file: {}", e))?;
    Ok(filename)
}


// ---------------------------------------------------------------------------
// Proxy state
// ---------------------------------------------------------------------------

pub struct ProxyState {
    child: Mutex<Option<std::process::Child>>,
}

impl ProxyState {
    pub fn new() -> Self {
        Self {
            child: Mutex::new(None),
        }
    }
}

// ---------------------------------------------------------------------------
// Command 10: Start proxy
// ---------------------------------------------------------------------------

#[derive(Serialize)]
pub struct StartProxyResult {
    success: bool,
    pid: u32,
    python: String,
    dir: String,
    log: String,
}

#[tauri::command]
fn start_proxy(state: tauri::State<'_, ProxyState>) -> Result<StartProxyResult, String> {
    let mut diag: Vec<String> = Vec::new();

    let mut guard = state.child.lock().map_err(|e| e.to_string())?;

    if let Some(ref mut child) = *guard {
        match child.try_wait() {
            Ok(Some(_)) => *guard = None,
            Ok(None) => return Ok(StartProxyResult {
                success: false, pid: 0,
                python: String::new(), dir: String::new(),
                log: "already_running".into(),
            }),
            Err(e) => return Err(format!("Cannot check child status: {}", e)),
        }
    }

    let deepseek_key = match std::env::var("DEEPSEEK_API_KEY") {
        Ok(k) => {
            diag.push(format!("DEEPSEEK_API_KEY: set (len={})", k.len()));
            k
        }
        Err(_) => {
            diag.push("DEEPSEEK_API_KEY: NOT SET".into());
            return Err("DEEPSEEK_API_KEY not set — set it in the API Key tab first.".into());
        }
    };

    let root = project_root();
    diag.push(format!("project_root: {}", root.display()));

    let proxy_py = root.join("proxy_server.py");
    diag.push(format!("proxy_server.py exists: {}", proxy_py.exists()));

    let config_json = root.join("config.json");
    diag.push(format!("config.json exists: {}", config_json.exists()));

    // Resolve python.exe via cmd so PATH matches the user's normal shell
    let python = std::process::Command::new("cmd")
        .args(["/C", "where python 2>nul"])
        .stdout(std::process::Stdio::piped())
        .stderr(std::process::Stdio::null())
        .output()
        .ok()
        .and_then(|out| String::from_utf8(out.stdout).ok())
        .map(|s| s.lines().next().unwrap_or("").trim().to_string())
        .filter(|s| !s.is_empty());
    diag.push(format!("where python result: {:?}", python));

    let python = python
        .ok_or_else(|| format!("Python not found. Diagnostics:\n{}", diag.join("\n")))?;

    diag.push(format!("Using python: {}", python));
    diag.push(format!("Launching: {} proxy_server.py in {}", python, root.display()));

    let mut child = std::process::Command::new(&python)
        .arg("proxy_server.py")
        .current_dir(&root)
        .env("DEEPSEEK_API_KEY", &deepseek_key)
        .stdout(std::process::Stdio::piped())
        .stderr(std::process::Stdio::piped())
        .spawn()
        .map_err(|e| format!("Cannot start proxy: {}\nDiagnostics:\n{}", e, diag.join("\n")))?;

    let pid = child.id();
    diag.push(format!("Spawned PID: {}", pid));

    // Wait 2s for uvicorn to bind the port, then check if still alive
    std::thread::sleep(std::time::Duration::from_millis(2000));
    match child.try_wait() {
        Ok(Some(status)) => {
            let stderr = child.stderr.take()
                .and_then(|mut r| { use std::io::Read; let mut b = String::new(); r.read_to_string(&mut b).ok().map(|_| b) })
                .unwrap_or_default();
            let stdout = child.stdout.take()
                .and_then(|mut r| { use std::io::Read; let mut b = String::new(); r.read_to_string(&mut b).ok().map(|_| b) })
                .unwrap_or_default();
            diag.push(format!("Exit code: {:?}", status.code()));
            if !stderr.is_empty() { diag.push(format!("stderr:\n{}", stderr.trim())); }
            if !stdout.is_empty() { diag.push(format!("stdout:\n{}", stdout.trim())); }
            return Err(format!("Proxy exited after 2s. Diagnostics:\n{}", diag.join("\n")));
        }
        Ok(None) => {
            diag.push("Process still running after 2s — port should be bound".into());
        }
        Err(e) => {
            return Err(format!("Cannot check proxy status: {}", e));
        }
    }

    *guard = Some(child);
    Ok(StartProxyResult {
        success: true,
        pid,
        python,
        dir: root.display().to_string(),
        log: diag.join("\n"),
    })
}

// ---------------------------------------------------------------------------
// Command 11: Stop proxy
// ---------------------------------------------------------------------------

#[tauri::command]
fn stop_proxy(state: tauri::State<'_, ProxyState>) -> Result<String, String> {
    let mut guard = state.child.lock().map_err(|e| e.to_string())?;

    match guard.take() {
        Some(mut child) => {
            child.kill().map_err(|e| format!("Cannot kill proxy: {}", e))?;
            child.wait().map_err(|e| format!("Cannot wait on proxy: {}", e))?;
            Ok("stopped".into())
        }
        None => Ok("not_running".into()),
    }
}

// ---------------------------------------------------------------------------
// Command 12: Proxy status
// ---------------------------------------------------------------------------

#[tauri::command]
fn proxy_status(state: tauri::State<'_, ProxyState>) -> Result<bool, String> {
    let mut guard = state.child.lock().map_err(|e| e.to_string())?;

    if let Some(ref mut child) = *guard {
        match child.try_wait() {
            Ok(Some(_)) => {
                *guard = None;
                Ok(false)
            }
            Ok(None) => Ok(true),
            Err(e) => Err(format!("Cannot check child status: {}", e)),
        }
    } else {
        Ok(false)
    }
}

// ---------------------------------------------------------------------------
// App entry point
// ---------------------------------------------------------------------------

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .manage(ProxyState::new())
        .invoke_handler(tauri::generate_handler![
            check_health,
            check_api_key,
            get_port_4000_process,
            read_config,
            read_latest_log,
            open_logs_folder,
            open_path,
            read_config_raw,
            write_config,
            find_claude_configs,
            list_logs,
            read_log,
            create_new_log,
            set_env_api_key,
            start_proxy,
            stop_proxy,
            proxy_status,
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}

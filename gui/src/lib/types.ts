// Hardware detection types
export interface GpuInfo {
  name: string;
  driver_version: string;
  vram_mb: number;
  is_nvidia: boolean;
  reflex_available: boolean;
}

export interface CpuInfo {
  name: string;
  cores: number;
  threads: number;
}

export interface MonitorInfo {
  name: string;
  resolution: string;
  refresh_rate: number;
  max_refresh_rate: number;
  vrr_supported: boolean | 'likely';
  vrr_type: 'G-Sync' | 'FreeSync' | 'HDMI VRR' | null;
  vrr_range: string | null;
  is_primary: boolean;
}

export interface HardwareInfo {
  gpu: GpuInfo;
  cpu: CpuInfo;
  ram_gb: number;
  monitors: MonitorInfo[];
}

// Audit types
export type Severity = 'critical' | 'warning' | 'info';

export interface Issue {
  title: string;
  severity: Severity;
  current_value: string;
  optimal_value: string;
  explanation: string;
  category: string;
}

// Profile types
export interface Profile {
  id: string;
  display_name: string;
  description: string;
  optimization_target: string;
  application_scope?: 'system_only' | 'system_plus_native_config';
  executables: string[];
  handlers?: string[];
  has_in_game_settings?: boolean;
  detected?: boolean;
  tray_category?: string;
  tray_subtitle?: string;
  tray_description?: string;
  tray_group?: string;
  tray_group_name?: string;
  tray_variant?: string;
  tray_rank?: number;
  tray_visible?: boolean;
  sync_mode?: 'on' | 'off' | 'agnostic';
}

export interface ProfileSettings {
  windows?: Record<string, unknown>;
  nvidia?: Record<string, unknown>;
  power?: Record<string, unknown>;
  registry?: Record<string, unknown>;
  mouse?: Record<string, unknown>;
  network?: Record<string, unknown>;
}

export interface InGameSetting {
  category: string;
  setting: string;
  value: string;
  reason?: string;
}

// Backup types
export interface Backup {
  id: string;
  created_at: string;
  components: string[];  // Array of handler names
}

// Settings types
export interface WindowsSettings {
  game_mode: boolean;
  game_bar: boolean;
  game_dvr: boolean;
  hags: boolean;
  vbs: boolean;
  hdr: boolean;
  auto_hdr: boolean;
}

export interface NvidiaSettings {
  low_latency_mode: 'off' | 'on' | 'ultra';
  power_management: 'optimal' | 'max_performance';
  vsync: boolean;
  shader_cache: 'limited' | 'unlimited';
  threaded_optimization: boolean;
}

export interface PowerSettings {
  active_plan: 'balanced' | 'high_performance' | 'ultimate_performance';
  usb_suspend: boolean;
  pcie_power_saving: boolean;
  cpu_max_performance: boolean;
}

export interface AllSettings {
  windows: WindowsSettings;
  nvidia: NvidiaSettings;
  power: PowerSettings;
}

// Apply result types
export interface ApplyStep {
  handler: string;
  status: 'pending' | 'in_progress' | 'completed' | 'failed';
  message?: string;
}

export interface ApplyHandlerResult {
  handler: string;
  status: 'success' | 'failed' | 'skipped';
  error?: string;
}

export interface TransactionCheckpoint {
  phase: string;
  status: string;
  message: string;
  at?: string;
}

export interface TransactionSummary {
  success: boolean;
  profile_id: string;
  state: string;
  backup_id?: string | null;
  error?: string | null;
  rollback_performed: boolean;
  rollback_error?: string | null;
  checkpoints: TransactionCheckpoint[];
}

export interface ComplianceIssue {
  code: string;
  severity: Severity;
  message: string;
  details?: string | null;
  source?: string | null;
}

export interface ComplianceSummary {
  profile_id?: string;
  passed: boolean;
  has_critical: boolean;
  issues: ComplianceIssue[];
}

export interface BackendStateVerification {
  checked_at: string;
  profile: string;
  all_active: boolean;
  status: 'active' | 'pending_apply' | 'pending_reboot' | 'mismatch' | 'error';
  pending_apply_settings: string[];
  pending_reboot_gated_settings: string[];
  mismatched_handlers: string[];
  error?: string;
}

export interface BackendState {
  current_profile: string | null;
  applied_at: string | null;
  reboot_pending: boolean;
  reboot_reasons: string[];
  verification?: BackendStateVerification;
}

export interface ApplyResult {
  success: boolean;
  profile: string;
  backup_id?: string | null;
  requires_reboot: boolean;
  reboot_reasons: string[];
  in_game_settings: boolean;
  error?: string | null;
  applied_settings: string[];
  /**
   * Per-handler granular applied lines, keyed by handler class name. Surfaces
   * messages like "Monitor Adaptive Sync: disabled" so UIs can suppress stale
   * follow-up prompts (e.g. "go to your monitor OSD and turn it off") when
   * ABSO already handled the action via DDC/CI or similar.
   */
  handler_applied_details?: Record<string, string[]>;
  /**
   * Structured signal for monitor firmware Adaptive Sync state after apply.
   * "enabled" / "disabled" when ABSO toggled it via DDC/CI, null otherwise.
   */
  monitor_adaptive_sync_state?: 'enabled' | 'disabled' | null;
  failed_settings: string[];
  warnings: string[];
  notices: string[];
  summary_level?: 'success' | 'notice' | 'caution' | 'warning';
  results: ApplyHandlerResult[];
  transaction?: TransactionSummary;
  compliance?: ComplianceSummary | null;
}

// Navigation types
export type Page =
  | 'home'
  | 'profile-wizard'
  | 'settings'
  | 'audit'
  | 'backups'
  | 'reports'
  | 'timer';

// Theme types
export type Theme = 'light' | 'dark' | 'system';

import { invoke } from '@tauri-apps/api/core';
import type {
  HardwareInfo,
  Issue,
  Profile,
  Backup,
  ApplyResult,
  BackendState,
} from './types';

/**
 * Run a raw ABSO CLI command
 */
export async function runAbsoCommand(
  command: string,
  args: string[] = []
): Promise<string> {
  return invoke<string>('run_abso_command', { command, args });
}

/**
 * CLI response wrapper format
 */
interface CliResponse<T> {
  success: boolean;
  data: T;
  error?: string;
}

/**
 * Run an ABSO CLI command with JSON output
 */
export async function runAbsoJson<T>(
  command: string,
  args: string[] = []
): Promise<T> {
  const result = await invoke<string>('run_abso_json', { command, args });
  const response = JSON.parse(result) as CliResponse<T>;

  if (!response.success) {
    const dataError =
      response.data &&
      typeof response.data === 'object' &&
      'error' in response.data &&
      typeof (response.data as { error?: unknown }).error === 'string'
        ? (response.data as { error: string }).error
        : response.data &&
            typeof response.data === 'object' &&
            'message' in response.data &&
            typeof (response.data as { message?: unknown }).message === 'string'
          ? (response.data as { message: string }).message
          : undefined;

    throw new Error(response.error || dataError || 'Command failed');
  }

  return response.data;
}

/**
 * Check if running as administrator
 */
export async function isAdmin(): Promise<boolean> {
  return invoke<boolean>('is_admin');
}

/**
 * Detect system hardware
 */
export async function detectHardware(): Promise<HardwareInfo> {
  return runAbsoJson<HardwareInfo>('detect');
}

/**
 * Run system audit
 */
export async function runAudit(verbose = true): Promise<Issue[]> {
  const args = verbose ? ['--verbose'] : [];
  return runAbsoJson<Issue[]>('audit', args);
}

/**
 * Get available profiles
 */
export async function getProfiles(): Promise<Profile[]> {
  return runAbsoJson<Profile[]>('profiles');
}

/**
 * Detect installed games
 */
export async function detectGames(): Promise<string[]> {
  return runAbsoJson<string[]>('games');
}

/**
 * Apply a profile
 */
export async function applyProfile(
  profileId: string,
  createBackup = true
): Promise<ApplyResult> {
  const args = createBackup ? [] : ['--no-backup'];
  return runAbsoJson<ApplyResult>('apply', [profileId, ...args]);
}

/**
 * Get list of backups
 */
export async function getBackups(): Promise<Backup[]> {
  return runAbsoJson<Backup[]>('backups');
}

/**
 * Restore from a backup
 */
export async function restoreBackup(
  backupId: string
): Promise<{ success: boolean; message: string }> {
  return runAbsoJson<{ success: boolean; message: string }>('restore', [
    backupId,
  ]);
}

/**
 * Create a manual backup
 */
export async function createBackup(): Promise<Backup> {
  return runAbsoJson<Backup>('backup-create');
}

/**
 * Delete a backup
 */
export async function deleteBackup(
  backupId: string
): Promise<{ success: boolean }> {
  return runAbsoJson<{ success: boolean }>('backup-delete', [backupId]);
}

/**
 * Get timer resolution
 */
export async function getTimerResolution(): Promise<{
  current: number;
  minimum: number;
  maximum: number;
}> {
  return runAbsoJson<{ current: number; minimum: number; maximum: number }>(
    'timer',
    ['--status']
  );
}

/**
 * Generate in-game settings report
 */
export async function getReport(
  profileId: string
): Promise<{ content: string; path: string }> {
  return runAbsoJson<{ content: string; path: string }>('report', [profileId]);
}

/**
 * Get persisted backend active-profile state.
 */
export async function getCurrentState(): Promise<BackendState> {
  return runAbsoJson<BackendState>('state');
}

/**
 * Get the current Tauri-side active profile cache.
 */
export async function getActiveProfile(): Promise<string | null> {
  return invoke<string | null>('get_active_profile');
}

/**
 * Set the current Tauri-side active profile cache (for tray menu sync)
 */
export async function setActiveProfileBackend(profileId: string | null): Promise<void> {
  return invoke<void>('set_active_profile', { profileId });
}

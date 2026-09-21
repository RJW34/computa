import type { BackendStateVerification, ManualSetupStep } from './types';

export type ProfileUiStateKind =
  | 'loading'
  | 'unknown'
  | 'none'
  | 'active'
  | 'needs_apply'
  | 'needs_manual'
  | 'needs_restart'
  | 'mismatch'
  | 'error';

export interface ProfileUiState {
  kind: ProfileUiStateKind;
  needsAttention: boolean;
  label: string;
  detail?: string;
}

interface ProfileReadbackSnapshot {
  activeProfile: string | null;
  activeProfileAppliedAt: string | null;
  activeProfileVerification: BackendStateVerification | null;
  activeProfileStateKnown: boolean;
  activeProfileStateError: string | null;
}

export function canAcceptProfileReadback(
  starting: ProfileReadbackSnapshot,
  current: ProfileReadbackSnapshot
): boolean {
  // Same-profile verification can change without a new apply timestamp.
  return starting.activeProfile === current.activeProfile &&
    starting.activeProfileAppliedAt === current.activeProfileAppliedAt &&
    starting.activeProfileVerification === current.activeProfileVerification &&
    starting.activeProfileStateKnown === current.activeProfileStateKnown &&
    starting.activeProfileStateError === current.activeProfileStateError;
}

export function formatStatusDetail(value: string): string {
  return value
    .replace(/SettingsHandler$/, ' settings')
    .replace(/Handler$/, '')
    .replace(/_/g, ' ')
    .replace(/\./g, ': ')
    .replace(/([a-z0-9])([A-Z])/g, '$1 $2');
}

export function uniqueStrings(values: Array<string | null | undefined>): string[] {
  const seen = new Set<string>();
  const result: string[] = [];

  values.forEach((value) => {
    const normalized = value?.trim();
    if (!normalized || seen.has(normalized)) {
      return;
    }

    seen.add(normalized);
    result.push(normalized);
  });

  return result;
}

export function verificationIsClean(
  verification?: BackendStateVerification | null
): boolean {
  // Managed-setting verification stays separate from manual setup. A manual
  // reminder must never imply that applying the profile again can repair it.
  return Boolean(
    verification &&
      verification.all_active &&
      verification.status === 'active' &&
      verification.pending_apply_settings.length === 0 &&
      verification.pending_reboot_gated_settings.length === 0 &&
      verification.mismatched_handlers.length === 0 &&
      !verification.error
  );
}

export function getPendingManualSteps(
  steps?: ManualSetupStep[] | null
): ManualSetupStep[] {
  return (steps ?? []).filter(
    (step) => step && typeof step === 'object' && step.satisfied !== true
  );
}

export function formatManualStep(step: ManualSetupStep): string {
  const scalar = (value: unknown): string | undefined =>
    typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean'
      ? String(value)
      : undefined;
  const label = step.label?.trim() || 'Manual setting';
  const current = step.current_label?.trim() || scalar(step.current) || 'Not confirmed';
  const target = step.expected_label?.trim() || scalar(step.expected);
  return `${label}: ${current}${target ? `; target: ${target}` : '; check manually'}`;
}

export function getRestartReasons(
  verification: BackendStateVerification | null | undefined,
  rebootReasons: string[] = []
): string[] {
  return uniqueStrings([
    ...rebootReasons,
    ...(verification?.pending_reboot_gated_settings ?? []),
  ]);
}

export function buildProfileUiState({
  activeProfileName,
  stateKnown,
  stateError,
  verification,
  rebootPending,
  rebootReasons,
}: {
  activeProfileName: string | null;
  stateKnown: boolean;
  stateError?: string | null;
  verification?: BackendStateVerification | null;
  rebootPending?: boolean;
  rebootReasons?: string[];
}): ProfileUiState {
  if (!stateKnown) {
    return {
      kind: 'loading',
      needsAttention: false,
      label: 'Checking backend profile state',
    };
  }

  if (stateError) {
    return {
      kind: 'unknown',
      needsAttention: true,
      label: 'Profile state unavailable',
      detail: stateError,
    };
  }

  if (!activeProfileName) {
    return {
      kind: 'none',
      needsAttention: false,
      label: 'No active profile',
    };
  }

  const pendingApply = verification?.pending_apply_settings ?? [];
  const pendingRestart = getRestartReasons(verification, rebootReasons);
  const clean = verificationIsClean(verification);

  if (verification?.status === 'error' || verification?.error) {
    return {
      kind: 'error',
      needsAttention: true,
      label: 'Profile verification failed',
      detail: verification.error,
    };
  }

  if (verification?.status === 'pending_apply' || pendingApply.length > 0) {
    return {
      kind: 'needs_apply',
      needsAttention: true,
      label: 'Profile needs apply',
      detail: formatStatusDetail(pendingApply[0] ?? activeProfileName),
    };
  }

  if (
    !clean &&
    (verification?.status === 'pending_reboot' ||
      pendingRestart.length > 0 ||
      rebootPending)
  ) {
    return {
      kind: 'needs_restart',
      needsAttention: true,
      label: 'Restart required',
      detail: formatStatusDetail(pendingRestart[0] ?? activeProfileName),
    };
  }

  if (
    verification &&
    (verification.status === 'mismatch' || verification.mismatched_handlers.length > 0)
  ) {
    return {
      kind: 'mismatch',
      needsAttention: true,
      label: 'Profile verification mismatch',
      detail: formatStatusDetail(verification.mismatched_handlers[0] ?? activeProfileName),
    };
  }

  if (!clean) {
    return {
      kind: 'unknown',
      needsAttention: true,
      label: 'Profile verification unavailable',
      detail: 'A saved profile name does not confirm that its settings are in effect.',
    };
  }

  const pendingManual = getPendingManualSteps(verification?.manual_steps);
  if (pendingManual.length > 0) {
    return {
      kind: 'needs_manual',
      needsAttention: true,
      label: 'Manual setup needed',
      detail: pendingManual.map(formatManualStep).join(' · '),
    };
  }

  return {
    kind: 'active',
    needsAttention: false,
    label: 'Active profile',
  };
}

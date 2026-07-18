import * as React from 'react';
import { AlertTriangle, Shield, ShieldOff, Clock, Gamepad2 } from 'lucide-react';
import { useAppStore } from '@/stores/appStore';
import { formatRelativeTime } from '@/lib/utils';
import { buildProfileUiState } from '@/lib/profileState';

export function StatusBar() {
  const {
    isAdmin,
    backups,
    checkAdmin,
    activeProfile,
    activeProfileAppliedAt,
    activeProfileVerification,
    activeProfileRebootPending,
    activeProfileRebootReasons,
    activeProfileStateKnown,
    activeProfileStateError,
    profiles,
  } = useAppStore();

  // Track if admin check has been done to prevent duplicate calls
  const adminCheckDone = React.useRef(false);

  React.useEffect(() => {
    if (adminCheckDone.current) return;
    adminCheckDone.current = true;
    checkAdmin();
  }, [checkAdmin]);

  const latestBackup = backups[0];
  const activeProfileName = activeProfile
    ? profiles.find((profile) => profile.id === activeProfile)?.display_name || activeProfile
    : null;
  const profileUiState = buildProfileUiState({
    activeProfileName,
    stateKnown: activeProfileStateKnown,
    stateError: activeProfileStateError,
    verification: activeProfileVerification,
    rebootPending: activeProfileRebootPending,
    rebootReasons: activeProfileRebootReasons,
  });
  const statusNeedsAttention = profileUiState.needsAttention;

  return (
    <div className="status-dock fixed bottom-0 left-0 right-0">
      <div className="container mx-auto flex items-center justify-between gap-3 px-6 py-2 text-sm">
        <div className="flex min-w-0 items-center gap-3">
          {/* Admin status */}
          <div className="status-pill">
            {isAdmin ? (
              <>
                <span className="led led--on" aria-hidden="true" />
                <Shield className="h-3.5 w-3.5 text-success" />
                <span className="text-muted-foreground">ADMIN</span>
              </>
            ) : (
              <>
                <span className="led led--warn" aria-hidden="true" />
                <ShieldOff className="h-3.5 w-3.5 text-warning" />
                <span className="text-warning">NOT ADMIN</span>
              </>
            )}
          </div>

          {/* Last backup */}
          <div className="status-pill hidden md:inline-flex">
            <Clock className="h-3.5 w-3.5 text-muted-foreground" />
            <span className="truncate text-muted-foreground">
              {latestBackup
                ? `BACKUP ${formatRelativeTime(latestBackup.created_at)}`
                : 'NO BACKUPS'}
            </span>
          </div>
        </div>

        <div className="flex min-w-0 items-center gap-3">
          <div className="status-pill max-w-[58vw]">
            <span
              className={statusNeedsAttention ? 'led led--warn' : 'led led--on'}
              aria-hidden="true"
            />
            {statusNeedsAttention ? (
              <AlertTriangle className="h-3.5 w-3.5 text-warning" />
            ) : (
              <Gamepad2 className="h-3.5 w-3.5 text-muted-foreground" />
            )}
            <span
              className={
                statusNeedsAttention
                  ? 'truncate text-warning'
                  : 'truncate text-muted-foreground'
              }
            >
              {activeProfileName
                ? profileUiState.kind === 'active'
                  ? `Active profile: ${activeProfileName}${
                      activeProfileAppliedAt
                        ? ` (${formatRelativeTime(activeProfileAppliedAt)})`
                        : ''
                    }`
                  : `${profileUiState.label}${
                      profileUiState.detail ? `: ${profileUiState.detail}` : ''
                    }`
                : profileUiState.label}
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}

import * as React from 'react';
import { AlertTriangle, Shield, ShieldOff, Clock, Gamepad2 } from 'lucide-react';
import { useAppStore } from '@/stores/appStore';
import { formatRelativeTime } from '@/lib/utils';

function formatStatusDetail(value: string): string {
  return value
    .replace(/SettingsHandler$/, ' settings')
    .replace(/Handler$/, '')
    .replace(/_/g, ' ')
    .replace(/\./g, ': ')
    .replace(/([a-z0-9])([A-Z])/g, '$1 $2');
}

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
  const verificationStatus = activeProfileVerification?.status;
  const pendingApply = activeProfileVerification?.pending_apply_settings ?? [];
  const pendingRebootGated =
    activeProfileVerification?.pending_reboot_gated_settings ?? [];
  const needsApply = verificationStatus === 'pending_apply' || pendingApply.length > 0;
  const needsRestart =
    !needsApply &&
    (activeProfileRebootPending ||
      verificationStatus === 'pending_reboot' ||
      pendingRebootGated.length > 0);
  const statusNeedsAttention = needsApply || needsRestart;
  const restartReason =
    activeProfileRebootReasons[0] ?? pendingRebootGated[0] ?? activeProfileName ?? 'profile';

  return (
    <div className="fixed bottom-0 left-0 right-0 border-t bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60">
      <div className="container mx-auto px-6 py-2 flex items-center justify-between text-sm">
        <div className="flex items-center gap-6">
          {/* Admin status */}
          <div className="flex items-center gap-2">
            {isAdmin ? (
              <>
                <Shield className="h-4 w-4 text-success" />
                <span className="text-muted-foreground">Admin</span>
              </>
            ) : (
              <>
                <ShieldOff className="h-4 w-4 text-warning" />
                <span className="text-warning">Not Admin</span>
              </>
            )}
          </div>

          {/* Last backup */}
          <div className="flex items-center gap-2">
            <Clock className="h-4 w-4 text-muted-foreground" />
            <span className="text-muted-foreground">
              {latestBackup
                ? `Last backup: ${formatRelativeTime(latestBackup.created_at)}`
                : 'No backups'}
            </span>
          </div>
        </div>

        <div className="flex items-center gap-6">
          <div className="flex items-center gap-2">
            {statusNeedsAttention ? (
              <AlertTriangle className="h-4 w-4 text-warning" />
            ) : (
              <Gamepad2 className="h-4 w-4 text-muted-foreground" />
            )}
            <span
              className={
                statusNeedsAttention
                  ? 'text-warning'
                  : 'text-muted-foreground'
              }
            >
              {activeProfileName
                ? needsApply
                  ? `Profile needs apply: ${formatStatusDetail(pendingApply[0] ?? activeProfileName)}`
                  : needsRestart
                    ? `Restart required: ${formatStatusDetail(restartReason)}`
                  : `Active profile: ${activeProfileName}${
                      activeProfileAppliedAt
                        ? ` (${formatRelativeTime(activeProfileAppliedAt)})`
                        : ''
                    }`
                : 'No active profile'}
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}

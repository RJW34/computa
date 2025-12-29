import * as React from 'react';
import { Shield, ShieldOff, Clock, CheckCircle } from 'lucide-react';
import { useAppStore } from '@/stores/appStore';
import { formatRelativeTime } from '@/lib/utils';

export function StatusBar() {
  const { isAdmin, backups, checkAdmin } = useAppStore();

  React.useEffect(() => {
    checkAdmin();
  }, [checkAdmin]);

  const latestBackup = backups[0];

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
          {/* NPI status - placeholder */}
          <div className="flex items-center gap-2">
            <CheckCircle className="h-4 w-4 text-success" />
            <span className="text-muted-foreground">NPI: Available</span>
          </div>
        </div>
      </div>
    </div>
  );
}

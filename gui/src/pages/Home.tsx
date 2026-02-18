import * as React from 'react';
import {
  Gamepad2,
  Search,
  Settings,
  Archive,
  FileText,
  Timer,
  CheckCircle2,
} from 'lucide-react';
import { ActionCard } from '@/components/cards/ActionCard';
import { HardwareSummary } from '@/components/HardwareSummary';
import { Header } from '@/components/Header';
import { useAppStore } from '@/stores/appStore';
import { Badge } from '@/components/ui/badge';

export function Home() {
  const {
    setPage,
    auditResults,
    runAudit,
    loadBackups,
    backups,
    activeProfile,
    activeProfileAppliedAt,
    profiles,
    loadProfiles,
  } = useAppStore();

  // Track if initial load has been done to prevent duplicate calls
  const initialLoadDone = React.useRef(false);

  React.useEffect(() => {
    // Only load data once on initial mount
    if (initialLoadDone.current) return;
    initialLoadDone.current = true;

    runAudit();
    loadBackups();
    void loadProfiles();
  }, [runAudit, loadBackups, loadProfiles]);

  const criticalCount = auditResults.filter((i) => i.severity === 'critical').length;
  const warningCount = auditResults.filter((i) => i.severity === 'warning').length;
  const totalIssues = criticalCount + warningCount;

  // Format the active profile applied time
  const getAppliedTimeAgo = () => {
    if (!activeProfileAppliedAt) return '';
    const appliedDate = new Date(activeProfileAppliedAt);
    const now = new Date();
    const diffMs = now.getTime() - appliedDate.getTime();
    const diffMins = Math.floor(diffMs / 60000);
    const diffHours = Math.floor(diffMins / 60);
    const diffDays = Math.floor(diffHours / 24);

    if (diffDays > 0) return `${diffDays}d ago`;
    if (diffHours > 0) return `${diffHours}h ago`;
    if (diffMins > 0) return `${diffMins}m ago`;
    return 'just now';
  };

  const activeProfileName = activeProfile
    ? (profiles.find((p) => p.id === activeProfile)?.display_name || activeProfile)
    : null;

  return (
    <div className="min-h-screen pb-12">
      <Header />

      <main className="container mx-auto px-6 py-6">
        <HardwareSummary />

        {/* Active Profile Banner */}
        {activeProfile && (
          <div className="mb-4 p-3 rounded-lg border border-success/30 bg-success/5 flex items-center justify-between">
            <div className="flex items-center gap-2">
              <CheckCircle2 className="h-5 w-5 text-success" />
              <span className="text-sm">
                Active Profile: <strong>{activeProfileName}</strong>
              </span>
              <Badge variant="outline" className="text-xs">
                {getAppliedTimeAgo()}
              </Badge>
            </div>
            <button
              onClick={() => setPage('profile-wizard')}
              className="text-sm text-muted-foreground hover:text-foreground"
            >
              Change
            </button>
          </div>
        )}

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          <ActionCard
            icon={Gamepad2}
            title="Apply Profile"
            subtitle={activeProfile ? `Active: ${activeProfileName}` : 'Optimize for a specific profile'}
            onClick={() => setPage('profile-wizard')}
          />

          <ActionCard
            icon={Search}
            title="Audit System"
            subtitle="Check for optimization issues"
            badge={
              totalIssues > 0
                ? {
                    count: totalIssues,
                    variant: criticalCount > 0 ? 'critical' : 'warning',
                  }
                : undefined
            }
            onClick={() => setPage('audit')}
          />

          <ActionCard
            icon={Settings}
            title="Settings"
            subtitle="Fine-tune individual settings"
            onClick={() => setPage('settings')}
          />

          <ActionCard
            icon={Archive}
            title="Backups"
            subtitle="Manage restore points"
            badge={
              backups.length > 0
                ? { count: backups.length, variant: 'default' }
                : undefined
            }
            onClick={() => setPage('backups')}
          />

          <ActionCard
            icon={FileText}
            title="Reports"
            subtitle="View in-game setting guides"
            onClick={() => setPage('reports')}
          />

          <ActionCard
            icon={Timer}
            title="Timer"
            subtitle="Set system timer resolution"
            onClick={() => setPage('timer')}
          />
        </div>
      </main>
    </div>
  );
}

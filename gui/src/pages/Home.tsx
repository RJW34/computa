import * as React from 'react';
import {
  Gamepad2,
  Search,
  Settings,
  Archive,
  FileText,
  Timer,
} from 'lucide-react';
import { ActionCard } from '@/components/cards/ActionCard';
import { HardwareSummary } from '@/components/HardwareSummary';
import { Header } from '@/components/Header';
import { StatusBar } from '@/components/StatusBar';
import { useAppStore } from '@/stores/appStore';

export function Home() {
  const { setPage, auditResults, runAudit, loadBackups, backups } = useAppStore();

  React.useEffect(() => {
    // Load initial data
    runAudit();
    loadBackups();
  }, [runAudit, loadBackups]);

  const criticalCount = auditResults.filter((i) => i.severity === 'critical').length;
  const warningCount = auditResults.filter((i) => i.severity === 'warning').length;
  const totalIssues = criticalCount + warningCount;

  return (
    <div className="min-h-screen pb-12">
      <Header />

      <main className="container mx-auto px-6 py-6">
        <HardwareSummary />

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          <ActionCard
            icon={Gamepad2}
            title="Apply Profile"
            subtitle="Optimize for a specific game"
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

      <StatusBar />
    </div>
  );
}

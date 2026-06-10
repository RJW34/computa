import * as React from 'react';
import { Header } from '@/components/Header';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import {
  AlertCircle,
  AlertTriangle,
  Info,
  RefreshCw,
  ChevronDown,
  ChevronUp,
  ArrowRight,
} from 'lucide-react';
import { useAppStore } from '@/stores/appStore';
import { cn } from '@/lib/utils';
import type { Severity } from '@/lib/types';

const SEVERITY_CONFIG: Record<
  Severity,
  { icon: typeof AlertCircle; label: string; variant: 'critical' | 'warning' | 'info' }
> = {
  critical: { icon: AlertCircle, label: 'Critical', variant: 'critical' },
  warning: { icon: AlertTriangle, label: 'Warning', variant: 'warning' },
  info: { icon: Info, label: 'Info', variant: 'info' },
};

export function AuditDetails() {
  const { auditResults, auditLoading, auditError, auditHasRun, runAudit, setPage } = useAppStore();
  const [expandedIssue, setExpandedIssue] = React.useState<string | null>(null);
  const [filterSeverity, setFilterSeverity] = React.useState<Severity | 'all'>('all');
  const [filterCategory, setFilterCategory] = React.useState<string>('all');

  const categories = React.useMemo(() => {
    const cats = new Set(auditResults.map((i) => i.category));
    return ['all', ...Array.from(cats)];
  }, [auditResults]);

  const filteredIssues = React.useMemo(() => {
    return auditResults.filter((issue) => {
      if (filterSeverity !== 'all' && issue.severity !== filterSeverity) {
        return false;
      }
      if (filterCategory !== 'all' && issue.category !== filterCategory) {
        return false;
      }
      return true;
    });
  }, [auditResults, filterSeverity, filterCategory]);

  const counts = React.useMemo(() => {
    return {
      critical: auditResults.filter((i) => i.severity === 'critical').length,
      warning: auditResults.filter((i) => i.severity === 'warning').length,
      info: auditResults.filter((i) => i.severity === 'info').length,
    };
  }, [auditResults]);

  return (
    <div className="min-h-screen">
      <Header showBack title="System Audit" />

      <main className="container mx-auto max-w-5xl px-6 py-6">
        {/* Severity filter chips */}
        <div className="flex flex-wrap gap-2 mb-4">
          {(['critical', 'warning', 'info'] as Severity[]).map((severity) => {
            const config = SEVERITY_CONFIG[severity];
            const isActive = filterSeverity === severity;
            return (
              <Badge
                key={severity}
                variant={isActive ? config.variant : 'outline'}
                className="cursor-pointer"
                onClick={() =>
                  setFilterSeverity(isActive ? 'all' : severity)
                }
              >
                <config.icon className="h-3 w-3 mr-1" />
                {config.label}: {counts[severity]}
              </Badge>
            );
          })}
        </div>

        {/* Category filter and refresh */}
        <div className="flex items-center justify-between mb-6">
          <div className="flex items-center gap-2">
            <span className="text-sm text-muted-foreground">Filter:</span>
            <select
              className="border rounded-md px-2 py-1 text-sm bg-background"
              value={filterCategory}
              onChange={(e) => setFilterCategory(e.target.value)}
            >
              {categories.map((cat) => (
                <option key={cat} value={cat}>
                  {cat === 'all' ? 'All Categories' : cat}
                </option>
              ))}
            </select>
          </div>

          <Button
            variant="outline"
            size="sm"
            onClick={() => void runAudit()}
            disabled={auditLoading}
          >
            <RefreshCw
              className={cn('h-4 w-4 mr-2', auditLoading && 'animate-spin')}
            />
            Re-scan
          </Button>
        </div>

        {/* Issues list */}
        <div className="space-y-3">
          {filteredIssues.length === 0 ? (
            <Card className="wizard-panel shadow-none">
              <CardContent className="py-8 text-center text-muted-foreground">
                {auditLoading
                  ? 'Running audit...'
                  : auditError
                    ? `Audit failed: ${auditError}`
                    : !auditHasRun
                      ? 'Run an audit to see findings from the current audit scope.'
                      : auditResults.length === 0
                        ? 'No issues were detected by the current audit scope.'
                  : 'No issues match the current filters.'}
              </CardContent>
            </Card>
          ) : (
            filteredIssues.map((issue, index) => {
              const config = SEVERITY_CONFIG[issue.severity];
              // Use a stable unique key combining category, title, and index
              const issueKey = `${issue.category}-${issue.title}-${index}`;
              const isExpanded = expandedIssue === issueKey;

              return (
                <Card
                  key={issueKey}
                  className={cn(
                    'wizard-panel border-l-4 shadow-none',
                    issue.severity === 'critical' && 'border-l-critical',
                    issue.severity === 'warning' && 'border-l-warning',
                    issue.severity === 'info' && 'border-l-info'
                  )}
                >
                  <CardContent className="p-4">
                    <div className="flex items-start justify-between">
                      <div className="flex-1">
                        <div className="flex items-center gap-2 mb-1">
                          <config.icon
                            className={cn(
                              'h-4 w-4',
                              issue.severity === 'critical' && 'text-critical',
                              issue.severity === 'warning' && 'text-warning',
                              issue.severity === 'info' && 'text-info'
                            )}
                          />
                          <h4 className="font-medium">{issue.title}</h4>
                        </div>
                        <div className="text-sm text-muted-foreground mb-2">
                          Current: <code className="bg-muted px-1 rounded">{issue.current_value}</code>
                          {' → '}
                          Optimal: <code className="bg-muted px-1 rounded">{issue.optimal_value}</code>
                        </div>
                        <Badge variant="outline" className="text-xs">
                          {issue.category}
                        </Badge>

                        {/* Expandable explanation */}
                        {issue.explanation && (
                          <div className="mt-3">
                            <button
                              className="text-sm text-muted-foreground flex items-center gap-1 hover:text-foreground"
                              onClick={() =>
                                setExpandedIssue(isExpanded ? null : issueKey)
                              }
                            >
                              {isExpanded ? (
                                <ChevronUp className="h-4 w-4" />
                              ) : (
                                <ChevronDown className="h-4 w-4" />
                              )}
                              Why does this matter?
                            </button>
                            {isExpanded && (
                              <p className="mt-2 text-sm text-muted-foreground bg-muted p-3 rounded-md">
                                {issue.explanation}
                              </p>
                            )}
                          </div>
                        )}
                      </div>
                    </div>
                  </CardContent>
                </Card>
              );
            })
          )}
        </div>

        {filteredIssues.length > 0 && (
          <div className="wizard-panel mt-6 px-4 py-3 text-sm text-muted-foreground">
            Per-issue fixing is not exposed here. Apply a profile to remediate, or review the profile-driven targets.
            <div className="mt-3 flex flex-wrap gap-2">
              <Button size="sm" onClick={() => setPage('profile-wizard')}>
                Apply a Profile
                <ArrowRight className="h-4 w-4 ml-2" />
              </Button>
              <Button size="sm" variant="outline" onClick={() => setPage('settings')}>
                Review Targets
              </Button>
            </div>
          </div>
        )}
      </main>
    </div>
  );
}

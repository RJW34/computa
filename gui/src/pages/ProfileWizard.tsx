import * as React from 'react';
import { Header } from '@/components/Header';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import {
  Check,
  Loader2,
  Gamepad2,
  ChevronRight,
  ChevronLeft,
  Copy,
  Undo2,
  AlertCircle,
  FileText,
} from 'lucide-react';
import { useAppStore } from '@/stores/appStore';
import { cn } from '@/lib/utils';
import type { ApplyResult } from '@/lib/types';
import * as api from '@/lib/api';

const STEPS = ['Select Profile', 'Review Scope', 'Backup Options', 'Apply'];

const HANDLER_LABEL_OVERRIDES: Record<string, string> = {
  NvidiaSettingsHandler: 'NVIDIA driver settings',
  WindowsSettingsHandler: 'Windows settings',
  PowerSettingsHandler: 'Power settings',
  NetworkSettingsHandler: 'Network settings',
  MouseSettingsHandler: 'Mouse settings',
  ProcessPriorityHandler: 'Process priority',
  CpuAffinityHandler: 'CPU affinity',
  GraphicsSettingsHandler: 'Graphics settings',
  ColorProfileSettingsHandler: 'Color settings',
  TimerSettingsHandler: 'Timer resolution',
  OBSSettingsHandler: 'OBS settings',
  Rivals2ConfigHandler: 'Rivals 2 config',
  OW2ConfigHandler: 'Overwatch 2 config',
};

function formatOptimizationTarget(target: string): string {
  return target
    .split('_')
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(' ');
}

function formatHandlerName(handlerName: string): string {
  const override = HANDLER_LABEL_OVERRIDES[handlerName];
  if (override) {
    return override;
  }

  return handlerName
    .replace(/SettingsHandler$/, '')
    .replace(/Handler$/, '')
    .replace(/([a-z0-9])([A-Z])/g, '$1 $2');
}

function addUniqueMessage(messages: string[], message?: string | null) {
  if (!message) {
    return;
  }

  const normalized = message.trim();
  if (!normalized || messages.includes(normalized)) {
    return;
  }

  messages.push(normalized);
}

function collectApplyWarnings(result: ApplyResult | null): string[] {
  if (!result) {
    return [];
  }

  const messages: string[] = [];

  result.warnings.forEach((warning) => addUniqueMessage(messages, warning));

  result.transaction?.checkpoints.forEach((checkpoint) => {
    if (checkpoint.status.toLowerCase() === 'warn') {
      addUniqueMessage(messages, checkpoint.message);
    }
  });

  result.compliance?.issues.forEach((issue) => {
    if (issue.severity !== 'warning') {
      return;
    }

    addUniqueMessage(
      messages,
      issue.details ? `${issue.message}: ${issue.details}` : issue.message
    );
  });

  return messages;
}

function collectApplyNotices(result: ApplyResult | null): string[] {
  if (!result) {
    return [];
  }

  const messages: string[] = [];
  result.notices.forEach((notice) => addUniqueMessage(messages, notice));
  return messages;
}

function buildApplyFailureMessage(result: ApplyResult | null): string {
  if (result?.error?.trim()) {
    return result.error.trim();
  }

  if (result?.failed_settings?.length) {
    return result.failed_settings.join('; ');
  }

  const failedHandlers =
    result?.results
      .filter((item) => item.status === 'failed')
      .map((item) => (item.error ? `${item.handler}: ${item.error}` : item.handler)) ?? [];
  if (failedHandlers.length > 0) {
    return failedHandlers.join('; ');
  }

  const failedCheckpoint = result?.transaction?.checkpoints.find(
    (checkpoint) => checkpoint.status.toLowerCase() === 'failed'
  );
  if (failedCheckpoint?.message) {
    return failedCheckpoint.message;
  }

  return 'Backend reported failure without a detailed error message.';
}

export function ProfileWizard() {
  const {
    setPage,
    wizardProfile,
    wizardStep,
    setWizardProfile,
    setWizardStep,
    resetWizard,
    setActiveProfile,
    profiles,
    profilesLoading,
    loadProfiles,
  } = useAppStore();

  const [createBackup, setCreateBackup] = React.useState(true);
  const [applying, setApplying] = React.useState(false);
  const [applyComplete, setApplyComplete] = React.useState(false);
  const [applyError, setApplyError] = React.useState<string | null>(null);
  const [appliedBackupId, setAppliedBackupId] = React.useState<string | null>(null);
  const [undoing, setUndoing] = React.useState(false);
  const [copyingReport, setCopyingReport] = React.useState(false);
  const [applyResult, setApplyResult] = React.useState<ApplyResult | null>(null);
  const [reportContent, setReportContent] = React.useState('');
  const [reportPath, setReportPath] = React.useState<string | null>(null);
  const [reportError, setReportError] = React.useState<string | null>(null);

  React.useEffect(() => {
    if (profiles.length === 0) {
      void loadProfiles();
    }
  }, [loadProfiles, profiles.length]);

  const selectedProfile = profiles.find((profile) => profile.id === wizardProfile);
  const applyWarnings = React.useMemo(() => collectApplyWarnings(applyResult), [applyResult]);
  const applyNotices = React.useMemo(() => collectApplyNotices(applyResult), [applyResult]);
  const applySummaryLevel =
    applyResult?.summary_level ??
    (applyWarnings.length > 0 ? 'warning' : applyNotices.length > 0 ? 'notice' : 'success');
  const committedWithWarnings = applySummaryLevel === 'warning';
  const appliedWithCautions = applySummaryLevel === 'caution';
  const appliedWithNotices = applySummaryLevel === 'notice';

  const handleBack = () => {
    if (wizardStep === 0) {
      resetWizard();
      setPage('home');
    } else {
      setWizardStep(wizardStep - 1);
    }
  };

  const handleNext = () => {
    if (wizardStep < STEPS.length - 1) {
      setWizardStep(wizardStep + 1);
    }
  };

  const handleApply = async () => {
    if (!wizardProfile) return;

    setApplying(true);
    setApplyComplete(false);
    setApplyError(null);
    setAppliedBackupId(null);
    setApplyResult(null);
    setReportContent('');
    setReportPath(null);
    setReportError(null);

    try {
      const result = await api.applyProfile(wizardProfile, createBackup);
      setApplyResult(result);

      if (result.success) {
        setAppliedBackupId(result.backup_id ?? null);

        try {
          const state = await api.getCurrentState();
          setActiveProfile(state.current_profile, state.applied_at ?? undefined);
        } catch (error) {
          console.warn('Failed to read backend active-profile state after apply:', error);
          setActiveProfile(wizardProfile);
        }

        try {
          await api.setActiveProfileBackend(wizardProfile);
        } catch (error) {
          console.warn('Failed to sync active profile with backend tray state:', error);
        }

        if (selectedProfile?.has_in_game_settings) {
          try {
            const report = await api.getReport(wizardProfile);
            setReportContent(report.content);
            setReportPath(report.path);
          } catch (error) {
            setReportError(
              error instanceof Error ? error.message : 'Failed to load in-game report'
            );
          }
        }

        setApplyComplete(true);
      } else {
        setApplyError(buildApplyFailureMessage(result));
      }
    } catch (error) {
      setApplyError(error instanceof Error ? error.message : 'Failed to apply profile');
    } finally {
      setApplying(false);
    }
  };

  const handleUndo = async () => {
    if (!appliedBackupId) {
      setApplyError(
        'Undo is unavailable because this profile was applied without creating a backup.'
      );
      return;
    }

    setUndoing(true);
    setApplyError(null);
    try {
      await api.restoreBackup(appliedBackupId);
      setActiveProfile(null);
      await api.setActiveProfileBackend(null);
      resetWizard();
      setPage('home');
    } catch (error) {
      setApplyError(error instanceof Error ? error.message : 'Failed to restore backup');
    } finally {
      setUndoing(false);
    }
  };

  const handleCopyReport = async () => {
    if (!selectedProfile?.has_in_game_settings) {
      return;
    }

    setCopyingReport(true);
    setReportError(null);
    try {
      const content =
        reportContent || (await api.getReport(selectedProfile.id)).content;
      if (!reportContent) {
        setReportContent(content);
      }
      await navigator.clipboard.writeText(content);
    } catch (error) {
      setReportError(error instanceof Error ? error.message : 'Failed to copy report');
    } finally {
      setCopyingReport(false);
    }
  };

  const handleDone = () => {
    resetWizard();
    setPage('home');
  };

  return (
    <div className="min-h-screen">
      <Header showBack title="Apply Profile" />

      <main className="container mx-auto px-6 py-6 max-w-3xl">
        <div className="mb-8">
          <div className="flex items-center justify-between mb-2">
            <span className="text-sm text-muted-foreground">
              Step {wizardStep + 1} of {STEPS.length}: {STEPS[wizardStep]}
            </span>
          </div>
          <div className="flex gap-1">
            {STEPS.map((_, i) => (
              <div
                key={i}
                className={cn(
                  'h-1.5 flex-1 rounded-full transition-colors',
                  i <= wizardStep ? 'bg-primary' : 'bg-muted'
                )}
              />
            ))}
          </div>
        </div>

        {wizardStep === 0 && (
          <div className="space-y-4">
            {profilesLoading && (
              <p className="text-sm text-muted-foreground">Loading profiles...</p>
            )}
            {profiles.map((profile) => (
              <Card
                key={profile.id}
                className={cn(
                  'cursor-pointer transition-all',
                  wizardProfile === profile.id
                    ? 'border-primary ring-2 ring-primary'
                    : 'hover:border-primary/50'
                )}
                onClick={() => setWizardProfile(profile.id)}
              >
                <CardContent className="flex items-center justify-between p-4">
                  <div className="flex items-center gap-4">
                    <Gamepad2 className="h-8 w-8 text-muted-foreground" />
                    <div>
                      <h3 className="font-semibold">{profile.display_name}</h3>
                      <p className="text-sm text-muted-foreground">{profile.description}</p>
                    </div>
                  </div>
                  {wizardProfile === profile.id && (
                    <Check className="h-5 w-5 text-primary" />
                  )}
                </CardContent>
              </Card>
            ))}
          </div>
        )}

        {wizardStep === 1 && selectedProfile && (
          <div className="space-y-4">
            <div className="mb-6">
              <h2 className="text-xl font-semibold">{selectedProfile.display_name}</h2>
              <p className="text-muted-foreground">
                Target: {formatOptimizationTarget(selectedProfile.optimization_target)}
              </p>
            </div>

            <Card>
              <CardContent className="p-4 space-y-2">
                <h4 className="font-medium">Profile Intent</h4>
                {selectedProfile.tray_subtitle && (
                  <p className="text-sm text-foreground">{selectedProfile.tray_subtitle}</p>
                )}
                <p className="text-sm text-muted-foreground">
                  {selectedProfile.tray_description || selectedProfile.description}
                </p>
              </CardContent>
            </Card>

            <Card>
              <CardContent className="p-4 space-y-3">
                <h4 className="font-medium">Backend Application Scope</h4>
                <p className="text-sm text-muted-foreground">
                  These are the backend handlers this profile will run through the apply pipeline.
                </p>
                <ul className="text-sm text-muted-foreground space-y-1">
                  {(selectedProfile.handlers || []).map((handlerName) => (
                    <li key={handlerName}>• {formatHandlerName(handlerName)}</li>
                  ))}
                </ul>
              </CardContent>
            </Card>

            <Card>
              <CardContent className="p-4 space-y-3">
                <h4 className="font-medium">Executable Matching</h4>
                <p className="text-sm text-muted-foreground">
                  ABSO uses these executable hints for detection and launch matching.
                </p>
                <ul className="text-sm text-muted-foreground space-y-1">
                  {selectedProfile.executables.map((executable) => (
                    <li key={executable}>• {executable}</li>
                  ))}
                </ul>
              </CardContent>
            </Card>

            <Card>
              <CardContent className="p-4 space-y-2">
                <h4 className="font-medium">In-Game Guidance</h4>
                <p className="text-sm text-muted-foreground">
                  {selectedProfile.has_in_game_settings
                    ? 'This profile includes an in-game settings report. ABSO will load the generated report after a successful apply.'
                    : 'This profile does not currently publish an in-game settings report.'}
                </p>
              </CardContent>
            </Card>
          </div>
        )}

        {wizardStep === 2 && (
          <div className="space-y-4">
            <p className="text-muted-foreground mb-4">
              Before applying changes, ABSO can create a backup so you can restore your
              previous settings if needed.
            </p>

            <Card
              className={cn(
                'cursor-pointer transition-all',
                createBackup ? 'border-primary ring-2 ring-primary' : 'hover:border-primary/50'
              )}
              onClick={() => setCreateBackup(true)}
            >
              <CardContent className="p-4">
                <div className="flex items-center gap-3">
                  <div
                    className={cn(
                      'w-4 h-4 rounded-full border-2',
                      createBackup ? 'border-primary bg-primary' : 'border-muted-foreground'
                    )}
                  >
                    {createBackup && (
                      <Check className="h-3 w-3 text-primary-foreground" />
                    )}
                  </div>
                  <div>
                    <h4 className="font-medium">Create backup before applying (Recommended)</h4>
                    <p className="text-sm text-muted-foreground">
                      The profile pipeline will save a restore point automatically.
                    </p>
                  </div>
                </div>
              </CardContent>
            </Card>

            <Card
              className={cn(
                'cursor-pointer transition-all',
                !createBackup ? 'border-warning ring-2 ring-warning' : 'hover:border-muted-foreground'
              )}
              onClick={() => setCreateBackup(false)}
            >
              <CardContent className="p-4">
                <div className="flex items-center gap-3">
                  <div
                    className={cn(
                      'w-4 h-4 rounded-full border-2',
                      !createBackup ? 'border-warning bg-warning' : 'border-muted-foreground'
                    )}
                  >
                    {!createBackup && (
                      <Check className="h-3 w-3 text-warning-foreground" />
                    )}
                  </div>
                  <div>
                    <h4 className="font-medium">Skip backup</h4>
                    <p className="text-sm text-warning">
                      Undo will be unavailable if you skip backup creation.
                    </p>
                  </div>
                </div>
              </CardContent>
            </Card>
          </div>
        )}

        {wizardStep === 3 && !applyComplete && (
          <div className="space-y-6 text-center py-12">
            <h2 className="text-xl font-semibold">
              {applying
                ? `Applying ${selectedProfile?.display_name}`
                : applyError
                  ? 'Apply Failed'
                  : 'Ready to Apply'}
            </h2>

            {applyError && (
              <div className="rounded-lg border border-destructive/30 bg-destructive/5 p-4 text-left text-sm text-destructive">
                <div className="flex items-start gap-2">
                  <AlertCircle className="h-5 w-5 mt-0.5" />
                  <div className="space-y-2">
                    <p>{applyError}</p>
                    {applyResult?.failed_settings && applyResult.failed_settings.length > 0 && (
                      <ul className="space-y-1">
                        {applyResult.failed_settings.map((setting) => (
                          <li key={setting}>• {setting}</li>
                        ))}
                      </ul>
                    )}
                  </div>
                </div>
              </div>
            )}

            {applying ? (
              <Card className="max-w-xl mx-auto text-left">
                <CardContent className="p-6 space-y-4">
                  <div className="flex items-center gap-3">
                    <Loader2 className="h-5 w-5 animate-spin text-primary" />
                    <span className="font-medium">Running backend profile pipeline...</span>
                  </div>
                  <div className="text-sm text-muted-foreground space-y-2">
                    <p>Backup creation: {createBackup ? 'enabled' : 'disabled'}.</p>
                    <p>
                      This screen updates when the backend finishes. Live per-handler progress is
                      not surfaced here yet, so ABSO does not fake stage-by-stage completion.
                    </p>
                  </div>
                </CardContent>
              </Card>
            ) : !applyError && (
              <p className="text-muted-foreground">
                Click Apply Now to run the full backend profile pipeline for{' '}
                {selectedProfile?.display_name}.
              </p>
            )}
          </div>
        )}

        {wizardStep === 3 && applyComplete && (
          <div className="space-y-6 text-center py-8">
            <div className="flex justify-center">
              <div
                className={cn(
                  'rounded-full p-4',
                  committedWithWarnings ? 'bg-warning/10' : 'bg-success/10'
                )}
              >
                {committedWithWarnings ? (
                  <AlertCircle className="h-12 w-12 text-warning" />
                ) : (
                  <Check className="h-12 w-12 text-success" />
                )}
              </div>
            </div>
            <h2 className="text-2xl font-semibold">
              {committedWithWarnings
                ? 'Committed With Warnings'
                : appliedWithCautions
                  ? 'Applied With Cautions'
                  : appliedWithNotices
                    ? 'Applied With Notices'
                    : 'Profile Applied'}
            </h2>
            <p className="text-muted-foreground">
              {committedWithWarnings
                ? `${selectedProfile?.display_name} applied successfully, but ABSO recorded warning conditions you should review.`
                : appliedWithCautions
                  ? `${selectedProfile?.display_name} applied successfully, with environmental cautions worth keeping in mind.`
                  : appliedWithNotices
                    ? `${selectedProfile?.display_name} applied successfully, with additional notices recorded by ABSO.`
                    : `${selectedProfile?.display_name} was applied successfully.`}
            </p>

            <Card className="text-left">
              <CardContent className="p-4 space-y-2">
                <h4 className="font-medium">Backup Status</h4>
                <p className="text-sm text-muted-foreground">
                  {appliedBackupId
                    ? `Backup created: ${appliedBackupId}`
                    : 'No backup was created for this apply.'}
                </p>
              </CardContent>
            </Card>

            {applyResult?.requires_reboot && (
              <Card className="text-left border-warning/40 bg-warning/5">
                <CardContent className="p-4 space-y-2">
                  <h4 className="font-medium">Reboot Required</h4>
                  {applyResult.reboot_reasons.length > 0 ? (
                    <ul className="text-sm text-muted-foreground space-y-1">
                      {applyResult.reboot_reasons.map((reason) => (
                        <li key={reason}>• {reason}</li>
                      ))}
                    </ul>
                  ) : (
                    <p className="text-sm text-muted-foreground">
                      The backend reported that some changes may require a reboot.
                    </p>
                  )}
                </CardContent>
              </Card>
            )}

            {applyWarnings.length > 0 && (
              <Card
                className={cn(
                  'text-left',
                  committedWithWarnings ? 'border-warning/40 bg-warning/5' : 'border-success/20 bg-success/5'
                )}
              >
                <CardContent className="p-4 space-y-3">
                  <h4 className="font-medium">
                    {committedWithWarnings ? 'Warnings' : 'Cautions'}
                  </h4>
                  <ul className="text-sm text-muted-foreground space-y-1">
                    {applyWarnings.map((warning) => (
                      <li key={warning}>• {warning}</li>
                    ))}
                  </ul>
                </CardContent>
              </Card>
            )}

            {applyNotices.length > 0 && (
              <Card className="text-left">
                <CardContent className="p-4 space-y-3">
                  <h4 className="font-medium">Notices</h4>
                  <ul className="text-sm text-muted-foreground space-y-1">
                    {applyNotices.map((notice) => (
                      <li key={notice}>â€¢ {notice}</li>
                    ))}
                  </ul>
                </CardContent>
              </Card>
            )}

            <Card className="text-left">
              <CardContent className="p-4 space-y-4">
                <div className="flex items-center gap-2">
                  <FileText className="h-4 w-4 text-muted-foreground" />
                  <h4 className="font-medium">In-Game Settings Report</h4>
                </div>

                {selectedProfile?.has_in_game_settings ? (
                  <>
                    <p className="text-sm text-muted-foreground">
                      This is the actual generated report for the selected profile.
                    </p>
                    <div className="bg-muted rounded-md p-4 font-mono text-sm whitespace-pre-wrap max-h-80 overflow-auto">
                      {reportError
                        ? `Profile applied, but the report could not be loaded: ${reportError}`
                        : reportContent || 'No in-game report content was returned.'}
                    </div>
                    {reportPath && (
                      <p className="text-xs text-muted-foreground">Report path: {reportPath}</p>
                    )}
                    <div className="flex gap-2">
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => void handleCopyReport()}
                        disabled={copyingReport || !reportContent}
                      >
                        {copyingReport ? (
                          <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                        ) : (
                          <Copy className="h-4 w-4 mr-2" />
                        )}
                        Copy to Clipboard
                      </Button>
                      <Button variant="outline" size="sm" onClick={() => setPage('reports')}>
                        View Full Report
                      </Button>
                    </div>
                  </>
                ) : (
                  <p className="text-sm text-muted-foreground">
                    This profile does not currently publish an in-game settings report.
                  </p>
                )}
              </CardContent>
            </Card>

            <div className="flex justify-center gap-4 pt-4">
              <Button
                variant="outline"
                onClick={() => void handleUndo()}
                disabled={undoing || !appliedBackupId}
              >
                {undoing ? (
                  <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                ) : (
                  <Undo2 className="h-4 w-4 mr-2" />
                )}
                {appliedBackupId ? 'Undo (Restore)' : 'Undo Unavailable'}
              </Button>
              <Button onClick={handleDone}>Done (Go Home)</Button>
            </div>
          </div>
        )}

        {!(wizardStep === 3 && applyComplete) && (
          <div className="flex justify-between mt-8">
            <Button variant="outline" onClick={handleBack}>
              <ChevronLeft className="h-4 w-4 mr-2" />
              {wizardStep === 0 ? 'Cancel' : 'Previous'}
            </Button>

            {wizardStep < 2 && (
              <Button onClick={handleNext} disabled={!wizardProfile}>
                Next
                <ChevronRight className="h-4 w-4 ml-2" />
              </Button>
            )}

            {wizardStep === 2 && (
              <Button onClick={handleNext}>
                Continue
                <ChevronRight className="h-4 w-4 ml-2" />
              </Button>
            )}

            {wizardStep === 3 && !applying && !applyComplete && (
              <Button onClick={handleApply}>
                Apply Now
                <ChevronRight className="h-4 w-4 ml-2" />
              </Button>
            )}
          </div>
        )}
      </main>
    </div>
  );
}

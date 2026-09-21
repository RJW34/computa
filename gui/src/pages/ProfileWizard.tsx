import * as React from 'react';
import { Header } from '@/components/Header';
import { ManualSetupList } from '@/components/ManualSetupList';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent } from '@/components/ui/card';
import { GameMark, gameArtVars, getGameArt } from '@/components/GameMark';
import {
  Check,
  Loader2,
  ChevronRight,
  ChevronLeft,
  Copy,
  Undo2,
  AlertCircle,
  FileText,
  Layers,
} from 'lucide-react';
import { useAppStore } from '@/stores/appStore';
import { cn } from '@/lib/utils';
import {
  getRestartReasons,
  getPendingManualSteps,
  verificationIsClean,
} from '@/lib/profileState';
import type { ApplyResult, BackendState, Profile } from '@/lib/types';
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

const PROFILE_CATEGORY_ORDER: Record<string, number> = {
  Desktop: 0,
  Fighting: 1,
  Shooters: 2,
  RPGs: 3,
  Other: 4,
};

interface ProfileGroup {
  id: string;
  name: string;
  category: string;
  rank: number;
  profiles: Profile[];
}

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
    setActiveProfileStateError,
  } = useAppStore();

  const [createBackup, setCreateBackup] = React.useState(true);
  const [applying, setApplying] = React.useState(false);
  const [applyComplete, setApplyComplete] = React.useState(false);
  const [applyError, setApplyError] = React.useState<string | null>(null);
  const [appliedBackupId, setAppliedBackupId] = React.useState<string | null>(null);
  const [undoing, setUndoing] = React.useState(false);
  const [copyingReport, setCopyingReport] = React.useState(false);
  const [applyResult, setApplyResult] = React.useState<ApplyResult | null>(null);
  const [postApplyState, setPostApplyState] = React.useState<BackendState | null>(null);
  const [reportContent, setReportContent] = React.useState('');
  const [reportPath, setReportPath] = React.useState<string | null>(null);
  const [reportError, setReportError] = React.useState<string | null>(null);
  const [categoryFilter, setCategoryFilter] = React.useState('All');

  React.useEffect(() => {
    if (profiles.length === 0) {
      void loadProfiles();
    }
  }, [loadProfiles, profiles.length]);

  const selectedProfile = profiles.find((profile) => profile.id === wizardProfile);
  const profileGroups = React.useMemo<ProfileGroup[]>(() => {
    const groups = new Map<string, ProfileGroup>();

    profiles
      .filter((profile) => profile.tray_visible !== false)
      .forEach((profile) => {
        const groupId = profile.tray_group || profile.id;
        const group = groups.get(groupId) ?? {
          id: groupId,
          name: profile.tray_group_name || profile.display_name,
          category: profile.tray_category || 'Other',
          rank: profile.tray_rank ?? 100,
          profiles: [],
        };

        group.rank = Math.min(group.rank, profile.tray_rank ?? 100);
        group.profiles.push(profile);
        groups.set(groupId, group);
      });

    return Array.from(groups.values())
      .map((group) => ({
        ...group,
        profiles: group.profiles.sort(
          (a, b) =>
            (a.tray_rank ?? 100) - (b.tray_rank ?? 100) ||
            (a.tray_variant || a.display_name).localeCompare(b.tray_variant || b.display_name)
        ),
      }))
      .sort(
        (a, b) =>
          (PROFILE_CATEGORY_ORDER[a.category] ?? 99) -
            (PROFILE_CATEGORY_ORDER[b.category] ?? 99) ||
          a.rank - b.rank ||
          a.name.localeCompare(b.name)
      );
  }, [profiles]);
  const visibleCategories = React.useMemo(
    () => [
      'All',
      ...Array.from(new Set(profileGroups.map((group) => group.category))).sort(
        (a, b) =>
          (PROFILE_CATEGORY_ORDER[a] ?? 99) - (PROFILE_CATEGORY_ORDER[b] ?? 99) ||
          a.localeCompare(b)
      ),
    ],
    [profileGroups]
  );
  const filteredProfileGroups = React.useMemo(
    () =>
      categoryFilter === 'All'
        ? profileGroups
        : profileGroups.filter((group) => group.category === categoryFilter),
    [categoryFilter, profileGroups]
  );
  const selectedArt = getGameArt(selectedProfile);
  const selectedGroupId = selectedProfile?.tray_group || selectedProfile?.id || null;
  const applyWarnings = React.useMemo(() => collectApplyWarnings(applyResult), [applyResult]);
  const applyNotices = React.useMemo(() => collectApplyNotices(applyResult), [applyResult]);
  const applySummaryLevel =
    applyResult?.summary_level ??
    (applyWarnings.length > 0 ? 'warning' : applyNotices.length > 0 ? 'notice' : 'success');
  const committedWithWarnings = applySummaryLevel === 'warning';
  const appliedWithCautions = applySummaryLevel === 'caution';
  const appliedWithNotices = applySummaryLevel === 'notice';
  const applyChanged = applyResult?.changed;
  const completedProfileName = applyResult?.profile
    ? profiles.find((profile) => profile.id === applyResult.profile)?.display_name ??
      applyResult.profile
    : selectedProfile?.display_name ?? 'Profile';
  const postApplyRestartReasons = postApplyState
    ? getRestartReasons(postApplyState.verification, postApplyState.reboot_reasons)
    : getRestartReasons(null, applyResult?.reboot_reasons ?? []);
  const postApplyVerificationClean = verificationIsClean(postApplyState?.verification);
  const postApplyManualSteps = postApplyState?.verification?.manual_steps ?? applyResult?.manual_steps;
  const postApplyNeedsManualSetup = getPendingManualSteps(postApplyManualSteps).length > 0;
  const postApplyNeedsRestart = postApplyState
    ? !postApplyVerificationClean &&
      (postApplyState.reboot_pending || postApplyRestartReasons.length > 0)
    : Boolean(applyResult?.requires_reboot);
  const applyCompletionMessage = applyChanged === false
    ? applyNotices[0] ?? `${completedProfileName} was already current.`
    : committedWithWarnings
      ? postApplyVerificationClean
        ? `${completedProfileName} completed with warnings and verified active.`
        : `${completedProfileName} completed with warnings worth reviewing.`
      : appliedWithCautions
        ? `${completedProfileName} completed with environmental cautions worth noting.`
        : appliedWithNotices
          ? `${completedProfileName} completed with notices below.`
          : postApplyVerificationClean
            ? `${completedProfileName} applied and verified active.`
            : postApplyNeedsRestart
              ? `${completedProfileName} applied; restart is required for the listed settings.`
              : `${completedProfileName} applied; backend state was refreshed.`;

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
    setPostApplyState(null);
    setReportContent('');
    setReportPath(null);
    setReportError(null);

    try {
      const result = await api.applyProfile(wizardProfile, createBackup);
      setApplyResult(result);

      if (result.success) {
        setAppliedBackupId(result.backup_id ?? null);
        let trayProfileId: string | null = result.profile ?? wizardProfile;

        try {
          const state = await api.getCurrentState();
          setPostApplyState(state);
          trayProfileId = state.current_profile ?? trayProfileId;
          setActiveProfile(
            state.current_profile,
            state.applied_at ?? undefined,
            state.verification ?? null,
            state.reboot_pending,
            state.reboot_reasons
          );
        } catch (error) {
          console.warn('Failed to read backend active-profile state after apply:', error);
          setActiveProfileStateError(
            error instanceof Error ? error.message : 'Failed to read backend state after apply'
          );
        }

        try {
          await api.setActiveProfileBackend(trayProfileId);
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

      <main className="container mx-auto max-w-6xl space-y-6 px-6 py-6">
        <section className="command-hero panel-enter p-5" style={gameArtVars(selectedArt)}>
          <div className="grid gap-5 lg:grid-cols-[0.9fr_1.1fr] lg:items-center">
            <div className="flex min-w-0 items-center gap-4">
              <GameMark profile={selectedProfile} size="hero" active={Boolean(selectedProfile)} />
              <div className="min-w-0">
                <p className="section-kicker">Profile pipeline</p>
                <h2 className="max-w-2xl text-3xl font-black leading-tight">
                  {selectedProfile?.display_name || 'Choose a title'}
                </h2>
                <p className="mt-2 line-clamp-2 text-sm text-muted-foreground">
                  {selectedProfile?.tray_description ||
                    selectedProfile?.description ||
                    'Select a game group, review the exact backend scope, and apply with a rollback point.'}
                </p>
              </div>
            </div>

            <div className="step-rail">
              {STEPS.map((step, i) => (
                <div
                  key={step}
                  className={cn('step-node', i <= wizardStep && 'step-node--active')}
                >
                  {i + 1}. {step}
                </div>
              ))}
            </div>
          </div>
        </section>

        {wizardStep === 0 && (
          <div className="space-y-4 panel-enter stagger-1">
            {profilesLoading && (
              <p className="text-sm text-muted-foreground">Loading profiles...</p>
            )}
            <div className="flex flex-wrap gap-2">
              {visibleCategories.map((category) => (
                <Button
                  key={category}
                  type="button"
                  variant={categoryFilter === category ? 'default' : 'outline'}
                  size="sm"
                  onClick={() => setCategoryFilter(category)}
                >
                  {category}
                </Button>
              ))}
            </div>

            <div className="grid gap-4 lg:grid-cols-2">
              {filteredProfileGroups.map((group) => {
                const art = getGameArt({ id: group.id });
                const groupIsSelected = selectedGroupId === group.id;

                return (
                  <section
                    key={group.id}
                    className={cn(
                      'wizard-panel p-4 panel-enter',
                      groupIsSelected && 'border-primary/50'
                    )}
                    style={gameArtVars(art)}
                  >
                    <div className="relative mb-4 flex items-center justify-between gap-4">
                      <GameMark groupId={group.id} size="lg" showName active={groupIsSelected} />
                      <div className="flex flex-col items-end gap-2">
                        <Badge variant={groupIsSelected ? 'success' : 'outline'}>
                          {group.category}
                        </Badge>
                        <span className="text-xs text-muted-foreground">
                          {group.profiles.length} lane{group.profiles.length === 1 ? '' : 's'}
                        </span>
                      </div>
                    </div>

                    <div className="relative grid gap-2">
                      {group.profiles.map((profile) => (
                        <button
                          key={profile.id}
                          type="button"
                          className={cn(
                            'flex min-w-0 items-center justify-between gap-3 rounded-md border p-3 text-left transition-all',
                            wizardProfile === profile.id
                              ? 'border-primary bg-primary/10 text-foreground'
                              : 'border-border/70 bg-background/40 hover:border-primary/40 hover:bg-primary/5'
                          )}
                          onClick={() => setWizardProfile(profile.id)}
                        >
                          <div className="min-w-0">
                            <h4 className="truncate font-bold">
                              {profile.tray_variant || profile.display_name}
                            </h4>
                            <p className="line-clamp-2 text-sm text-muted-foreground">
                              {profile.tray_subtitle || profile.description}
                            </p>
                          </div>
                          <div className="flex flex-none items-center gap-2">
                            <Badge variant={profile.sync_mode === 'off' ? 'warning' : 'outline'}>
                              {profile.sync_mode === 'off'
                                ? 'No Sync'
                                : profile.sync_mode === 'on'
                                  ? 'Sync'
                                  : 'Adaptive'}
                            </Badge>
                            {wizardProfile === profile.id && (
                              <Check className="h-5 w-5 text-primary" />
                            )}
                          </div>
                        </button>
                      ))}
                    </div>
                  </section>
                );
              })}
            </div>
          </div>
        )}

        {wizardStep === 1 && selectedProfile && (
          <div className="space-y-4 panel-enter stagger-1">
            <div className="wizard-panel p-4" style={gameArtVars(selectedArt)}>
              <div className="relative flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
                <div className="flex min-w-0 items-center gap-4">
                  <GameMark profile={selectedProfile} size="lg" showName active />
                  <div className="min-w-0">
                    <h2 className="truncate text-2xl font-black">{selectedProfile.display_name}</h2>
                    <p className="text-sm text-muted-foreground">
                      Target: {formatOptimizationTarget(selectedProfile.optimization_target)}
                    </p>
                  </div>
                </div>
                <div className="flex flex-wrap gap-2">
                  <Badge variant="outline">{selectedProfile.tray_category || 'Other'}</Badge>
                  <Badge variant={selectedProfile.sync_mode === 'off' ? 'warning' : 'outline'}>
                    {selectedProfile.sync_mode === 'off'
                      ? 'No Sync'
                      : selectedProfile.sync_mode === 'on'
                        ? 'Sync On'
                        : 'Adaptive Sync'}
                  </Badge>
                  {selectedProfile.has_in_game_settings && (
                    <Badge variant="success">Report</Badge>
                  )}
                </div>
              </div>
            </div>

            <Card className="wizard-panel shadow-none">
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

            <Card className="wizard-panel shadow-none">
              <CardContent className="p-4 space-y-3">
                <div className="flex items-center gap-2">
                  <Layers className="h-4 w-4 text-primary" />
                  <h4 className="font-medium">Backend Application Scope</h4>
                </div>
                <p className="text-sm text-muted-foreground">
                  {selectedProfile.application_scope === 'system_plus_native_config'
                    ? 'Applies machine-level settings and a title-specific config handler.'
                    : 'Applies machine-level settings only; the title still relies on manual in-game configuration.'}
                </p>
                <ul className="text-sm text-muted-foreground space-y-1">
                  {(selectedProfile.handlers || []).map((handlerName) => (
                    <li key={handlerName}>- {formatHandlerName(handlerName)}</li>
                  ))}
                </ul>
              </CardContent>
            </Card>

            <Card className="wizard-panel shadow-none">
              <CardContent className="p-4 space-y-3">
                <h4 className="font-medium">Executable Matching</h4>
                <p className="text-sm text-muted-foreground">
                  ABSO uses these executable hints for detection and launch matching.
                </p>
                <ul className="text-sm text-muted-foreground space-y-1">
                  {selectedProfile.executables.map((executable) => (
                    <li key={executable}>- {executable}</li>
                  ))}
                </ul>
              </CardContent>
            </Card>

            <Card className="wizard-panel shadow-none">
              <CardContent className="p-4 space-y-2">
                <h4 className="font-medium">In-Game Guidance</h4>
                <p className="text-sm text-muted-foreground">
                  {selectedProfile.has_in_game_settings
                    ? 'An in-game settings report loads after a successful apply.'
                    : 'No in-game settings report for this profile.'}
                </p>
              </CardContent>
            </Card>
          </div>
        )}

        {wizardStep === 2 && (
          <div className="space-y-4 panel-enter stagger-1">
            <p className="text-muted-foreground mb-4">
              ABSO can create a backup first so you can roll back if needed.
            </p>

            <Card
              className={cn(
                'wizard-panel cursor-pointer shadow-none transition-all',
                createBackup ? 'border-primary ring-2 ring-primary' : 'hover:border-primary/50'
              )}
              style={gameArtVars(selectedArt)}
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
                      A restore point is saved automatically.
                    </p>
                  </div>
                </div>
              </CardContent>
            </Card>

            <Card
              className={cn(
                'wizard-panel cursor-pointer shadow-none transition-all',
                !createBackup ? 'border-warning ring-2 ring-warning' : 'hover:border-muted-foreground'
              )}
              style={gameArtVars(selectedArt)}
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
                      Undo will be unavailable.
                    </p>
                  </div>
                </div>
              </CardContent>
            </Card>
          </div>
        )}

        {wizardStep === 3 && !applyComplete && (
          <div className="space-y-6 text-center py-12 panel-enter stagger-1">
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
              <Card className="wizard-panel mx-auto max-w-xl text-left shadow-none" style={gameArtVars(selectedArt)}>
                <CardContent className="p-6 space-y-4">
                  <div className="flex items-center gap-3">
                    <Loader2 className="h-5 w-5 animate-spin text-primary" />
                    <span className="font-medium">Running backend profile pipeline...</span>
                  </div>
                  <div className="text-sm text-muted-foreground space-y-2">
                    <p>Backup: {createBackup ? 'enabled' : 'skipped'}.</p>
                    <p>
                      This screen updates when the backend finishes. Per-handler progress is not
                      yet streamed live.
                    </p>
                  </div>
                </CardContent>
              </Card>
            ) : !applyError && (
              <p className="text-muted-foreground">
                Click Apply Now to run the profile pipeline for {selectedProfile?.display_name}.
              </p>
            )}
          </div>
        )}

        {wizardStep === 3 && applyComplete && (
          <div className="space-y-6 text-center py-8 panel-enter stagger-1">
            <div className="flex justify-center">
              <div
                className={cn(
                  'rounded-full p-4',
                  committedWithWarnings || postApplyNeedsManualSetup ? 'bg-warning/10' : 'bg-success/10'
                )}
              >
                {committedWithWarnings || postApplyNeedsManualSetup ? (
                  <AlertCircle className="h-12 w-12 text-warning" />
                ) : (
                  <Check className="h-12 w-12 text-success" />
                )}
              </div>
            </div>
            <h2 className="text-2xl font-semibold">
              {applyChanged === false
                ? 'No Profile Changes Needed'
                : committedWithWarnings
                ? 'Completed With Warnings'
                : appliedWithCautions
                  ? 'Completed With Cautions'
                  : appliedWithNotices
                    ? 'Completed With Notices'
                    : 'Apply Completed'}
            </h2>
            <p className="text-muted-foreground">
              {applyCompletionMessage}
              {postApplyNeedsManualSetup && ' Manual setup still needs attention below.'}
            </p>

            {postApplyNeedsManualSetup && (
              <Card className="wizard-panel border-warning/40 bg-warning/5 text-left shadow-none" style={gameArtVars(selectedArt)}>
                <CardContent className="p-4">
                  <ManualSetupList steps={postApplyManualSteps} />
                </CardContent>
              </Card>
            )}

            <Card className="wizard-panel text-left shadow-none" style={gameArtVars(selectedArt)}>
              <CardContent className="p-4 space-y-2">
                <h4 className="font-medium">Backup Status</h4>
                <p className="text-sm text-muted-foreground">
                  {appliedBackupId
                    ? `Backup created: ${appliedBackupId}`
                    : 'No backup created.'}
                </p>
              </CardContent>
            </Card>

            {postApplyNeedsRestart && (
              <Card className="wizard-panel border-warning/40 bg-warning/5 text-left shadow-none" style={gameArtVars(selectedArt)}>
                <CardContent className="p-4 space-y-2">
                  <h4 className="font-medium">Reboot Required</h4>
                  {postApplyRestartReasons.length > 0 ? (
                    <ul className="text-sm text-muted-foreground space-y-1">
                      {postApplyRestartReasons.map((reason) => (
                        <li key={reason}>• {reason}</li>
                      ))}
                    </ul>
                  ) : (
                    <p className="text-sm text-muted-foreground">
                      Some changes may require a reboot.
                    </p>
                  )}
                </CardContent>
              </Card>
            )}

            {applyWarnings.length > 0 && (
              <Card
                className={cn(
                  'wizard-panel text-left shadow-none',
                  committedWithWarnings ? 'border-warning/40 bg-warning/5' : 'border-success/20 bg-success/5'
                )}
                style={gameArtVars(selectedArt)}
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
              <Card className="wizard-panel text-left shadow-none" style={gameArtVars(selectedArt)}>
                <CardContent className="p-4 space-y-3">
                  <h4 className="font-medium">Notices</h4>
                  <ul className="text-sm text-muted-foreground space-y-1">
                    {applyNotices.map((notice) => (
                      <li key={notice}>• {notice}</li>
                    ))}
                  </ul>
                </CardContent>
              </Card>
            )}

            <Card className="wizard-panel text-left shadow-none" style={gameArtVars(selectedArt)}>
              <CardContent className="p-4 space-y-4">
                <div className="flex items-center gap-2">
                  <FileText className="h-4 w-4 text-muted-foreground" />
                  <h4 className="font-medium">In-Game Settings Report</h4>
                </div>

                {selectedProfile?.has_in_game_settings ? (
                  <>
                    <p className="text-sm text-muted-foreground">
                      Generated for this profile.
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
              <Button onClick={handleDone}>Done</Button>
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

import * as React from 'react';
import {
  Activity,
  Archive,
  CheckCircle2,
  FileText,
  Gamepad2,
  Search,
  Settings,
  Shield,
  Timer,
  Zap,
  AlertTriangle,
  RefreshCw,
} from 'lucide-react';
import { ActionCard } from '@/components/cards/ActionCard';
import { GameMark, gameArtVars, getGameArt } from '@/components/GameMark';
import { HardwareSummary } from '@/components/HardwareSummary';
import { Header } from '@/components/Header';
import { ManualSetupList } from '@/components/ManualSetupList';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { useAppStore } from '@/stores/appStore';
import { buildProfileUiState, canAcceptProfileReadback } from '@/lib/profileState';
import { cn, formatRelativeTime } from '@/lib/utils';
import type { Profile } from '@/lib/types';
import * as api from '@/lib/api';

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

function buildProfileGroups(profiles: Profile[]): ProfileGroup[] {
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
}

export function Home() {
  const {
    setPage,
    auditResults,
    runAudit,
    loadBackups,
    backups,
    activeProfile,
    activeProfileAppliedAt,
    activeProfileVerification,
    activeProfileRebootPending,
    activeProfileRebootReasons,
    activeProfileStateKnown,
    activeProfileStateError,
    profiles,
    loadProfiles,
    setWizardProfile,
    isAdmin,
    setActiveProfile,
    setActiveProfileStateError,
  } = useAppStore();

  const initialLoadDone = React.useRef(false);
  const verificationInFlight = React.useRef(false);
  const [checkingProfile, setCheckingProfile] = React.useState(false);

  const verifyCurrentProfile = async () => {
    if (verificationInFlight.current) return;
    const startingState = useAppStore.getState();
    if (!startingState.activeProfileStateKnown) return;
    verificationInFlight.current = true;
    setCheckingProfile(true);
    const stillCurrent = () => canAcceptProfileReadback(startingState, useAppStore.getState());
    try {
      const state = await api.getCurrentState();
      if (!stillCurrent()) return;
      setActiveProfile(
        state.current_profile, state.applied_at ?? undefined, state.verification ?? null,
        state.reboot_pending, state.reboot_reasons
      );
    } catch (error) {
      if (stillCurrent()) {
        setActiveProfileStateError(error instanceof Error ? error.message : 'Profile verification failed');
      }
    } finally {
      verificationInFlight.current = false;
      setCheckingProfile(false);
    }
  };

  React.useEffect(() => {
    if (initialLoadDone.current) return;
    initialLoadDone.current = true;

    runAudit();
    loadBackups();
    void loadProfiles();
  }, [runAudit, loadBackups, loadProfiles]);

  const profileGroups = React.useMemo(() => buildProfileGroups(profiles), [profiles]);
  const criticalCount = auditResults.filter((i) => i.severity === 'critical').length;
  const warningCount = auditResults.filter((i) => i.severity === 'warning').length;
  const totalIssues = criticalCount + warningCount;
  const activeProfileObject = activeProfile
    ? profiles.find((profile) => profile.id === activeProfile) ?? null
    : null;
  const activeProfileName = activeProfileObject?.display_name || activeProfile || null;
  const profileUiState = buildProfileUiState({
    activeProfileName,
    stateKnown: activeProfileStateKnown,
    stateError: activeProfileStateError,
    verification: activeProfileVerification,
    rebootPending: activeProfileRebootPending,
    rebootReasons: activeProfileRebootReasons,
  });
  const activeGroupId = activeProfileObject?.tray_group || activeProfileObject?.id || null;
  const heroArt = getGameArt(activeProfileObject);
  const latestBackup = backups[0];
  const activeCopy =
    activeProfileName && profileUiState.kind === 'active'
      ? `${activeProfileName} is verified active.`
      : profileUiState.detail
        ? `${profileUiState.label}: ${profileUiState.detail}`
      : activeProfileName
        ? `${profileUiState.label}: ${activeProfileName}`
        : profileUiState.label;

  const openProfileGroup = (group: ProfileGroup) => {
    const preferredProfile =
      group.profiles.find((profile) => profile.id === activeProfile) ?? group.profiles[0];
    setWizardProfile(preferredProfile?.id ?? null);
    setPage('profile-wizard');
  };

  return (
    <div className="min-h-screen">
      <Header />

      <main className="container mx-auto space-y-7 px-6 py-6">
        <section className="command-hero panel-enter p-5 md:p-6" style={gameArtVars(heroArt)}>
          <div className="grid gap-6 lg:grid-cols-[1.15fr_0.85fr] lg:items-end">
            <div className="flex min-w-0 flex-col gap-5">
              <div className="flex min-w-0 items-center gap-4">
                <GameMark
                  profile={activeProfileObject}
                  size="hero"
                  active={!profileUiState.needsAttention}
                />
                <div className="min-w-0">
                  <p className="section-kicker">Live profile</p>
                  <h2 className="max-w-2xl text-3xl font-black leading-tight md:text-4xl">
                    {activeProfileName || 'No active profile'}
                  </h2>
                  <p
                    className={cn(
                      'mt-2 max-w-2xl text-sm',
                      profileUiState.needsAttention
                        ? 'text-warning'
                        : 'text-muted-foreground'
                    )}
                  >
                    {activeCopy}
                  </p>
                </div>
              </div>

              <div className="flex flex-wrap gap-2">
                <Button onClick={() => setPage('profile-wizard')} className="gap-2">
                  <Gamepad2 className="h-4 w-4" />
                  Change profile
                </Button>
                <Button variant="outline" onClick={() => setPage('audit')} className="gap-2">
                  <Search className="h-4 w-4" />
                  Review audit
                </Button>
              </div>
            </div>

            <div className="metric-strip">
              <div className="metric-chip">
                <div className="metric-chip__label">State</div>
                <div className="metric-chip__value">
                  {profileUiState.needsAttention ? profileUiState.label : 'Ready'}
                </div>
              </div>
              <div className="metric-chip">
                <div className="metric-chip__label">Applied</div>
                <div className="metric-chip__value">
                  {activeProfileAppliedAt ? formatRelativeTime(activeProfileAppliedAt) : 'Unknown'}
                </div>
              </div>
              <div className="metric-chip">
                <div className="metric-chip__label">Audit</div>
                <div className="metric-chip__value">
                  {totalIssues > 0 ? `${totalIssues} issue${totalIssues === 1 ? '' : 's'}` : 'Clean'}
                </div>
              </div>
              <div className="metric-chip">
                <div className="metric-chip__label">Backups</div>
                <div className="metric-chip__value">{backups.length || 'None'}</div>
              </div>
            </div>
          </div>
        </section>

        <HardwareSummary />

        <section className="space-y-4 panel-enter stagger-1">
          <div className="section-heading">
            <div>
              <p className="section-kicker">Game deck</p>
              <h2 className="text-2xl font-black">Profile roster</h2>
            </div>
            <Badge variant="outline" className="hidden md:inline-flex">
              {profileGroups.length} title groups / {profiles.length} variants
            </Badge>
          </div>

          <div className="profile-roster">
            {profileGroups.map((group) => {
              const art = getGameArt({ id: group.id });
              const isActiveGroup = activeGroupId === group.id;
              const variantPreview = group.profiles
                .slice(0, 3)
                .map((profile) => profile.tray_variant || profile.display_name)
                .join(' / ');

              return (
                <button
                  key={group.id}
                  type="button"
                  className={cn(
                    'profile-group-tile text-left panel-enter',
                    isActiveGroup && 'profile-group-tile--active'
                  )}
                  style={gameArtVars(art)}
                  onClick={() => openProfileGroup(group)}
                >
                  <div className="relative flex items-start justify-between gap-4">
                    <GameMark groupId={group.id} size="lg" showName active={isActiveGroup} />
                    <div className="flex flex-col items-end gap-2">
                      <Badge variant={isActiveGroup ? 'success' : 'outline'}>
                        {isActiveGroup ? 'Live' : group.category}
                      </Badge>
                      <span className="text-xs text-muted-foreground">
                        {group.profiles.length} variant{group.profiles.length === 1 ? '' : 's'}
                      </span>
                    </div>
                  </div>
                  <p className="relative mt-4 line-clamp-2 text-sm text-muted-foreground">
                    {variantPreview}
                  </p>
                </button>
              );
            })}
          </div>
        </section>

        <section className="space-y-4 panel-enter stagger-2">
          <div className="section-heading">
            <div>
              <p className="section-kicker">Operations</p>
              <h2 className="text-2xl font-black">Control surface</h2>
            </div>
            <div className="hidden items-center gap-2 text-sm text-muted-foreground md:flex">
              {isAdmin ? (
                <>
                  <Shield className="h-4 w-4 text-success" />
                  Elevated runtime
                </>
              ) : (
                <>
                  <AlertTriangle className="h-4 w-4 text-warning" />
                  Standard runtime
                </>
              )}
            </div>
          </div>

          <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
            <ActionCard
              icon={Gamepad2}
              title="Apply Profile"
              subtitle={activeProfileName ? `Live: ${activeProfileName}` : 'Optimize for a title'}
              onClick={() => setPage('profile-wizard')}
            />

            <ActionCard
              icon={Activity}
              title="System Audit"
              subtitle="Check drift, warnings, and profile readiness"
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
              subtitle="Inspect profile-driven setting targets"
              onClick={() => setPage('settings')}
            />

            <ActionCard
              icon={Archive}
              title="Backups"
              subtitle={
                latestBackup
                  ? `Latest restore point: ${formatRelativeTime(latestBackup.created_at)}`
                  : 'Create and restore rollback points'
              }
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
              subtitle="Open title-specific in-game settings notes"
              onClick={() => setPage('reports')}
            />

            <ActionCard
              icon={Timer}
              title="Timer"
              subtitle="Inspect current timer resolution"
              onClick={() => setPage('timer')}
            />
          </div>
        </section>

        <section className="wizard-panel panel-enter stagger-3 p-4" style={gameArtVars(heroArt)}>
          <div className="relative flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
            <div className="flex items-center gap-3">
              {profileUiState.needsAttention ? (
                <AlertTriangle className="h-5 w-5 text-warning" />
              ) : (
                <CheckCircle2 className="h-5 w-5 text-success" />
              )}
              <div>
                <h3 className="font-bold">Profile state details</h3>
                <p className="text-sm text-muted-foreground">
                  {profileUiState.detail ||
                    (activeProfileVerification?.checked_at
                      ? `Verified ${formatRelativeTime(activeProfileVerification.checked_at)}`
                      : 'Backend verification runs when the app opens.')}
                </p>
              </div>
            </div>
            <div className="flex flex-wrap items-center gap-3 text-sm text-muted-foreground">
              <span className="flex items-center gap-2">
                <Zap className="h-4 w-4 text-primary" />
                {profiles.length} profile variants loaded
              </span>
              <Button variant="outline" size="sm" disabled={checkingProfile || !activeProfileStateKnown}
                onClick={() => void verifyCurrentProfile()}>
                <RefreshCw className={cn('mr-2 h-4 w-4', checkingProfile && 'animate-spin')} />
                {checkingProfile ? 'Checking settings…' : 'Verify profile'}
              </Button>
            </div>
          </div>
          {profileUiState.kind === 'needs_manual' && (
            <div className="relative mt-4 border-t border-border pt-4">
              <ManualSetupList steps={activeProfileVerification?.manual_steps} />
            </div>
          )}
        </section>
      </main>
    </div>
  );
}

import * as React from 'react';
import { Header } from '@/components/Header';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Progress } from '@/components/ui/progress';
import {
  Check,
  Loader2,
  Gamepad2,
  ChevronRight,
  ChevronLeft,
  Copy,
  Undo2,
} from 'lucide-react';
import { useAppStore } from '@/stores/appStore';
import { cn } from '@/lib/utils';

const PROFILES = [
  {
    id: 'slippi-melee',
    name: 'Slippi Melee',
    description: 'Ultra-low latency for competitive SSBM',
    target: 'minimum_latency',
  },
  {
    id: 'rivals2',
    name: 'Rivals of Aether 2',
    description: 'VRR-optimized for UE5 fighting game',
    target: 'vrr_fighting_game',
  },
  {
    id: 'cod-bo7',
    name: 'Call of Duty: Black Ops 7',
    description: 'Low latency with Nvidia Reflex',
    target: 'low_latency_high_fps',
  },
  {
    id: 'diablo4',
    name: 'Diablo 4',
    description: 'Balanced performance for ARPG',
    target: 'balanced',
  },
];

const STEPS = ['Select Game', 'Review Settings', 'Backup Options', 'Apply'];

export function ProfileWizard() {
  const {
    setPage,
    wizardProfile,
    wizardStep,
    setWizardProfile,
    setWizardStep,
    resetWizard,
  } = useAppStore();

  const [createBackup, setCreateBackup] = React.useState(true);
  const [applying, setApplying] = React.useState(false);
  const [applyProgress, setApplyProgress] = React.useState(0);
  const [applyComplete, setApplyComplete] = React.useState(false);

  const selectedProfile = PROFILES.find((p) => p.id === wizardProfile);

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
    setApplying(true);
    setApplyProgress(0);

    // Simulate apply progress
    const steps = ['Backup', 'Windows', 'Nvidia', 'Power', 'Registry', 'Mouse'];
    for (let i = 0; i < steps.length; i++) {
      await new Promise((resolve) => setTimeout(resolve, 500));
      setApplyProgress(((i + 1) / steps.length) * 100);
    }

    setApplying(false);
    setApplyComplete(true);
  };

  const handleDone = () => {
    resetWizard();
    setPage('home');
  };

  return (
    <div className="min-h-screen">
      <Header showBack title="Apply Profile" />

      <main className="container mx-auto px-6 py-6 max-w-3xl">
        {/* Progress indicator */}
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

        {/* Step 0: Select Game */}
        {wizardStep === 0 && (
          <div className="space-y-4">
            {PROFILES.map((profile) => (
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
                      <h3 className="font-semibold">{profile.name}</h3>
                      <p className="text-sm text-muted-foreground">
                        {profile.description}
                      </p>
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

        {/* Step 1: Review Settings */}
        {wizardStep === 1 && selectedProfile && (
          <div className="space-y-4">
            <div className="mb-6">
              <h2 className="text-xl font-semibold">{selectedProfile.name}</h2>
              <p className="text-muted-foreground">
                Target: {selectedProfile.target.replace(/_/g, ' ')}
              </p>
            </div>

            <p className="text-muted-foreground mb-4">
              This profile will change:
            </p>

            <Card>
              <CardContent className="p-4">
                <h4 className="font-medium mb-2">Windows</h4>
                <ul className="text-sm text-muted-foreground space-y-1">
                  <li>• Game Mode: ON</li>
                  <li>• HAGS: Profile-dependent</li>
                  <li>• Fullscreen Optimizations: DISABLED</li>
                </ul>
              </CardContent>
            </Card>

            <Card>
              <CardContent className="p-4">
                <h4 className="font-medium mb-2">Nvidia</h4>
                <ul className="text-sm text-muted-foreground space-y-1">
                  <li>• Low Latency Mode: ON</li>
                  <li>• Power Management: Maximum Performance</li>
                  <li>• VSync: Profile-dependent</li>
                </ul>
              </CardContent>
            </Card>

            <Card>
              <CardContent className="p-4">
                <h4 className="font-medium mb-2">Power</h4>
                <ul className="text-sm text-muted-foreground space-y-1">
                  <li>• Power Plan: Ultimate Performance</li>
                </ul>
              </CardContent>
            </Card>
          </div>
        )}

        {/* Step 2: Backup Options */}
        {wizardStep === 2 && (
          <div className="space-y-4">
            <p className="text-muted-foreground mb-4">
              Before applying changes, A.B.S.O. can create a backup so you can
              restore your previous settings if needed.
            </p>

            <Card
              className={cn(
                'cursor-pointer transition-all',
                createBackup
                  ? 'border-primary ring-2 ring-primary'
                  : 'hover:border-primary/50'
              )}
              onClick={() => setCreateBackup(true)}
            >
              <CardContent className="p-4">
                <div className="flex items-center gap-3">
                  <div
                    className={cn(
                      'w-4 h-4 rounded-full border-2',
                      createBackup
                        ? 'border-primary bg-primary'
                        : 'border-muted-foreground'
                    )}
                  >
                    {createBackup && (
                      <Check className="h-3 w-3 text-primary-foreground" />
                    )}
                  </div>
                  <div>
                    <h4 className="font-medium">
                      Create backup before applying (Recommended)
                    </h4>
                    <p className="text-sm text-muted-foreground">
                      A restore point will be saved automatically
                    </p>
                  </div>
                </div>
              </CardContent>
            </Card>

            <Card
              className={cn(
                'cursor-pointer transition-all',
                !createBackup
                  ? 'border-warning ring-2 ring-warning'
                  : 'hover:border-muted-foreground'
              )}
              onClick={() => setCreateBackup(false)}
            >
              <CardContent className="p-4">
                <div className="flex items-center gap-3">
                  <div
                    className={cn(
                      'w-4 h-4 rounded-full border-2',
                      !createBackup
                        ? 'border-warning bg-warning'
                        : 'border-muted-foreground'
                    )}
                  >
                    {!createBackup && (
                      <Check className="h-3 w-3 text-warning-foreground" />
                    )}
                  </div>
                  <div>
                    <h4 className="font-medium">Skip backup</h4>
                    <p className="text-sm text-warning">
                      You won't be able to undo these changes
                    </p>
                  </div>
                </div>
              </CardContent>
            </Card>
          </div>
        )}

        {/* Step 3: Applying */}
        {wizardStep === 3 && !applyComplete && (
          <div className="space-y-6 text-center py-12">
            <h2 className="text-xl font-semibold">
              {applying ? `Applying ${selectedProfile?.name}` : 'Ready to Apply'}
            </h2>

            {applying ? (
              <>
                <Progress value={applyProgress} className="w-full max-w-md mx-auto" />
                <div className="space-y-2 text-sm text-muted-foreground">
                  <div className="flex items-center justify-center gap-2">
                    {applyProgress >= 17 ? (
                      <Check className="h-4 w-4 text-success" />
                    ) : (
                      <Loader2 className="h-4 w-4 animate-spin" />
                    )}
                    Backup created
                  </div>
                  <div className="flex items-center justify-center gap-2">
                    {applyProgress >= 34 ? (
                      <Check className="h-4 w-4 text-success" />
                    ) : applyProgress >= 17 ? (
                      <Loader2 className="h-4 w-4 animate-spin" />
                    ) : (
                      <div className="h-4 w-4" />
                    )}
                    Windows settings applied
                  </div>
                  <div className="flex items-center justify-center gap-2">
                    {applyProgress >= 51 ? (
                      <Check className="h-4 w-4 text-success" />
                    ) : applyProgress >= 34 ? (
                      <Loader2 className="h-4 w-4 animate-spin" />
                    ) : (
                      <div className="h-4 w-4" />
                    )}
                    Nvidia settings applied
                  </div>
                  <div className="flex items-center justify-center gap-2">
                    {applyProgress >= 100 ? (
                      <Check className="h-4 w-4 text-success" />
                    ) : applyProgress >= 51 ? (
                      <Loader2 className="h-4 w-4 animate-spin" />
                    ) : (
                      <div className="h-4 w-4" />
                    )}
                    Remaining settings
                  </div>
                </div>
              </>
            ) : (
              <p className="text-muted-foreground">
                Click Apply to optimize your system for {selectedProfile?.name}
              </p>
            )}
          </div>
        )}

        {/* Step 3: Complete */}
        {wizardStep === 3 && applyComplete && (
          <div className="space-y-6 text-center py-8">
            <div className="flex justify-center">
              <div className="rounded-full bg-success/10 p-4">
                <Check className="h-12 w-12 text-success" />
              </div>
            </div>
            <h2 className="text-2xl font-semibold">Success!</h2>
            <p className="text-muted-foreground">
              {selectedProfile?.name} profile has been applied.
            </p>

            <Card className="text-left">
              <CardContent className="p-4">
                <h4 className="font-medium mb-3">In-Game Settings</h4>
                <p className="text-sm text-muted-foreground mb-3">
                  For best results, also configure these in-game:
                </p>
                <ul className="text-sm space-y-1">
                  <li>• <strong>Graphics Backend</strong>: Vulkan</li>
                  <li>• <strong>VSync</strong>: OFF</li>
                  <li>• <strong>Fullscreen</strong>: Exclusive</li>
                  <li>• <strong>Internal Resolution</strong>: Native</li>
                </ul>
                <div className="flex gap-2 mt-4">
                  <Button variant="outline" size="sm">
                    <Copy className="h-4 w-4 mr-2" />
                    Copy to Clipboard
                  </Button>
                  <Button variant="outline" size="sm">
                    View Full Report
                  </Button>
                </div>
              </CardContent>
            </Card>

            <div className="flex justify-center gap-4 pt-4">
              <Button variant="outline" onClick={handleDone}>
                <Undo2 className="h-4 w-4 mr-2" />
                Undo (Restore)
              </Button>
              <Button onClick={handleDone}>Done (Go Home)</Button>
            </div>
          </div>
        )}

        {/* Navigation buttons */}
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
                Apply
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

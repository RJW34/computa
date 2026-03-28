import { Header } from '@/components/Header';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { ArrowRight, ShieldAlert } from 'lucide-react';
import { useAppStore } from '@/stores/appStore';

// Simple settings shown by default
const SIMPLE_SETTINGS = [
  {
    category: 'Windows',
    settings: [
      {
        id: 'game_mode',
        label: 'Game Mode',
        description: 'Prioritizes gaming, reduces background activity',
        default: true,
      },
      {
        id: 'game_bar',
        label: 'Game Bar',
        description: 'Xbox Game Bar overlay (adds overhead)',
        default: false,
      },
      {
        id: 'hags',
        label: 'HAGS',
        description: 'Hardware-Accelerated GPU Scheduling',
        default: true,
      },
    ],
  },
  {
    category: 'Power',
    settings: [
      {
        id: 'ultimate_performance',
        label: 'Ultimate Performance',
        description: 'Maximum CPU/GPU performance power plan',
        default: true,
      },
    ],
  },
];

// Additional advanced settings (Windows settings merged into SIMPLE_SETTINGS when advanced)
const ADVANCED_SETTINGS = [
  {
    category: 'Windows (Advanced)',
    settings: [
      {
        id: 'game_dvr',
        label: 'Game DVR',
        description: 'Background recording (significant overhead)',
        default: false,
      },
      {
        id: 'vbs',
        label: 'VBS / Memory Integrity',
        description: 'Security feature with ~5% performance cost',
        default: false,
      },
      {
        id: 'fso',
        label: 'Fullscreen Optimizations',
        description: 'Windows compositor in fullscreen (adds latency)',
        default: false,
      },
      {
        id: 'mpo',
        label: 'Multi-Plane Overlay',
        description: 'Can cause stutter in some games',
        default: false,
      },
    ],
  },
  {
    category: 'Mouse',
    settings: [
      {
        id: 'mouse_accel',
        label: 'Mouse Acceleration',
        description: 'Enhanced Pointer Precision (disable for 1:1)',
        default: false,
      },
    ],
  },
  {
    category: 'Network',
    settings: [
      {
        id: 'nagle',
        label: "Nagle's Algorithm",
        description: 'Batches network packets (adds latency)',
        default: false,
      },
      {
        id: 'tcp_autotuning',
        label: 'TCP Auto-Tuning',
        description: 'Dynamic receive window (disable for consistency)',
        default: false,
      },
    ],
  },
];

export function SettingsEditor() {
  const { settingsMode, setSettingsMode, setPage } = useAppStore();

  const allSettings =
    settingsMode === 'advanced'
      ? [...SIMPLE_SETTINGS, ...ADVANCED_SETTINGS]
      : SIMPLE_SETTINGS;

  return (
    <div className="min-h-screen">
      <Header showBack title="Settings" />

      <main className="container mx-auto px-6 py-6 max-w-3xl">
        <Card className="mb-6 border-warning/40 bg-warning/5">
          <CardContent className="pt-6">
            <div className="flex gap-3">
              <ShieldAlert className="h-5 w-5 text-warning flex-shrink-0 mt-0.5" />
              <div className="space-y-3">
                <div>
                  <p className="font-medium">Direct per-setting apply is intentionally disabled.</p>
                  <p className="text-sm text-muted-foreground">
                    This page now shows the targets ABSO profiles aim for. We only apply settings
                    through the profile pipeline so backup, validation, and rollback stay honest.
                  </p>
                </div>
                <div className="flex flex-wrap gap-2">
                  <Button onClick={() => setPage('profile-wizard')}>
                    Apply a Profile
                    <ArrowRight className="h-4 w-4 ml-2" />
                  </Button>
                  <Button variant="outline" onClick={() => setPage('audit')}>
                    Run Audit
                  </Button>
                </div>
              </div>
            </div>
          </CardContent>
        </Card>

        <div className="flex items-center justify-between mb-6">
          <Tabs
            value={settingsMode}
            onValueChange={(v) => setSettingsMode(v as 'simple' | 'advanced')}
          >
            <TabsList>
              <TabsTrigger value="simple">Simple</TabsTrigger>
              <TabsTrigger value="advanced">Advanced</TabsTrigger>
            </TabsList>
          </Tabs>
        </div>

        <div className="space-y-6">
          {allSettings.map((category) => (
            <Card key={category.category}>
              <CardHeader className="pb-3">
                <CardTitle className="text-lg">{category.category}</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                {category.settings.map((setting) => (
                  <div
                    key={setting.id}
                    className="flex items-center justify-between"
                  >
                    <div className="flex-1 pr-4">
                      <div className="font-medium">{setting.label}</div>
                      <p className="text-sm text-muted-foreground">
                        {setting.description}
                      </p>
                    </div>
                    <div
                      className={`rounded-full px-3 py-1 text-xs font-medium ${
                        setting.default
                          ? 'bg-success/10 text-success'
                          : 'bg-muted text-muted-foreground'
                      }`}
                    >
                      Recommended: {setting.default ? 'On' : 'Off'}
                    </div>
                  </div>
                ))}
              </CardContent>
            </Card>
          ))}
        </div>
      </main>
    </div>
  );
}

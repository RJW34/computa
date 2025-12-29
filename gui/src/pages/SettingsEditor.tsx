import * as React from 'react';
import { Header } from '@/components/Header';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Switch } from '@/components/ui/switch';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { RotateCcw } from 'lucide-react';
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

// Additional advanced settings
const ADVANCED_SETTINGS = [
  {
    category: 'Windows',
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
  const { settingsMode, setSettingsMode } = useAppStore();
  const [settings, setSettings] = React.useState<Record<string, boolean>>({});
  const [hasChanges, setHasChanges] = React.useState(false);

  // Initialize settings with defaults
  React.useEffect(() => {
    const defaults: Record<string, boolean> = {};
    [...SIMPLE_SETTINGS, ...ADVANCED_SETTINGS].forEach((category) => {
      category.settings.forEach((setting) => {
        defaults[setting.id] = setting.default;
      });
    });
    setSettings(defaults);
  }, []);

  const handleToggle = (id: string, value: boolean) => {
    setSettings((prev) => ({ ...prev, [id]: value }));
    setHasChanges(true);
  };

  const handleApply = () => {
    // Would call API to apply settings
    setHasChanges(false);
  };

  const handleReset = () => {
    const defaults: Record<string, boolean> = {};
    [...SIMPLE_SETTINGS, ...ADVANCED_SETTINGS].forEach((category) => {
      category.settings.forEach((setting) => {
        defaults[setting.id] = setting.default;
      });
    });
    setSettings(defaults);
    setHasChanges(false);
  };

  const allSettings =
    settingsMode === 'advanced'
      ? [...SIMPLE_SETTINGS, ...ADVANCED_SETTINGS]
      : SIMPLE_SETTINGS;

  return (
    <div className="min-h-screen">
      <Header showBack title="Settings" />

      <main className="container mx-auto px-6 py-6 max-w-3xl">
        {/* Mode toggle */}
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

          <Button variant="outline" size="sm" onClick={handleReset}>
            <RotateCcw className="h-4 w-4 mr-2" />
            Reset All
          </Button>
        </div>

        {/* Settings groups */}
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
                      <label
                        htmlFor={setting.id}
                        className="font-medium cursor-pointer"
                      >
                        {setting.label}
                      </label>
                      <p className="text-sm text-muted-foreground">
                        {setting.description}
                      </p>
                    </div>
                    <Switch
                      id={setting.id}
                      checked={settings[setting.id] ?? setting.default}
                      onCheckedChange={(checked) =>
                        handleToggle(setting.id, checked)
                      }
                    />
                  </div>
                ))}
              </CardContent>
            </Card>
          ))}
        </div>

        {/* Apply button */}
        {hasChanges && (
          <div className="fixed bottom-20 left-0 right-0 p-4 bg-background border-t">
            <div className="container mx-auto max-w-3xl flex justify-end">
              <Button onClick={handleApply}>Apply Changes</Button>
            </div>
          </div>
        )}
      </main>
    </div>
  );
}

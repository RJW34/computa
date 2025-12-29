import * as React from 'react';
import { Header } from '@/components/Header';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Copy, FileDown, Gamepad2 } from 'lucide-react';

const PROFILES = [
  { id: 'slippi-melee', name: 'Slippi Melee' },
  { id: 'rivals2', name: 'Rivals 2' },
  { id: 'cod-bo7', name: 'CoD BO7' },
];

const SAMPLE_REPORT = `## Graphics

- **Backend**: Vulkan (lower latency than OpenGL)
- **VSync**: OFF
- **Fullscreen**: Exclusive
- **Internal Resolution**: Native

## Audio

- **Backend**: Cubeb (lowest latency)
- **Latency**: Lowest stable setting

## Controller

- **Adapter Mode**: Wii U / GameCube Adapter
- **Background Input**: ON

## Display Notes

Even without VRR, higher refresh rate monitors reduce scanout latency.
At 144Hz vs 60Hz, you save ~10ms of display latency.
`;

export function Reports() {
  const [selectedProfile, setSelectedProfile] = React.useState(PROFILES[0].id);

  const handleCopy = () => {
    navigator.clipboard.writeText(SAMPLE_REPORT);
  };

  return (
    <div className="min-h-screen">
      <Header showBack title="Reports" />

      <main className="container mx-auto px-6 py-6 max-w-3xl">
        <p className="text-muted-foreground mb-4">
          Select a game to view recommended in-game settings:
        </p>

        {/* Profile selector */}
        <div className="flex gap-2 mb-6">
          {PROFILES.map((profile) => (
            <Button
              key={profile.id}
              variant={selectedProfile === profile.id ? 'default' : 'outline'}
              onClick={() => setSelectedProfile(profile.id)}
            >
              {profile.name}
            </Button>
          ))}
        </div>

        {/* Report content */}
        <Card>
          <CardContent className="pt-6">
            <div className="flex items-center justify-between mb-4">
              <h3 className="font-semibold text-lg flex items-center gap-2">
                <Gamepad2 className="h-5 w-5" />
                {PROFILES.find((p) => p.id === selectedProfile)?.name} - In-Game
                Settings
              </h3>
            </div>

            <div className="prose prose-sm dark:prose-invert max-w-none">
              <div className="bg-muted p-4 rounded-md font-mono text-sm whitespace-pre-wrap">
                {SAMPLE_REPORT}
              </div>
            </div>

            <div className="flex gap-2 mt-4">
              <Button variant="outline" onClick={handleCopy}>
                <Copy className="h-4 w-4 mr-2" />
                Copy to Clipboard
              </Button>
              <Button variant="outline">
                <FileDown className="h-4 w-4 mr-2" />
                Export as PDF
              </Button>
            </div>
          </CardContent>
        </Card>
      </main>
    </div>
  );
}

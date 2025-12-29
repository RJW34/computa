import * as React from 'react';
import { Header } from '@/components/Header';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Slider } from '@/components/ui/slider';
import { Switch } from '@/components/ui/switch';
import { Info } from 'lucide-react';

export function TimerResolution() {
  const [resolution, setResolution] = React.useState(0.5);
  const [keepAlive, setKeepAlive] = React.useState(false);
  const [currentResolution] = React.useState(15.625);

  const handleApply = () => {
    // Would call api.setTimerResolution(resolution, keepAlive)
  };

  return (
    <div className="min-h-screen">
      <Header showBack title="Timer Resolution" />

      <main className="container mx-auto px-6 py-6 max-w-2xl">
        <Card className="mb-6">
          <CardContent className="pt-6">
            <p className="text-sm text-muted-foreground mb-2">
              Current Resolution:
            </p>
            <p className="text-2xl font-bold">{currentResolution} ms</p>
            <p className="text-sm text-muted-foreground">(default)</p>
          </CardContent>
        </Card>

        <Card className="mb-6">
          <CardContent className="pt-6 pb-8">
            <div className="space-y-6">
              <div>
                <div className="flex justify-between mb-4">
                  <span className="text-sm text-muted-foreground">
                    0.5ms (Gaming)
                  </span>
                  <span className="text-sm text-muted-foreground">
                    15.625ms (Default)
                  </span>
                </div>
                <Slider
                  value={[resolution]}
                  onValueChange={([value]) => setResolution(value)}
                  min={0.5}
                  max={15.625}
                  step={0.5}
                  className="mb-4"
                />
                <p className="text-center font-medium">
                  Selected: {resolution} ms
                </p>
              </div>
            </div>
          </CardContent>
        </Card>

        <Card className="mb-6 border-info/50 bg-info/5">
          <CardContent className="pt-6">
            <div className="flex gap-3">
              <Info className="h-5 w-5 text-info flex-shrink-0 mt-0.5" />
              <div className="text-sm">
                <h4 className="font-medium mb-2">What is timer resolution?</h4>
                <p className="text-muted-foreground mb-2">
                  Timer resolution affects system scheduling granularity. Lower
                  values (0.5ms) improve frame pacing consistency and thread
                  wake precision.
                </p>
                <p className="text-warning font-medium">
                  Note: This does NOT directly reduce input latency. For input
                  latency, use Nvidia Reflex or frame queue management.
                </p>
              </div>
            </div>
          </CardContent>
        </Card>

        <Card className="mb-6">
          <CardContent className="pt-6">
            <div className="flex items-center justify-between">
              <div>
                <label htmlFor="keep-alive" className="font-medium">
                  Keep resolution while A.B.S.O. is running
                </label>
                <p className="text-sm text-muted-foreground">
                  Timer resolution resets when the process that set it exits
                </p>
              </div>
              <Switch
                id="keep-alive"
                checked={keepAlive}
                onCheckedChange={setKeepAlive}
              />
            </div>
          </CardContent>
        </Card>

        <div className="flex justify-end">
          <Button onClick={handleApply}>Apply</Button>
        </div>
      </main>
    </div>
  );
}

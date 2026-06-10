import * as React from 'react';
import { Header } from '@/components/Header';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Info, Loader2, RefreshCcw } from 'lucide-react';
import * as api from '@/lib/api';

export function TimerResolution() {
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);
  const [timerInfo, setTimerInfo] = React.useState<{
    current: number;
    minimum: number;
    maximum: number;
  } | null>(null);

  const loadStatus = React.useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const status = await api.getTimerResolution();
      setTimerInfo(status);
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : 'Failed to query timer resolution');
      setTimerInfo(null);
    } finally {
      setLoading(false);
    }
  }, []);

  React.useEffect(() => {
    void loadStatus();
  }, [loadStatus]);

  return (
    <div className="min-h-screen">
      <Header showBack title="Timer Resolution" />

      <main className="container mx-auto max-w-3xl px-6 py-6">
        <Card className="wizard-panel mb-6 shadow-none">
          <CardContent className="pt-6">
            {loading ? (
              <div className="flex items-center gap-2 text-muted-foreground">
                <Loader2 className="h-4 w-4 animate-spin" />
                <span>Reading current timer state...</span>
              </div>
            ) : error ? (
              <div className="text-sm text-destructive">
                Failed to read timer status: {error}
              </div>
            ) : timerInfo ? (
              <div className="space-y-3">
                <div>
                  <p className="text-sm text-muted-foreground mb-2">Current Resolution</p>
                  <p className="text-2xl font-bold">{timerInfo.current} ms</p>
                </div>
                <div className="grid grid-cols-2 gap-4 text-sm text-muted-foreground">
                  <div>
                    <p className="font-medium text-foreground">Fastest Supported</p>
                    <p>{timerInfo.minimum} ms</p>
                  </div>
                  <div>
                    <p className="font-medium text-foreground">Default / Highest</p>
                    <p>{timerInfo.maximum} ms</p>
                  </div>
                </div>
              </div>
            ) : null}
          </CardContent>
        </Card>

        <Card className="wizard-panel mb-6 border-info/50 bg-info/5 shadow-none">
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
                <p className="text-muted-foreground mt-2">
                  Read-only here. A one-shot request would revert as soon as the command exits,
                  so no Apply control is exposed until a persistent timer service exists.
                </p>
              </div>
            </div>
          </CardContent>
        </Card>

        <div className="flex justify-end">
          <Button variant="outline" onClick={() => void loadStatus()} disabled={loading}>
            <RefreshCcw className="h-4 w-4 mr-2" />
            Refresh Status
          </Button>
        </div>
      </main>
    </div>
  );
}

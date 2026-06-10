import * as React from 'react';
import { Card, CardContent } from '@/components/ui/card';
import { Cpu, Loader2, Monitor, RefreshCw, AlertCircle } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { useAppStore } from '@/stores/appStore';
import { formatHardwareSummary } from '@/lib/utils';

export function HardwareSummary() {
  const { hardware, hardwareLoading, hardwareError, detectHardware } =
    useAppStore();

  // Track in-flight request to prevent race conditions
  const isDetecting = React.useRef(false);

  React.useEffect(() => {
    if (!hardware && !hardwareLoading && !isDetecting.current) {
      isDetecting.current = true;
      detectHardware().finally(() => {
        isDetecting.current = false;
      });
    }
  }, [hardware, hardwareLoading, detectHardware]);

  if (hardwareLoading) {
    return (
      <Card className="hardware-panel mb-6 shadow-none">
        <CardContent className="flex items-center justify-center py-4">
          <Loader2 className="h-5 w-5 animate-spin mr-2" />
          <span className="text-muted-foreground">Detecting hardware...</span>
        </CardContent>
      </Card>
    );
  }

  if (hardwareError) {
    return (
      <Card className="hardware-panel mb-6 border-destructive/40 bg-destructive/5 shadow-none">
        <CardContent className="flex items-center justify-between py-4">
          <div className="flex items-center">
            <AlertCircle className="h-5 w-5 text-destructive mr-2" />
            <span className="text-destructive">Failed to detect hardware</span>
          </div>
          <Button variant="outline" size="sm" onClick={() => detectHardware()}>
            <RefreshCw className="h-4 w-4 mr-2" />
            Retry
          </Button>
        </CardContent>
      </Card>
    );
  }

  if (!hardware) {
    return null;
  }

  return (
      <Card className="hardware-panel mb-6 shadow-none">
      <CardContent className="flex items-center justify-between gap-4 py-4">
        <div className="flex min-w-0 items-center gap-3">
          <div className="control-tile__icon h-10 w-10">
            <Cpu className="h-5 w-5" />
          </div>
          <div className="min-w-0">
            <p className="text-xs font-bold uppercase text-primary">Detected rig</p>
            <span className="block truncate text-sm font-medium">
              {formatHardwareSummary(hardware)}
            </span>
          </div>
        </div>
        <div className="hidden min-w-0 items-center gap-2 text-xs text-muted-foreground md:flex">
          <Monitor className="h-4 w-4 text-primary" />
          <span className="truncate">{hardware.monitors.length} display path(s)</span>
        </div>
        <Button
          variant="ghost"
          size="sm"
          onClick={() => detectHardware()}
          className="h-8 w-8 p-0"
        >
          <RefreshCw className="h-4 w-4" />
        </Button>
      </CardContent>
    </Card>
  );
}

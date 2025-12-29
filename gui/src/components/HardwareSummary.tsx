import * as React from 'react';
import { Card, CardContent } from '@/components/ui/card';
import { Loader2, RefreshCw, AlertCircle } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { useAppStore } from '@/stores/appStore';
import { formatHardwareSummary } from '@/lib/utils';

export function HardwareSummary() {
  const { hardware, hardwareLoading, hardwareError, detectHardware } =
    useAppStore();

  React.useEffect(() => {
    if (!hardware && !hardwareLoading) {
      detectHardware();
    }
  }, [hardware, hardwareLoading, detectHardware]);

  if (hardwareLoading) {
    return (
      <Card className="mb-6">
        <CardContent className="flex items-center justify-center py-4">
          <Loader2 className="h-5 w-5 animate-spin mr-2" />
          <span className="text-muted-foreground">Detecting hardware...</span>
        </CardContent>
      </Card>
    );
  }

  if (hardwareError) {
    return (
      <Card className="mb-6 border-destructive">
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
    <Card className="mb-6">
      <CardContent className="flex items-center justify-between py-4">
        <span className="text-sm font-medium">
          {formatHardwareSummary(hardware)}
        </span>
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

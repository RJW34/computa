import { formatManualStep, getPendingManualSteps } from '@/lib/profileState';
import type { ManualSetupStep } from '@/lib/types';

export function ManualSetupList({ steps }: { steps?: ManualSetupStep[] }) {
  const pending = getPendingManualSteps(steps);
  if (pending.length === 0) return null;

  return (
    <div className="space-y-2 text-left">
      <h4 className="font-medium text-warning">Manual setup needed</h4>
      <p className="text-sm text-muted-foreground">
        Complete these settings manually, then verify the profile again.
      </p>
      <ul className="space-y-2 text-sm">
        {pending.map((step, index) => (
          <li key={`${step.handler ?? ''}:${step.key ?? ''}:${index}`}>
            <p>{formatManualStep(step)}</p>
            {step.instruction && (
              <p className="text-muted-foreground">{step.instruction}</p>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}

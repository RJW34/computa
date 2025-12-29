import * as React from 'react';
import { Card, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { cn } from '@/lib/utils';
import type { LucideIcon } from 'lucide-react';

interface ActionCardProps {
  icon: LucideIcon;
  title: string;
  subtitle: string;
  badge?: {
    count: number;
    variant: 'critical' | 'warning' | 'info' | 'success' | 'default';
  };
  onClick: () => void;
  disabled?: boolean;
}

export function ActionCard({
  icon: Icon,
  title,
  subtitle,
  badge,
  onClick,
  disabled,
}: ActionCardProps) {
  return (
    <Card
      className={cn(
        'cursor-pointer transition-all hover:shadow-md hover:border-primary/50',
        disabled && 'opacity-50 cursor-not-allowed hover:shadow-sm hover:border-border'
      )}
      onClick={disabled ? undefined : onClick}
    >
      <CardContent className="flex flex-col items-center justify-center p-6 text-center min-h-[140px] relative">
        {badge && badge.count > 0 && (
          <Badge
            variant={badge.variant}
            className="absolute top-3 right-3"
          >
            {badge.count}
          </Badge>
        )}
        <Icon className="h-10 w-10 mb-3 text-muted-foreground" />
        <h3 className="font-semibold text-lg">{title}</h3>
        <p className="text-sm text-muted-foreground mt-1">{subtitle}</p>
      </CardContent>
    </Card>
  );
}

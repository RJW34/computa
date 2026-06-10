import { Card, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { cn } from '@/lib/utils';
import { ArrowUpRight, type LucideIcon } from 'lucide-react';

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
        'control-tile cursor-pointer shadow-none',
        disabled && 'opacity-50 cursor-not-allowed'
      )}
      onClick={disabled ? undefined : onClick}
    >
      <CardContent className="relative flex min-h-[140px] flex-col justify-between p-5">
        {badge && badge.count > 0 && (
          <Badge
            variant={badge.variant}
            className="absolute top-3 right-3"
          >
            {badge.count}
          </Badge>
        )}
        <div className="control-tile__icon">
          <Icon className="h-5 w-5" />
        </div>
        <div className="space-y-1">
          <div className="flex items-center justify-between gap-3">
            <h3 className="text-base font-bold">{title}</h3>
            <ArrowUpRight className="h-4 w-4 text-muted-foreground" />
          </div>
          <p className="line-clamp-2 text-sm text-muted-foreground">{subtitle}</p>
        </div>
      </CardContent>
    </Card>
  );
}

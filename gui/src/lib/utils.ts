import { type ClassValue, clsx } from 'clsx';
import { twMerge } from 'tailwind-merge';

/**
 * Merge Tailwind classes with clsx
 */
export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

/**
 * Format a timestamp to a human-readable string
 */
export function formatTimestamp(timestamp: string): string {
  const date = new Date(timestamp);
  return date.toLocaleString(undefined, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

/**
 * Format relative time (e.g., "2 hours ago")
 */
export function formatRelativeTime(timestamp: string): string {
  const date = new Date(timestamp);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMins = Math.floor(diffMs / 60000);
  const diffHours = Math.floor(diffMins / 60);
  const diffDays = Math.floor(diffHours / 24);

  if (diffMins < 1) return 'just now';
  if (diffMins < 60) return `${diffMins} minute${diffMins === 1 ? '' : 's'} ago`;
  if (diffHours < 24) return `${diffHours} hour${diffHours === 1 ? '' : 's'} ago`;
  if (diffDays < 7) return `${diffDays} day${diffDays === 1 ? '' : 's'} ago`;
  return formatTimestamp(timestamp);
}

/**
 * Get severity color classes
 */
export function getSeverityClasses(severity: 'critical' | 'warning' | 'info') {
  switch (severity) {
    case 'critical':
      return 'bg-critical text-critical-foreground';
    case 'warning':
      return 'bg-warning text-warning-foreground';
    case 'info':
      return 'bg-info text-info-foreground';
  }
}

/**
 * Get severity icon
 */
export function getSeverityIcon(severity: 'critical' | 'warning' | 'info') {
  switch (severity) {
    case 'critical':
      return 'AlertCircle';
    case 'warning':
      return 'AlertTriangle';
    case 'info':
      return 'Info';
  }
}

/**
 * Format hardware summary line
 * Shows: GPU @ RefreshHz · CPU · RAM · VRR type (if available)
 */
export function formatHardwareSummary(hardware: {
  gpu: { name: string };
  cpu: { name: string };
  ram_gb: number;
  monitors: { refresh_rate: number; vrr_type: string | null; is_primary?: boolean }[];
}): string {
  const gpuShort = hardware.gpu.name
    .replace('NVIDIA GeForce ', '')
    .replace('AMD Radeon ', '');
  const cpuShort = hardware.cpu.name
    .replace('Intel(R) Core(TM) ', '')
    .replace('AMD Ryzen ', 'Ryzen ')
    .replace(' Processor', '')
    .split('@')[0]
    .trim();

  // Use the PRIMARY monitor for Hz display (not just first in list)
  const primaryMonitor = hardware.monitors.find((m: { is_primary?: boolean }) => m.is_primary) || hardware.monitors[0];
  const refreshHz = primaryMonitor?.refresh_rate ? `@ ${primaryMonitor.refresh_rate}Hz` : '';
  const vrrType = primaryMonitor?.vrr_type || '';

  // Format: GPU @ Hz · CPU · RAM · VRR
  let summary = `${gpuShort} ${refreshHz} · ${cpuShort} · ${hardware.ram_gb}GB`;
  if (vrrType) {
    summary += ` · ${vrrType}`;
  }

  return summary;
}

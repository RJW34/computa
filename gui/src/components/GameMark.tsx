import * as React from 'react';
import { Monitor, Sparkles } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { Profile } from '@/lib/types';

export interface GameArt {
  key: string;
  name: string;
  shortName: string;
  mark: string;
  eyebrow: string;
  accent: string;
  accent2: string;
  ink: string;
  surface: string;
}

const DEFAULT_ART: GameArt = {
  key: 'default',
  name: 'ABSO',
  shortName: 'ABSO',
  mark: 'A',
  eyebrow: 'PROFILE',
  accent: '#7dd3fc',
  accent2: '#f59e0b',
  ink: '#f8fafc',
  surface: '#0f172a',
};

const GAME_ART: Record<string, GameArt> = {
  productivity: {
    key: 'productivity',
    name: 'Desktop / Productivity',
    shortName: 'Desktop',
    mark: 'DX',
    eyebrow: 'WORKSTATION',
    accent: '#2dd4bf',
    accent2: '#facc15',
    ink: '#ecfeff',
    surface: '#0f1f1d',
  },
  'slippi-melee': {
    key: 'slippi-melee',
    name: 'Super Smash Bros. Melee (Slippi)',
    shortName: 'Slippi',
    mark: 'SLP',
    eyebrow: 'MELEE',
    accent: '#67e8f9',
    accent2: '#fde047',
    ink: '#ecfeff',
    surface: '#121a26',
  },
  rivals2: {
    key: 'rivals2',
    name: 'Rivals 2',
    shortName: 'Rivals',
    mark: 'R2',
    eyebrow: 'ARENA',
    accent: '#fb923c',
    accent2: '#22d3ee',
    ink: '#fff7ed',
    surface: '#21150f',
  },
  diablo4: {
    key: 'diablo4',
    name: 'Diablo 4',
    shortName: 'Diablo IV',
    mark: 'D4',
    eyebrow: 'SANCTUARY',
    accent: '#ef4444',
    accent2: '#f59e0b',
    ink: '#fee2e2',
    surface: '#1f0d0d',
  },
  fortnite: {
    key: 'fortnite',
    name: 'Fortnite',
    shortName: 'Fortnite',
    mark: 'FN',
    eyebrow: 'BR',
    accent: '#38bdf8',
    accent2: '#f472b6',
    ink: '#eff6ff',
    surface: '#10172f',
  },
  'marvel-rivals': {
    key: 'marvel-rivals',
    name: 'Marvel Rivals',
    shortName: 'Marvel',
    mark: 'MR',
    eyebrow: 'TEAMFIGHT',
    accent: '#facc15',
    accent2: '#ef4444',
    ink: '#fffbeb',
    surface: '#1f1608',
  },
  deadlock: {
    key: 'deadlock',
    name: 'Deadlock',
    shortName: 'Deadlock',
    mark: 'DL',
    eyebrow: 'LANE',
    accent: '#f59e0b',
    accent2: '#14b8a6',
    ink: '#fff7ed',
    surface: '#201a0c',
  },
  overwatch2: {
    key: 'overwatch2',
    name: 'Overwatch 2',
    shortName: 'Overwatch',
    mark: 'OW2',
    eyebrow: 'HERO FPS',
    accent: '#fb923c',
    accent2: '#60a5fa',
    ink: '#fff7ed',
    surface: '#1c1722',
  },
  'pokemon-auto-chess': {
    key: 'pokemon-auto-chess',
    name: 'Pokemon Auto Chess',
    shortName: 'Auto Chess',
    mark: 'PAC',
    eyebrow: 'WEBGL',
    accent: '#facc15',
    accent2: '#3b82f6',
    ink: '#fffbeb',
    surface: '#172033',
  },
  pacdeluxe: {
    key: 'pacdeluxe',
    name: 'PACDeluxe (Pokemon Auto Chess)',
    shortName: 'PACDeluxe',
    mark: 'PDX',
    eyebrow: 'TAURI',
    accent: '#a7f3d0',
    accent2: '#60a5fa',
    ink: '#f0fdf4',
    surface: '#10211a',
  },
  'ryujinx-ssbu': {
    key: 'ryujinx-ssbu',
    name: 'SSBU / HewDraw Remix (Ryujinx)',
    shortName: 'SSBU',
    mark: 'SSB',
    eyebrow: 'EMU',
    accent: '#c084fc',
    accent2: '#f97316',
    ink: '#faf5ff',
    surface: '#191124',
  },
};

export function getGameKeyFromProfile(profile?: Pick<Profile, 'id' | 'tray_group'> | null): string {
  const id = profile?.tray_group || profile?.id || '';

  if (id.startsWith('slippi-melee')) return 'slippi-melee';
  if (id.startsWith('rivals2')) return 'rivals2';
  if (id.startsWith('diablo4')) return 'diablo4';
  if (id.startsWith('fortnite')) return 'fortnite';
  if (id.startsWith('marvel-rivals')) return 'marvel-rivals';
  if (id.startsWith('deadlock')) return 'deadlock';
  if (id.startsWith('overwatch2')) return 'overwatch2';
  if (id.startsWith('pokemon-auto-chess')) return 'pokemon-auto-chess';
  if (id.startsWith('pacdeluxe')) return 'pacdeluxe';
  if (id.startsWith('productivity')) return 'productivity';
  if (id.startsWith('ryujinx-ssbu')) return 'ryujinx-ssbu';

  return id || 'default';
}

export function getGameArt(profile?: Pick<Profile, 'id' | 'tray_group'> | null): GameArt {
  const key = getGameKeyFromProfile(profile);
  return GAME_ART[key] || DEFAULT_ART;
}

export function getGameArtByKey(key?: string | null): GameArt {
  if (!key) return DEFAULT_ART;
  return GAME_ART[getGameKeyFromProfile({ id: key })] || DEFAULT_ART;
}

export function gameArtVars(art: GameArt): React.CSSProperties {
  return {
    '--game-a': art.accent,
    '--game-b': art.accent2,
    '--game-ink': art.ink,
    '--game-surface': art.surface,
  } as React.CSSProperties;
}

interface GameMarkProps {
  profile?: Pick<Profile, 'id' | 'tray_group'> | null;
  groupId?: string;
  size?: 'sm' | 'md' | 'lg' | 'hero';
  active?: boolean;
  showName?: boolean;
  className?: string;
}

export function GameMark({
  profile,
  groupId,
  size = 'md',
  active,
  showName,
  className,
}: GameMarkProps) {
  const art = groupId ? getGameArtByKey(groupId) : getGameArt(profile);
  const isDesktop = art.key === 'productivity';

  return (
    <div
      className={cn(
        'game-mark',
        `game-mark--${size}`,
        active && 'game-mark--active',
        showName && 'game-mark--labeled',
        className
      )}
      style={gameArtVars(art)}
      aria-label={`${art.name} stylized mark`}
    >
      <div className="game-mark__plate" aria-hidden="true">
        <div className="game-mark__scan" />
        <div className="game-mark__ring" />
        <div className="game-mark__letters">
          {isDesktop ? <Monitor className="h-[0.9em] w-[0.9em]" /> : art.mark}
        </div>
        <Sparkles className="game-mark__spark" />
      </div>
      {showName && (
        <div className="min-w-0">
          <div className="game-mark__eyebrow">{art.eyebrow}</div>
          <div className="game-mark__name">{art.shortName}</div>
        </div>
      )}
    </div>
  );
}

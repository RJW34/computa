import {
  Archive,
  ArrowLeft,
  FileText,
  Gamepad2,
  Home,
  Moon,
  Search,
  Settings,
  Sun,
  Timer,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { useAppStore } from '@/stores/appStore';
import type { Page, Theme } from '@/lib/types';
import { cn } from '@/lib/utils';

interface HeaderProps {
  showBack?: boolean;
  title?: string;
}

export function Header({ showBack, title }: HeaderProps) {
  const { currentPage, theme, setTheme, setPage } = useAppStore();

  const cycleTheme = () => {
    const themes: Theme[] = ['light', 'dark', 'system'];
    const currentIndex = themes.indexOf(theme);
    const nextTheme = themes[(currentIndex + 1) % themes.length];
    setTheme(nextTheme);
  };

  const navItems: Array<{ page: Page; label: string; icon: typeof Home }> = [
    { page: 'home', label: 'Home', icon: Home },
    { page: 'profile-wizard', label: 'Profiles', icon: Gamepad2 },
    { page: 'audit', label: 'Audit', icon: Search },
    { page: 'backups', label: 'Backups', icon: Archive },
    { page: 'reports', label: 'Reports', icon: FileText },
    { page: 'timer', label: 'Timer', icon: Timer },
  ];

  return (
    <header className="command-header">
      <div className="container mx-auto px-6 py-3 flex items-center justify-between gap-4">
        <div className="flex items-center gap-4">
          {showBack && (
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setPage('home')}
              className="gap-2"
            >
              <ArrowLeft className="h-4 w-4" />
              <span className="hidden sm:inline">Back</span>
            </Button>
          )}
          <div className="brand-lockup">
            <div className="brand-sigil">cp</div>
            <div className="min-w-0">
              <h1 className="brand-word truncate">
                {title ? title : (
                  <>
                    computa<b>_</b>
                  </>
                )}
              </h1>
              <p className="etch truncate">per-game windows optimization</p>
            </div>
          </div>
        </div>

        <nav className="hidden xl:flex items-center gap-1.5" aria-label="Primary">
          {navItems.map(({ page, label, icon: Icon }) => (
            <button
              key={page}
              type="button"
              className={cn('nav-switch', currentPage === page && 'nav-switch--active')}
              onClick={() => setPage(page)}
            >
              <Icon className="h-3.5 w-3.5" />
              <span>{label}</span>
            </button>
          ))}
        </nav>

        <div className="flex items-center gap-2">
          <Button
            variant="ghost"
            size="icon"
            title="Settings"
            onClick={() => setPage('settings')}
            className={cn(currentPage === 'settings' && 'bg-primary/10 text-primary')}
          >
            <Settings className="h-5 w-5" />
          </Button>
          <Button
            variant="ghost"
            size="icon"
            onClick={cycleTheme}
            title={`Theme: ${theme}`}
            className="hidden sm:inline-flex"
          >
            {theme === 'dark' ? (
              <Moon className="h-5 w-5" />
            ) : theme === 'light' ? (
              <Sun className="h-5 w-5" />
            ) : (
              <div className="h-5 w-5 flex items-center justify-center">
                <Sun className="h-3 w-3 absolute" />
                <Moon className="h-3 w-3 absolute translate-x-1 translate-y-1" />
              </div>
            )}
          </Button>
        </div>
      </div>
    </header>
  );
}

import { Moon, Sun, Settings, ArrowLeft } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { useAppStore } from '@/stores/appStore';
import type { Theme } from '@/lib/types';

interface HeaderProps {
  showBack?: boolean;
  title?: string;
}

export function Header({ showBack, title }: HeaderProps) {
  const { theme, setTheme, setPage } = useAppStore();

  const cycleTheme = () => {
    const themes: Theme[] = ['light', 'dark', 'system'];
    const currentIndex = themes.indexOf(theme);
    const nextTheme = themes[(currentIndex + 1) % themes.length];
    setTheme(nextTheme);
  };

  return (
    <header className="border-b">
      <div className="container mx-auto px-6 py-4 flex items-center justify-between">
        <div className="flex items-center gap-4">
          {showBack && (
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setPage('home')}
              className="gap-2"
            >
              <ArrowLeft className="h-4 w-4" />
              Back
            </Button>
          )}
          <h1 className="text-xl font-bold">
            {title || 'A.B.S.O.'}
          </h1>
        </div>

        <div className="flex items-center gap-2">
          <Button
            variant="ghost"
            size="icon"
            onClick={cycleTheme}
            title={`Theme: ${theme}`}
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
          <Button
            variant="ghost"
            size="icon"
            title="Settings"
            onClick={() => setPage('settings')}
          >
            <Settings className="h-5 w-5" />
          </Button>
        </div>
      </div>
    </header>
  );
}

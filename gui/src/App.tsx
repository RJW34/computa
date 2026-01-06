import { useEffect } from 'react';
import { listen } from '@tauri-apps/api/event';
import { useAppStore } from '@/stores/appStore';
import { StatusBar } from '@/components/StatusBar';
import {
  Home,
  ProfileWizard,
  SettingsEditor,
  AuditDetails,
  BackupManager,
  Reports,
  TimerResolution,
} from '@/pages';

function App() {
  const { currentPage, _hasHydrated, setActiveProfile } = useAppStore();

  // Listen for profile changes from system tray
  useEffect(() => {
    const unlisten = listen<string>('profile-applied', (event) => {
      // Update the active profile in the store when applied from tray
      setActiveProfile(event.payload);
    });

    return () => {
      unlisten.then((fn) => fn());
    };
  }, [setActiveProfile]);

  // Wait for hydration to prevent flash of default state
  if (!_hasHydrated) {
    return null;
  }

  const renderPage = () => {
    switch (currentPage) {
      case 'home':
        return <Home />;
      case 'profile-wizard':
        return <ProfileWizard />;
      case 'settings':
        return <SettingsEditor />;
      case 'audit':
        return <AuditDetails />;
      case 'backups':
        return <BackupManager />;
      case 'reports':
        return <Reports />;
      case 'timer':
        return <TimerResolution />;
      default:
        return <Home />;
    }
  };

  return (
    <>
      {renderPage()}
      <StatusBar />
    </>
  );
}

export default App;

import { useEffect } from 'react';
import { listen } from '@tauri-apps/api/event';
import { useAppStore } from '@/stores/appStore';
import { StatusBar } from '@/components/StatusBar';
import * as api from '@/lib/api';
import {
  Home,
  ProfileWizard,
  SettingsEditor,
  AuditDetails,
  BackupManager,
  Reports,
  TimerResolution,
} from '@/pages';

interface ProfileAppliedEvent {
  profile_id: string;
  warnings: string[];
  notices: string[];
}

function App() {
  const { currentPage, _hasHydrated, setActiveProfile } = useAppStore();

  useEffect(() => {
    if (!_hasHydrated) {
      return;
    }

    const syncBackendState = async () => {
      try {
        const state = await api.getCurrentState();
        setActiveProfile(
          state.current_profile,
          state.applied_at ?? undefined,
          state.verification ?? null,
          state.reboot_pending,
          state.reboot_reasons
        );
      } catch (error) {
        console.warn('Failed to sync backend active-profile state:', error);
      }
    };

    void syncBackendState();

    const unlisten = listen<ProfileAppliedEvent>('profile-applied', () => {
      void syncBackendState();
    });

    return () => {
      unlisten.then((fn) => fn());
    };
  }, [_hasHydrated, setActiveProfile]);

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

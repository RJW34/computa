import { useEffect, useRef } from 'react';
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
  const {
    currentPage,
    _hasHydrated,
    setActiveProfile,
    setActiveProfileStateError,
    setActiveProfileStateLoading,
  } = useAppStore();
  const stateSyncSeq = useRef(0);

  useEffect(() => {
    if (!_hasHydrated) {
      return;
    }

    let disposed = false;
    const syncBackendState = async () => {
      const seq = ++stateSyncSeq.current;
      setActiveProfileStateLoading();
      try {
        const state = await api.getCurrentState();
        if (disposed || seq !== stateSyncSeq.current) {
          return;
        }
        setActiveProfile(
          state.current_profile,
          state.applied_at ?? undefined,
          state.verification ?? null,
          state.reboot_pending,
          state.reboot_reasons
        );
      } catch (error) {
        if (disposed || seq !== stateSyncSeq.current) {
          return;
        }
        console.warn('Failed to sync backend active-profile state:', error);
        setActiveProfileStateError(
          error instanceof Error ? error.message : 'Failed to read backend state'
        );
      }
    };

    void syncBackendState();

    let unlisten: Promise<() => void> | null = null;
    if (typeof window !== 'undefined' && '__TAURI_INTERNALS__' in window) {
      unlisten = listen<ProfileAppliedEvent>('profile-applied', () => {
        void syncBackendState();
      });
    }

    return () => {
      disposed = true;
      stateSyncSeq.current += 1;
      if (unlisten) {
        unlisten.then((fn) => fn()).catch(() => undefined);
      }
    };
  }, [_hasHydrated, setActiveProfile, setActiveProfileStateError, setActiveProfileStateLoading]);

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
    <div className="app-shell">
      {renderPage()}
      <StatusBar />
      <div className="app-grain" aria-hidden="true" />
    </div>
  );
}

export default App;

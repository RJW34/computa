import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import type {
  HardwareInfo,
  Issue,
  Profile,
  Backup,
  Page,
  Theme,
} from '@/lib/types';
import * as api from '@/lib/api';

interface AppState {
  // Hydration state
  _hasHydrated: boolean;
  setHasHydrated: (state: boolean) => void;
  // Navigation
  currentPage: Page;
  setPage: (page: Page) => void;

  // Theme
  theme: Theme;
  setTheme: (theme: Theme) => void;

  // Admin status
  isAdmin: boolean;
  checkAdmin: () => Promise<void>;

  // Hardware
  hardware: HardwareInfo | null;
  hardwareLoading: boolean;
  hardwareError: string | null;
  detectHardware: () => Promise<void>;

  // Audit
  auditResults: Issue[];
  auditLoading: boolean;
  auditError: string | null;
  auditHasRun: boolean;
  runAudit: () => Promise<void>;

  // Profiles
  profiles: Profile[];
  profilesLoading: boolean;
  loadProfiles: () => Promise<void>;

  // Active profile tracking
  activeProfile: string | null;  // Profile ID of currently applied profile
  activeProfileAppliedAt: string | null;  // ISO timestamp when profile was applied
  setActiveProfile: (profileId: string | null, appliedAt?: string) => void;

  // Backups
  backups: Backup[];
  backupsLoading: boolean;
  backupsError: string | null;
  loadBackups: () => Promise<void>;

  // Settings mode
  settingsMode: 'simple' | 'advanced';
  setSettingsMode: (mode: 'simple' | 'advanced') => void;

  // Profile wizard state
  wizardProfile: string | null;
  wizardStep: number;
  setWizardProfile: (profileId: string | null) => void;
  setWizardStep: (step: number) => void;
  resetWizard: () => void;
}

export const useAppStore = create<AppState>()(
  persist(
    (set) => ({
      // Hydration state - tracks when localStorage data has been loaded
      _hasHydrated: false,
      setHasHydrated: (state) => set({ _hasHydrated: state }),

      // Navigation
      currentPage: 'home',
      setPage: (page) => set({ currentPage: page }),

      // Theme
      theme: 'system',
      setTheme: (theme) => {
        set({ theme });
        applyTheme(theme);
      },

      // Admin status
      isAdmin: false,
      checkAdmin: async () => {
        try {
          const isAdmin = await api.isAdmin();
          set({ isAdmin });
        } catch {
          set({ isAdmin: false });
        }
      },

      // Hardware
      hardware: null,
      hardwareLoading: false,
      hardwareError: null,
      detectHardware: async () => {
        set({ hardwareLoading: true, hardwareError: null });
        try {
          const hardware = await api.detectHardware();
          set({ hardware, hardwareLoading: false });
        } catch (error) {
          set({
            hardwareError:
              error instanceof Error ? error.message : 'Detection failed',
            hardwareLoading: false,
          });
        }
      },

      // Audit
      auditResults: [],
      auditLoading: false,
      auditError: null,
      auditHasRun: false,
      runAudit: async () => {
        set({ auditLoading: true, auditError: null });
        try {
          const results = await api.runAudit();
          set({ auditResults: results, auditLoading: false, auditHasRun: true });
        } catch (error) {
          set({
            auditError: error instanceof Error ? error.message : 'Audit failed',
            auditLoading: false,
            auditHasRun: false,
          });
        }
      },

      // Profiles
      profiles: [],
      profilesLoading: false,
      loadProfiles: async () => {
        set({ profilesLoading: true });
        try {
          const profiles = await api.getProfiles();
          set({ profiles, profilesLoading: false });
        } catch {
          set({ profilesLoading: false });
        }
      },

      // Active profile tracking
      activeProfile: null,
      activeProfileAppliedAt: null,
      setActiveProfile: (profileId, appliedAt) => set({
        activeProfile: profileId,
        activeProfileAppliedAt: profileId ? (appliedAt || new Date().toISOString()) : null,
      }),

      // Backups
      backups: [],
      backupsLoading: false,
      backupsError: null as string | null,
      loadBackups: async () => {
        set({ backupsLoading: true, backupsError: null });
        try {
          const backups = await api.getBackups();
          set({ backups, backupsLoading: false });
        } catch (error) {
          console.error('Failed to load backups:', error);
          set({
            backupsLoading: false,
            backupsError: error instanceof Error ? error.message : 'Failed to load backups'
          });
        }
      },

      // Settings mode
      settingsMode: 'simple',
      setSettingsMode: (mode) => set({ settingsMode: mode }),

      // Profile wizard
      wizardProfile: null,
      wizardStep: 0,
      setWizardProfile: (profileId) => set({ wizardProfile: profileId }),
      setWizardStep: (step) => set({ wizardStep: step }),
      resetWizard: () => set({ wizardProfile: null, wizardStep: 0 }),
    }),
    {
      name: 'abso-storage',
      partialize: (state) => ({
        theme: state.theme,
        settingsMode: state.settingsMode,
        activeProfile: state.activeProfile,
        activeProfileAppliedAt: state.activeProfileAppliedAt,
      }),
      onRehydrateStorage: () => (state) => {
        state?.setHasHydrated(true);
      },
    }
  )
);

/**
 * Apply theme to document
 */
function applyTheme(theme: Theme) {
  const root = document.documentElement;
  root.classList.remove('light', 'dark');

  if (theme === 'system') {
    const systemDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
    root.classList.add(systemDark ? 'dark' : 'light');
  } else {
    root.classList.add(theme);
  }
}

// Initialize theme on load
if (typeof window !== 'undefined') {
  const stored = localStorage.getItem('abso-storage');
  if (stored) {
    try {
      const { state } = JSON.parse(stored);
      if (state?.theme) {
        applyTheme(state.theme);
      }
    } catch {
      // Ignore parse errors
    }
  }

  // Listen for system theme changes
  window
    .matchMedia('(prefers-color-scheme: dark)')
    .addEventListener('change', () => {
      const { theme } = useAppStore.getState();
      if (theme === 'system') {
        applyTheme('system');
      }
    });
}

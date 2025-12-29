import { useAppStore } from '@/stores/appStore';
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
  const { currentPage } = useAppStore();

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
}

export default App;

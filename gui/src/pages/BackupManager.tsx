import * as React from 'react';
import { Header } from '@/components/Header';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Archive, Trash2, RotateCcw, Plus, Loader2 } from 'lucide-react';
import { useAppStore } from '@/stores/appStore';
import { formatTimestamp } from '@/lib/utils';
import * as api from '@/lib/api';

export function BackupManager() {
  const { backups, backupsLoading, backupsError, loadBackups, setActiveProfile } = useAppStore();
  const [restoring, setRestoring] = React.useState<string | null>(null);
  const [creating, setCreating] = React.useState(false);
  const [deleting, setDeleting] = React.useState<string | null>(null);
  const [actionMessage, setActionMessage] = React.useState<string | null>(null);
  const [actionError, setActionError] = React.useState<string | null>(null);

  // Track if load has been triggered to prevent duplicate calls
  const loadTriggered = React.useRef(false);

  React.useEffect(() => {
    // Only load if not already loaded and not currently loading
    if (loadTriggered.current || backupsLoading) return;
    if (backups.length > 0) return; // Already have data

    loadTriggered.current = true;
    loadBackups();
  }, [backups.length, backupsLoading, loadBackups]);

  const handleRestore = async (backupId: string) => {
    setActionMessage(null);
    setActionError(null);
    setRestoring(backupId);
    try {
      await api.restoreBackup(backupId);
      setActiveProfile(null);
      await api.setActiveProfileBackend(null);
      await loadBackups();
      setActionMessage(`Restored backup ${backupId}. Active profile state was cleared.`);
    } catch (error) {
      setActionError(error instanceof Error ? error.message : 'Failed to restore backup');
    } finally {
      setRestoring(null);
    }
  };

  const handleCreateBackup = async () => {
    setActionMessage(null);
    setActionError(null);
    setCreating(true);
    try {
      const backup = await api.createBackup();
      await loadBackups();
      setActionMessage(`Created backup ${backup.id}.`);
    } catch (error) {
      setActionError(error instanceof Error ? error.message : 'Failed to create backup');
    } finally {
      setCreating(false);
    }
  };

  const handleDelete = async (backupId: string) => {
    if (!window.confirm(`Delete backup ${backupId}? This cannot be undone.`)) {
      return;
    }

    setActionMessage(null);
    setActionError(null);
    setDeleting(backupId);
    try {
      await api.deleteBackup(backupId);
      await loadBackups();
      setActionMessage(`Deleted backup ${backupId}.`);
    } catch (error) {
      setActionError(error instanceof Error ? error.message : 'Failed to delete backup');
    } finally {
      setDeleting(null);
    }
  };

  return (
    <div className="min-h-screen">
      <Header showBack title="Backups" />

      <main className="container mx-auto px-6 py-6 max-w-3xl">
        {actionError && (
          <div className="mb-4 rounded-lg border border-destructive/30 bg-destructive/5 px-4 py-3 text-sm text-destructive">
            {actionError}
          </div>
        )}

        {actionMessage && (
          <div className="mb-4 rounded-lg border border-success/30 bg-success/5 px-4 py-3 text-sm text-success">
            {actionMessage}
          </div>
        )}

        {backupsLoading ? (
          <div className="flex items-center justify-center py-12">
            <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
          </div>
        ) : backups.length === 0 ? (
          <Card>
            <CardContent className="py-12 text-center">
              <Archive className="h-12 w-12 mx-auto mb-4 text-muted-foreground" />
              <h3 className="font-semibold mb-2">No Backups Yet</h3>
              <p className="text-muted-foreground mb-4">
                Backups are created automatically when you apply a profile.
              </p>
              {backupsError && (
                <p className="text-sm text-destructive mb-4">
                  Failed to load backups: {backupsError}
                </p>
              )}
              <Button onClick={handleCreateBackup} disabled={creating}>
                {creating ? (
                  <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                ) : (
                  <Plus className="h-4 w-4 mr-2" />
                )}
                Create Backup Now
              </Button>
            </CardContent>
          </Card>
        ) : (
          <div className="space-y-4">
            {backups.map((backup) => (
              <Card key={backup.id}>
                <CardContent className="p-4">
                  <div className="flex items-start justify-between">
                    <div>
                      <h4 className="font-medium">
                        {formatTimestamp(backup.created_at)}
                      </h4>
                      <p className="text-sm text-muted-foreground mt-1">
                        Backup ID: {backup.id}
                      </p>
                      <p className="text-xs text-muted-foreground mt-2">
                        Components:{' '}
                        {backup.components
                          .map((c) => c.replace('SettingsHandler', ''))
                          .join(', ')}
                      </p>
                    </div>
                    <div className="flex gap-2">
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => handleRestore(backup.id)}
                        disabled={restoring !== null || deleting !== null || creating}
                      >
                        {restoring === backup.id ? (
                          <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                        ) : (
                          <RotateCcw className="h-4 w-4 mr-2" />
                        )}
                        Restore
                      </Button>
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => void handleDelete(backup.id)}
                        disabled={restoring !== null || deleting !== null || creating}
                      >
                        {deleting === backup.id ? (
                          <Loader2 className="h-4 w-4 animate-spin" />
                        ) : (
                          <Trash2 className="h-4 w-4" />
                        )}
                      </Button>
                    </div>
                  </div>
                </CardContent>
              </Card>
            ))}

            <div className="flex justify-end pt-4">
              <Button onClick={handleCreateBackup} disabled={creating || restoring !== null || deleting !== null}>
                {creating ? (
                  <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                ) : (
                  <Plus className="h-4 w-4 mr-2" />
                )}
                Create Backup Now
              </Button>
            </div>
          </div>
        )}
      </main>
    </div>
  );
}

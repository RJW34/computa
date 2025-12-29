import * as React from 'react';
import { Header } from '@/components/Header';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Archive, Trash2, RotateCcw, Eye, Plus, Loader2 } from 'lucide-react';
import { useAppStore } from '@/stores/appStore';
import { formatTimestamp } from '@/lib/utils';

export function BackupManager() {
  const { backups, backupsLoading, loadBackups } = useAppStore();
  const [restoring, setRestoring] = React.useState<string | null>(null);

  React.useEffect(() => {
    loadBackups();
  }, [loadBackups]);

  const handleRestore = async (backupId: string) => {
    setRestoring(backupId);
    // Simulate restore
    await new Promise((resolve) => setTimeout(resolve, 2000));
    setRestoring(null);
    // Would call api.restoreBackup(backupId) in real implementation
  };

  const handleCreateBackup = async () => {
    // Would call api.createBackup() in real implementation
    await loadBackups();
  };

  return (
    <div className="min-h-screen">
      <Header showBack title="Backups" />

      <main className="container mx-auto px-6 py-6 max-w-3xl">
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
              <Button onClick={handleCreateBackup}>
                <Plus className="h-4 w-4 mr-2" />
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
                        {backup.description || `Before profile application`}
                      </p>
                      <p className="text-xs text-muted-foreground mt-2">
                        Components:{' '}
                        {Object.keys(backup.components)
                          .map((c) => c.replace('SettingsHandler', ''))
                          .join(', ')}
                      </p>
                    </div>
                    <div className="flex gap-2">
                      <Button variant="outline" size="sm">
                        <Eye className="h-4 w-4 mr-2" />
                        View Details
                      </Button>
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => handleRestore(backup.id)}
                        disabled={restoring !== null}
                      >
                        {restoring === backup.id ? (
                          <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                        ) : (
                          <RotateCcw className="h-4 w-4 mr-2" />
                        )}
                        Restore
                      </Button>
                      <Button variant="outline" size="sm">
                        <Trash2 className="h-4 w-4" />
                      </Button>
                    </div>
                  </div>
                </CardContent>
              </Card>
            ))}

            <div className="flex justify-end pt-4">
              <Button onClick={handleCreateBackup}>
                <Plus className="h-4 w-4 mr-2" />
                Create Backup Now
              </Button>
            </div>
          </div>
        )}
      </main>
    </div>
  );
}

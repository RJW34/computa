import * as React from 'react';
import { Header } from '@/components/Header';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Copy, FileDown, Gamepad2 } from 'lucide-react';
import { useAppStore } from '@/stores/appStore';
import * as api from '@/lib/api';

export function Reports() {
  const { profiles, profilesLoading, loadProfiles, activeProfile } = useAppStore();
  const [selectedProfile, setSelectedProfile] = React.useState<string | null>(null);
  const [reportContent, setReportContent] = React.useState<string>('');
  const [reportLoading, setReportLoading] = React.useState(false);
  const [reportError, setReportError] = React.useState<string | null>(null);

  React.useEffect(() => {
    if (profiles.length === 0) {
      void loadProfiles();
    }
  }, [loadProfiles, profiles.length]);

  React.useEffect(() => {
    if (selectedProfile === null && profiles.length > 0) {
      const preferredProfile = activeProfile && profiles.some((p) => p.id === activeProfile)
        ? activeProfile
        : profiles[0].id;
      setSelectedProfile(preferredProfile);
    }
  }, [activeProfile, profiles, selectedProfile]);

  React.useEffect(() => {
    const loadReport = async () => {
      if (!selectedProfile) {
        return;
      }

      setReportLoading(true);
      setReportError(null);
      try {
        const report = await api.getReport(selectedProfile);
        setReportContent(report.content);
      } catch (error) {
        setReportError(error instanceof Error ? error.message : 'Failed to load report');
        setReportContent('');
      } finally {
        setReportLoading(false);
      }
    };

    void loadReport();
  }, [selectedProfile]);

  const handleCopy = () => {
    if (reportContent) {
      void navigator.clipboard.writeText(reportContent);
    }
  };

  const selectedProfileName = profiles.find((p) => p.id === selectedProfile)?.display_name;

  return (
    <div className="min-h-screen">
      <Header showBack title="Reports" />

      <main className="container mx-auto px-6 py-6 max-w-3xl">
        <p className="text-muted-foreground mb-4">
          Select a profile to view recommended in-game settings:
        </p>

        {profilesLoading && (
          <p className="text-sm text-muted-foreground mb-4">Loading profiles...</p>
        )}

        {/* Profile selector */}
        <div className="flex flex-wrap gap-2 mb-6">
          {profiles.map((profile) => (
            <Button
              key={profile.id}
              variant={selectedProfile === profile.id ? 'default' : 'outline'}
              onClick={() => setSelectedProfile(profile.id)}
            >
              {profile.display_name}
            </Button>
          ))}
        </div>

        {/* Report content */}
        <Card>
          <CardContent className="pt-6">
            <div className="flex items-center justify-between mb-4">
              <h3 className="font-semibold text-lg flex items-center gap-2">
                <Gamepad2 className="h-5 w-5" />
                {selectedProfileName ? `${selectedProfileName} - In-Game Settings` : 'In-Game Settings'}
              </h3>
            </div>

            <div className="prose prose-sm dark:prose-invert max-w-none">
              <div className="bg-muted p-4 rounded-md font-mono text-sm whitespace-pre-wrap">
                {reportLoading
                  ? 'Loading report...'
                  : reportError
                    ? `Failed to load report: ${reportError}`
                    : reportContent || 'No report available.'}
              </div>
            </div>

            <div className="flex gap-2 mt-4">
              <Button variant="outline" onClick={handleCopy} disabled={!reportContent}>
                <Copy className="h-4 w-4 mr-2" />
                Copy to Clipboard
              </Button>
              <Button variant="outline" disabled>
                <FileDown className="h-4 w-4 mr-2" />
                Export as PDF
              </Button>
            </div>
          </CardContent>
        </Card>
      </main>
    </div>
  );
}

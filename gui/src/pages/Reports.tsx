import * as React from 'react';
import { Header } from '@/components/Header';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent } from '@/components/ui/card';
import { GameMark, gameArtVars, getGameArt } from '@/components/GameMark';
import { Copy, FileText } from 'lucide-react';
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

  const selectedProfileObject = profiles.find((p) => p.id === selectedProfile);
  const selectedProfileName = selectedProfileObject?.display_name;
  const selectedArt = getGameArt(selectedProfileObject);

  return (
    <div className="min-h-screen">
      <Header showBack title="Reports" />

      <main className="container mx-auto max-w-5xl space-y-5 px-6 py-6">
        <section className="command-hero panel-enter p-5" style={gameArtVars(selectedArt)}>
          <div className="relative flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
            <div className="flex min-w-0 items-center gap-4">
              <GameMark profile={selectedProfileObject} size="lg" showName active />
              <div className="min-w-0">
                <p className="section-kicker">In-game report</p>
                <h2 className="truncate text-2xl font-black">
                  {selectedProfileName || 'Select a profile'}
                </h2>
                <p className="line-clamp-2 text-sm text-muted-foreground">
                  {selectedProfileObject?.tray_description ||
                    selectedProfileObject?.description ||
                    'Profile-specific in-game setting notes load here.'}
                </p>
              </div>
            </div>
            {selectedProfileObject?.has_in_game_settings && (
              <Badge variant="success">Report available</Badge>
            )}
          </div>
        </section>

        {profilesLoading && (
          <p className="text-sm text-muted-foreground mb-4">Loading profiles...</p>
        )}

        {/* Profile selector */}
        <div className="grid gap-2 md:grid-cols-2 xl:grid-cols-3">
          {profiles.map((profile) => (
            <button
              key={profile.id}
              type="button"
              className={`flex min-w-0 items-center gap-3 rounded-md border p-3 text-left transition-all ${
                selectedProfile === profile.id
                  ? 'border-primary bg-primary/10'
                  : 'border-border/70 bg-card/70 hover:border-primary/40'
              }`}
              onClick={() => setSelectedProfile(profile.id)}
            >
              <GameMark profile={profile} size="sm" />
              <span className="truncate text-sm font-semibold">{profile.display_name}</span>
            </button>
          ))}
        </div>

        {/* Report content */}
        <Card className="wizard-panel shadow-none" style={gameArtVars(selectedArt)}>
          <CardContent className="pt-6">
            <div className="flex items-center justify-between mb-4">
              <h3 className="font-semibold text-lg flex items-center gap-2">
                <FileText className="h-5 w-5 text-primary" />
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
            </div>
          </CardContent>
        </Card>
      </main>
    </div>
  );
}

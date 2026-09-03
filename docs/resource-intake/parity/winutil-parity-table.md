# WinUtil → computa parity table

- Source: [ChrisTitusTech/winutil](https://github.com/ChrisTitusTech/winutil),
  `config/tweaks.json` (fetched 2026-09-03; 67 entries).
- Method: every WinUtil tweak's actual payload (registry writes, service
  changes, scripts) was extracted and mapped against computa's live surfaces:
  `abso/data/debloat_tweaks.yaml`, `abso/settings/debloat.py`,
  `abso/settings/updates.py`, `abso/settings/windows.py`,
  `abso/settings/mouse.py`, `abso/settings/power.py`,
  `abso/settings/network.py`, and the profile catalog.
- Dispositions follow `EXTERNAL_RESOURCE_INCORPORATION.md`:
  **absorbed** / **documented-noop** / **rejected** / **watchlist**.

## Absorbed (8 reversible deltas imported into `debloat_tweaks.yaml`)

| WinUtil tweak | Imported as | Tier | Notes |
|---|---|---|---|
| WPFTweaksActivity (partial) | Disable User Activity Publishing (`PublishUserActivities=0`) | 1 | Completes computa's existing Activity History pair |
| WPFTweaksTelemetry (partial) | Disable Implicit Ink Data Collection (`RestrictImplicitInkCollection=1`) | 1 | InputPersonalization family was uncovered |
| WPFTweaksTelemetry (partial) | Disable Implicit Text Data Collection (`RestrictImplicitTextCollection=1`) | 1 | |
| WPFTweaksTelemetry (partial) | Disable Contact Harvesting (`HarvestContacts=0`) | 1 | |
| WPFTweaksTelemetry (partial) | Disable Personalization Data Consent (`AcceptedPrivacyPolicy=0`) | 1 | |
| WPFTweaksPreventDeviceMetadataFromNetwork | Prevent Device Metadata Download | 2 | Tier 2: device icons/names stop updating |
| WPFTweaksWPBT | Disable WPBT Vendor Software Execution | 2 | Blocks OEM boot-time software injection; next-boot effect |
| WPFTweaksServices (partial) | MapsBroker to Manual | 2 | Only the safe subset of their service list (see rejected) |

All 8 are plain registry/service writes with recorded defaults — fully covered
by DebloatHandler's existing backup/restore path and locked by
`tests/test_handlers/test_debloat.py::TestBundledCatalogIntegrity`.

## Documented-noop (already covered by computa, often more carefully)

| WinUtil tweak | computa coverage | Note |
|---|---|---|
| WPFTweaksConsumerFeatures | `debloat_tweaks.yaml` DisableWindowsConsumerFeatures | identical |
| WPFTweaksActivity (core pair) | EnableActivityFeed + UploadUserActivities rows | identical keys |
| WPFTweaksTelemetry (core) | AdvertisingInfo, TailoredExperiences, OnlineSpeech, TIPC, Siuf, Start_TrackProgs rows | WinUtil writes `AllowTelemetry=0` (Security level — only honored on Enterprise/Education SKUs); computa deliberately writes `1` (Required), the honest Home/Pro floor |
| WPFTweaksLocation (ConsentStore) | Disable Location Tracking row (tier 2) | `lfsvc` is Manual by default on Win11 — their service change is a no-op |
| WPFTweaksDeliveryOptimization | `abso/settings/updates.py` writes `DODownloadMode=0` | computa uses the Config key with backup/restore |
| WPFTweaksDisableBGapps | Disable Background Apps (Global) row (tier 2) | identical key |
| WPFToggleMouseAcceleration | `MouseSettingsHandler` | computa also fixes the smooth-mouse curves, sensitivity=10, and broadcasts `SPI_SETMOUSESPEED` |
| WPFMultiplaneOverlay | MPO handling in the display/windows path | computa models `OverlayTestMode` as reboot-gated with truthful verification; WinUtil writes it with no reboot semantics |
| WPFToggleGameMode | `windows.py` per-profile `game_mode` | per-profile, not global |
| WPFAddUltPerf / WPFRemoveUltPerf | `power.py` Ultimate Performance + min-state/core-parking plan | computa's plan handling is deeper (hidden-setting reads via `/qh`) |
| WPFTweaksWidget | appx row `MicrosoftWindows.Client.WebExperience` (tier 3) | |
| WPFTweaksWindowsAI (Copilot part) | appx row `Microsoft.Copilot` (tier 3) + `ai_agents.py` detect-only surface | see watchlist for the rest |
| WPFTweaksRestorePoint | computa's own timestamped backup/restore transaction model | different mechanism, same guarantee class, per-apply instead of per-run |

## Rejected (with rationale)

| WinUtil tweak | Rationale |
|---|---|
| WPFTweaksTeredo / WPFTweaksIPv46 / WPFTweaksDisableIPv6 | Online-safety bar: Teredo/IPv6 disable breaks Xbox Live party/matchmaking paths some games still use; latency claims are placebo-tier on healthy networks. computa's network handler stays scoped to measured TCP/NIC tweaks |
| WPFTweaksServices (StorSvc, SharedAccess, CscService parts) | StorSvc-to-Manual has documented breakage (USB storage detection); SharedAccess breaks Mobile Hotspot; CscService is already effectively off on desktops. Not worth the support surface for zero measured gaming gain |
| WPFTweaksRazerBlock / WPFTweaksLogiBlock | Directly conflicts with computa's peripheral stance: `SearchOrderConfig=0` + `DisableCoInstallers=1` block ALL vendor co-installers, and computa deliberately protects G HUB (process_overrides.protect) on this class of rigs |
| WPFTweaksDisplay (visual-effects bundle) | UX-only desktop-feel changes (animations, Aero Peek, menu delay); no measurable in-game benefit on a GPU-composited desktop — outside computa's optimization mission |
| Customize Preferences category (dark mode, taskbar, NumLock, file extensions, snapping, scrollbars, sticky keys, lock screen, login blur, Outlook, battery %, Settings home, Start recommendations, BSoD details, verbose logon, long paths, UTC clock) | Windows customization, not PC optimization — out of product scope |
| WPFTweaksRemoveEdge / WPFTweaksRemoveOneDrive / WPFTweaksEdgeDebloat / WPFTweaksBraveDebloat / WPFTweaksBlockAdobeNet / WPFchangedns / WPFTweaksRemoveHomeAndGallery / WPFTweaksRightClickMenu / WPFTweaksRevertStartMenu / WPFTweaksDisableNotifications / WPFTweaksDisableWarningForUnsignedRdp / WPFTweaksDisableBitLocker / WPFTweaksDisableStoreSearch / WPFTweaksDisableExplorerAutoDiscovery / WPFTweaksEndTaskOnTaskbar | Third-party app surgery, shell customization, security-posture changes, or destructive uninstalls — wrong risk class for a gaming optimizer with a reversibility guarantee |
| WPFTweaksDiskCleanup / WPFTweaksDeleteTempFiles / WPFTweaksStorage / WPFTweaksReservedStorage | One-shot disk maintenance actions, not reversible settings; Reserved Storage disable can break feature updates |
| WPFTweaksHiber | Hibernation/Fast-Startup interplay is power-domain policy; disk-space win only, no gaming benefit; if ever wanted it belongs in `power.py`, not debloat |
| WPFToggleStandbyFix / WPFToggleS3Sleep | Laptop Modern-Standby domain; `PlatformAoAcOverride` is firmware-sensitive and irrelevant to the desktop target |

## Watchlist

| WinUtil tweak | Why deferred | Unblock condition |
|---|---|---|
| WPFTweaksServices (`SvcHostSplitThresholdInKB`) | Real, measurable svchost-count reduction, but the correct value is RAM-dependent (needs computed value + verify logic, not a static YAML row) | Small handler feature: compute threshold from installed RAM, reboot-gated, with verify |
| WPFTweaksWindowsAI (policy/script parts) | computa's 25H2 AI surface (`ai_agents.py`, `xbox_mode.py`) is deliberately detect-only while the rollout stabilizes | Revisit when the 25H2 AI agent surface ships broadly and a reversible policy set is confirmed |
| WPFOOSUbutton | Just launches O&O ShutUp10 — superseded by the dedicated ShutUp10 mapping candidate | Handled by `oo-shutup10-privacy-toggle-mapping` |

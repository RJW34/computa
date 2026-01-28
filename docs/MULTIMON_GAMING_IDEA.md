# Multi-Monitor Gaming Mode

## Concept

Allow gaming on primary monitor while using secondary monitors freely, without breaking out of the game or losing optimization benefits.

**User Goal:** Exclusive fullscreen latency benefits + cursor freedom across monitors + other apps running on secondary displays.

## Technical Reality

True exclusive fullscreen is fundamentally incompatible with multi-monitor cursor freedom. The game has exclusive control of the display adapter output - Windows can't render a cross-monitor cursor.

**However:** Modern Windows 11 + HAGS + VRR gets borderless within ~1-2ms of exclusive fullscreen.

## Proposed Solution: Optimized Borderless Profile

Create profile variants that use optimized borderless instead of exclusive fullscreen:

```
rivals2-online           -> rivals2-online-multimon
slippi-melee             -> slippi-melee-multimon
```

### Settings Differences from Exclusive Profiles

| Setting | Exclusive | Multi-Monitor |
|---------|-----------|---------------|
| Display Mode | Exclusive Fullscreen | Borderless Windowed |
| FSO (Fullscreen Optimizations) | OFF | ON (let Windows optimize) |
| VRR in Windowed | N/A | ON |
| MPO (Multi-Plane Overlay) | OFF | ON |
| Windows VRR Optimize | OFF | ON |

### Latency Impact Assessment

| Game | Exclusive vs Borderless Delta | Acceptable? |
|------|------------------------------|-------------|
| Slippi Melee | ~1-2ms | Maybe not for tournament practice |
| Rivals 2 Online | ~1-2ms | Yes - rollback masks this |
| Rivals 2 Offline | ~1-2ms | Depends on use case |
| Diablo 4 | ~1-2ms | Yes |
| CoD BO7 | ~1-2ms | Marginal |

## Implementation Plan

1. **Create base mixin or flag** in `BaseProfile`:
   ```python
   @property
   def multi_monitor_mode(self) -> bool:
       return False
   ```

2. **WindowsSettingsHandler changes**:
   - When `multi_monitor_mode=True`:
     - Enable FSO instead of disabling
     - Enable VRR optimize
     - Keep other monitors at current refresh (don't force 60Hz)

3. **NvidiaSettingsHandler changes**:
   - When `multi_monitor_mode=True`:
     - Keep MPO enabled
     - Consider VRR/G-SYNC enabled for borderless

4. **Game config handlers** (Rivals2ConfigHandler, DolphinConfigHandler):
   - Set `fullscreen_mode = 1` (Borderless) instead of `0` (Exclusive)

5. **Tray integration**:
   - Add toggle or separate profiles
   - Or: Auto-detect multi-monitor setup and suggest

## Alternative Approaches (More Complex)

### GPU Passthrough VM
- Dedicate GPU to VM running game
- Host OS handles other monitors
- Complex, adds latency, but truly isolated

### Looking Glass
- Similar to passthrough but with frame capture
- Game runs in VM, displayed on host via shared memory
- Sub-1ms overhead claimed

### Dual GPU
- Separate GPU per monitor group
- Game on primary GPU, desktop on secondary
- Requires compatible hardware

## Decision Criteria

When to use multi-monitor mode:
- Online play where rollback masks small latency differences
- Casual/practice sessions
- Games where 1-2ms doesn't matter (ARPGs, etc.)

When to use exclusive mode:
- Tournament practice (Melee, Rivals 2)
- Offline training with frame-perfect inputs
- Any scenario where every ms counts

## Notes

- User currently turns off other monitors when gaming
- OLED primary monitor
- Fighting game focus (latency-sensitive)
- A/B testing recommended before committing to multi-mon workflow

import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';
import ts from 'typescript';

const source = await readFile(new URL('../src/lib/profileState.ts', import.meta.url), 'utf8');
const { outputText } = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 },
});
const { buildProfileUiState, getPendingManualSteps, formatManualStep, verificationIsClean, canAcceptProfileReadback } = await import(
  `data:text/javascript;base64,${Buffer.from(outputText).toString('base64')}`
);
const saved = { activeProfileName: 'Test profile', stateKnown: true };
const clean = {
  all_active: true, status: 'active', pending_apply_settings: [],
  pending_reboot_gated_settings: [], mismatched_handlers: [],
};

test('a saved profile with absent or incomplete verification stays unverified', () => {
  assert.equal(buildProfileUiState(saved).kind, 'unknown');
  assert.equal(buildProfileUiState({ ...saved, verification: { ...clean, all_active: false } }).kind, 'unknown');
});

test('only clean verification earns active status', () => {
  assert.equal(buildProfileUiState({ ...saved, verification: clean }).kind, 'active');
  assert.equal(buildProfileUiState({ ...saved, verification: { ...clean, error: 'read failed' } }).kind, 'error');
});

test('pending changes and failed readback retain actionable states', () => {
  assert.equal(buildProfileUiState({ ...saved, verification: { ...clean, pending_apply_settings: ['Game.cap'] } }).kind, 'needs_apply');
  assert.equal(buildProfileUiState({ ...saved, verification: { ...clean, pending_reboot_gated_settings: ['HAGS'] } }).kind, 'needs_restart');
  assert.equal(buildProfileUiState({ ...saved, verification: { ...clean, mismatched_handlers: ['Game'] } }).kind, 'mismatch');
});

const reflex = {
  handler: 'OW2ConfigHandler', key: 'reflex_mode', label: 'NVIDIA Reflex (in-game)',
  current: 0, current_label: 'Off', expected: 2, expected_label: 'Enabled + Boost',
  satisfied: false,
};

test('manual-only setup needs attention without becoming an apply or reboot problem', () => {
  const verification = { ...clean, manual_steps: [reflex] };
  const ui = buildProfileUiState({ ...saved, verification });
  assert.equal(ui.kind, 'needs_manual');
  assert.equal(ui.needsAttention, true);
  assert.match(ui.detail, /Off; target: Enabled \+ Boost/);
  assert.equal(verificationIsClean(verification), true);
  assert.deepEqual(verification.pending_apply_settings, []);
});

test('only an explicitly satisfied manual check clears the reminder', () => {
  for (const satisfied of [false, null, undefined]) {
    const verification = { ...clean, manual_steps: [{ ...reflex, satisfied }] };
    assert.equal(buildProfileUiState({ ...saved, verification }).kind, 'needs_manual');
  }
  assert.equal(buildProfileUiState({ ...saved, verification: {
    ...clean, manual_steps: [{ ...reflex, satisfied: true }],
  } }).kind, 'active');
  assert.deepEqual(getPendingManualSteps(null), []);
});

test('manual checks never hide a failed readback or a required system action', () => {
  const manual = { ...clean, manual_steps: [reflex] };
  for (const [changes, kind] of [
    [{ error: 'read failed' }, 'error'],
    [{ pending_apply_settings: ['Graphics.fso'] }, 'needs_apply'],
    [{ pending_reboot_gated_settings: ['Graphics.mpo'] }, 'needs_restart'],
    [{ mismatched_handlers: ['Graphics'] }, 'mismatch'],
    [{ all_active: false }, 'unknown'],
  ]) {
    assert.equal(buildProfileUiState({ ...saved, verification: { ...manual, ...changes } }).kind, kind);
  }
});

test('manual reminders tolerate missing values and non-game manual actions', () => {
  assert.equal(formatManualStep({ label: 'NVIDIA application binding', expected: 'Overwatch 2' }),
    'NVIDIA application binding: Not confirmed; target: Overwatch 2');
  assert.equal(formatManualStep({ label: 'Setting', current: 0, expected: false }),
    'Setting: 0; target: false');
  assert.equal(formatManualStep({}), 'Manual setting: Not confirmed; check manually');
  assert.deepEqual(getPendingManualSteps([null, { satisfied: true }, reflex]), [reflex]);
});

test('older readback cannot revive a reminder after same-profile verification changes', () => {
  const starting = {
    activeProfile: 'overwatch2', activeProfileAppliedAt: '2026-09-21T00:44:18',
    activeProfileVerification: { ...clean, manual_steps: [reflex] },
    activeProfileStateKnown: true, activeProfileStateError: null,
  };
  assert.equal(canAcceptProfileReadback(starting, { ...starting }), true);
  for (const change of [
    { activeProfileVerification: { ...clean, manual_steps: [{ ...reflex, satisfied: true }] } },
    { activeProfileVerification: null, activeProfileStateKnown: false },
    { activeProfileStateError: 'Newer verification failed' },
    { activeProfile: 'slippi-melee' },
    { activeProfileAppliedAt: '2026-09-21T01:00:00' },
  ]) {
    assert.equal(canAcceptProfileReadback(starting, { ...starting, ...change }), false);
  }
});

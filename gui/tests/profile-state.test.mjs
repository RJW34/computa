import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';
import ts from 'typescript';

const source = await readFile(new URL('../src/lib/profileState.ts', import.meta.url), 'utf8');
const { outputText } = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 },
});
const { buildProfileUiState } = await import(
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

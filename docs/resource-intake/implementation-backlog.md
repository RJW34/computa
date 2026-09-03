# External Resource Incorporation Backlog

This is the concrete handoff for a stronger model or future agent.

## Immediate next pass

1. Start with `INITIAL_PROPOSALS.md` and the seeded rows in
   `incoming-candidates.json`.
2. Do the `Chris Titus Tech WinUtil` parity audit first because computa already
   has a direct target surface in `debloat_tweaks.yaml`.
3. For each seeded resource, map it to a real computa surface before proposing
   code.
4. Check whether the capability is already present, partially present, or
   intentionally excluded.
5. Write or update one decision note per resource family that matters.
6. Only then start code changes.

## Good first implementation slices

- user-facing docs that explain already-present external influences honestly
- missing troubleshooting/verification docs for current integrations
- safe optional integrations with clear rollback and detection paths
- benchmark harnesses that test whether a third-party idea is real or placebo

## Things to reject unless strong evidence appears

- one-click blind debloat packs
- irreversible registry bundles with no restore story
- latency/network placebo tweaks with no measurement path
- anti-cheat-risky process tampering in online profiles
- Windows service removal framed as a universal gaming win

## Handoff standard

A follow-on implementation pass should leave behind:

- updated candidate statuses
- explicit decision notes
- code/docs/tests if something was absorbed
- a short summary of what still remains unreviewed

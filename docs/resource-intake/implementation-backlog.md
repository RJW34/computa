# External Resource Incorporation Backlog

This is the concrete handoff for a stronger model or future agent.

## Immediate next pass

1. Replace the placeholder row in `incoming-candidates.json` with real resources
   from prior user discussion, tweets, repo links, or archived notes.
2. For each resource, map it to a real computa surface before proposing code.
3. Check whether the capability is already present, partially present, or
   intentionally excluded.
4. Write one `decision-template.md` copy per resource family that matters.
5. Only then start code changes.

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

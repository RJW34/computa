# Security Policy

ABSO modifies Windows registry, services, power plans, and display drivers. Issues that could result in registry/service corruption, broken backups, or privilege escalation are treated as security findings.

## Reporting

Open a private GitHub issue (if the repo is private) or contact the maintainer directly. Do not file public issues for vulnerabilities until a fix is available.

## Scope

In-scope:
- Privilege escalation paths (e.g. command injection in the elevated process).
- Registry writes outside the documented allowlist (Multimedia/Tasks/Games, Tcpip/Parameters, PriorityControl, AppCompatFlags).
- Backup/restore round-trip integrity failures.
- Trust-boundary issues with user-supplied YAML profiles.

Out-of-scope:
- Issues requiring physical access or pre-existing administrator privileges (the tool itself requires admin).
- Hardware-specific behavior on systems without an NVIDIA GPU + supported display.

# Audit entry point

See [the independent audit report](README.md), the clean
[integration entrypoint](INTEGRATION.md), [reproduction commands](REPRODUCE.md)
and the [engineering contract](../architecture/ENGINEERING_CONTRACT.md).

The original audit branch `audit/world-os-hardening` was reconciled onto
OpenCode remediation `cf05def`, then integrated with current `main` `b92aa4d`
without pulling that newer main into the audit branch itself.
Known legacy release blockers remain; manual review of every line is not certified.

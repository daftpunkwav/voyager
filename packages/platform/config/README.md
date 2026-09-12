# platform/config — Configuration loading convention (skeleton)

Precedence: defaults < config file < environment variables; each service only reads configuration under its own prefix (§7.7).
Secrets do not live in this package — see platform/secrets.

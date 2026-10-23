# Guidance by documentation type

Open only the section you need. The lists are **candidates**. Include an item only when the project has it and the audience needs it.

## README

**Candidate sections:** overview and purpose; features that are actually implemented; supported platforms, runtimes, and dependencies; prerequisites; installation and setup; configuration and env vars; auth requirements; running the app, scripts, workers, and services; usage examples; API or integration points; database setup and migrations; test, lint, and dev commands; deployment and operational notes; troubleshooting; project structure; links to architecture, API, and contributing docs.

- Fit it to the project's size and audience. A small library needs a short README, and a service may need links out to deeper docs.
- Move large reference material, such as a full env var table or API reference, into `docs/` and link to it, rather than letting the README grow too big.
- **When updating an existing README:**
  - Keep accurate content and project-specific terminology.
  - Fix outdated, contradictory, or duplicated instructions in place.
  - Don't delete content just because it's unconventional.
  - Clearly separate implemented features from planned or unsupported ones.

## API documentation

**Per endpoint:**
- method and path, and the purpose
- authn and authz requirements
- path, query, header, and body parameters, with required or optional, types, formats, constraints, and defaults
- example request and response, status codes, and the error format
- pagination, filtering, and sorting
- rate limits, timeouts, retries, and idempotency, **only if they're implemented**
- side effects, such as DB writes, external calls, or async jobs
- versioning and compatibility notes

**Trace the full path:** route registration → middleware (auth, validation, rate limiting) → handler → service or DB → serializer. A handler with no auth code may still be protected by router-level middleware. Use tests to confirm status codes and edge cases.

**If a spec already exists** (OpenAPI, Swagger, Postman, and so on):
- Read it first, and update it in place, keeping its schema names, conventions, and versioning.
- Report places where the spec and the implementation disagree.
- Don't create a second competing spec.
- If the spec is generated from code annotations, update the annotations, not the generated file.

## Architecture notes

**Investigate:** entry points and initialization; major modules and their responsibilities and boundaries; data and control flow; internal APIs and external integrations; persistence boundaries; jobs, schedulers, queues, and events; config loading and dependency setup; security boundaries; error propagation, logging, and retries; deployment topology, if the repo shows it; key design decisions and constraints.

- Describe how the system **actually** works. Label each claim **observed**, **inferred**, or **unknown**.
- Name a pattern only when the code demonstrates it.
- **Mermaid diagrams** are useful for system context, component relationships, request flows, data pipelines, sequences for complex workflows, and deployment. Every arrow should match a real dependency or call. Leave out diagrams that don't clarify anything.

## Setup and development guide

**Sources:** manifests, lockfiles, version files (`.nvmrc`, `.python-version`, `.tool-versions`, `rust-toolchain`), scripts, `Makefile`/task runners, Dockerfiles and Compose files, and CI workflows. CI is often the most reliable record of the real setup steps.

**Cover:**
- runtime and tool versions, if they're pinned
- the package manager, which you can tell from the lockfile
- install commands
- env setup, such as copying `.env.example` and the secrets to obtain, with names only
- local DB init and migrations
- start, build, test, lint, and format commands
- optional services, Docker or Compose usage, and OS-specific notes
- **how to tell it worked**, such as expected output, a URL, or a health check
- fixes for common setup failures

Use the commands that exist in the repo. Mark any instruction you didn't run as **unverified** and say what needs checking.

## Code examples and usage guides

- Use real function names, signatures, routes, config fields, return values, and error behavior.
- Include imports and prerequisites. Match the project's language version and style.
- Keep them minimal but reproducible. Use clearly marked placeholders for values the user must supply.
- No credentials, production IDs, or sensitive data.
- Validate them by running, compiling, or using the project's doctest or example tooling, when that's safe. Otherwise don't imply they were run.

## Configuration and environment variable reference

**For each setting:** the exact key, its purpose, type and format, whether it's required or optional, the default **only if one is actually defined**, where it's loaded and used, whether it's sensitive, validation and failure behavior, and a safe example value.

**Cross-check both directions** (see validation.md):
- vars used in code but missing from the docs or sample file
- vars documented or in the sample file but no longer used
- defaults that differ between code and docs
- required settings with no setup instructions
- real secrets committed in sample files or docs. Report the location only.

## CLI, scripts, and operations

**Sources:** argument parsers, command registration, `--help` output (run it only if that's safe), scripts, cron or scheduler config, CI jobs.

**Document:**
- commands and subcommands, arguments, flags, and accepted values
- prerequisites and permissions
- inputs and outputs, and exit codes if they're defined
- side effects, and **whether the command modifies data**
- logging and error behavior
- safe example invocations
- dry-run support **only if it exists**
- scheduling and operational dependencies

Clearly document the effects of destructive or disruptive commands and the precautions to take. Never assume a flag exists because similar tools have one.

## Dependencies and integrations

- **Evidence:** manifests, lockfiles, imports, integration code, deployment config.
- **Document:** external services and APIs, DB engines and drivers, significant libraries, credentials and permissions needed, network and infrastructure needs, required versions, data exchanged, failure modes, and retry behavior.
- **Watch for:**
  - an installed dependency that isn't actually used
  - an SDK present in the codebase, which doesn't prove the integration is wired up or working

## Troubleshooting and runbooks

**Structure for each issue:**
- the **symptom**, such as the exact error text or behavior
- **likely causes**
- **diagnostics**, such as commands or log locations
- **config checks**
- **safe fix steps**
- **how to confirm it's resolved**
- **when to escalate**

Base them on real evidence: error messages in the code, logs, tests, issue notes, or failures you reproduced. Label each cause as **verified** or **hypothesis**. Never make up incidents, known bugs, or procedures.

## Maintenance and consistency audit

Look for:
- docs that contradict the code
- broken links, and outdated paths, commands, and config keys
- examples that use obsolete interfaces
- duplicate explanations that have drifted apart
- important public interfaces with no docs
- inconsistent terminology
- oversized READMEs that should be split
- docs that weren't updated after a behavior change

When documenting a code change, update only the docs that change affects, and only within the task's scope.

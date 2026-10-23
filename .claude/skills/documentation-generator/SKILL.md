---
name: documentation-generator
description: Creates, updates, and audits software documentation grounded in the actual code, config, tests, and project conventions, including READMEs, API references (and existing OpenAPI or Swagger specs), architecture notes with Mermaid diagrams, setup and development guides, configuration and environment-variable references, CLI and script docs, code examples, integration docs, and troubleshooting runbooks. Use when the user asks to write, generate, update, fix, or review documentation or a README; document an API, endpoint, module, CLI, config, or setup process; write architecture notes or a runbook; add usage examples; check whether docs are outdated or match the code; or update docs after a code change. Never invents features, commands, endpoints, or settings. Not for designing or planning architecture (use architecture-planner).
argument-hint: "[doc type, file, or scope]"
---

# Documentation Generator

Write documentation that is **true to this repository**. It should be accurate, useful to its audience, consistent with the project, and cheap to maintain. Accuracy comes before completeness. A short, correct document beats a long one full of guesses.

## Non-negotiable rules

- **Never invent.** Don't document endpoints, fields, status codes, commands, flags, env vars, defaults, features, integrations, or architecture patterns unless the repository shows them. If something can't be established, leave it out or label it clearly as unknown.
- **The implementation is the source of truth for current behavior.** Use tests and existing docs as supporting evidence. When they disagree with the code, flag the disagreement. **Never change code** to match the docs.
- **Never claim verification you didn't do.** Don't say a command, install, or example "works" unless you ran it and saw it succeed. Label anything else as **unverified**.
- **Never include secrets.** Document the key name and how to provide it securely, never a real value. Use clearly marked placeholders such as `<YOUR_API_KEY>`. If you find a committed secret, report its location, not its value.
- **Keep changes minimal.** Keep accurate existing content and project terminology. Edit the affected sections rather than rewriting whole documents. Don't churn wording for style.
- **Have one source of truth per topic.** Link to canonical docs instead of copying them. Update an existing spec, such as OpenAPI, rather than creating a competing one.
- **Stay safe.** Don't install packages, start external services, or run destructive or risky commands just to validate documentation without a good reason and authorization.

## Workflow

### 1. Scope and audience

Work out the doc type: README, API reference, architecture, setup guide, examples, config reference, CLI or operations, integrations, troubleshooting, or an audit. Then work out the audience: new developers, contributors, API consumers, operators, end users, or an internal team. If the scope is clear, proceed. If the request is vague ("improve the docs"), inspect the repo and recommend the most valuable scope before writing a lot.

### 2. Inspect the repository

Use targeted inspection, not a read of every file. Depending on the doc type, look at:

- existing READMEs and `docs/`, and their conventions such as headings, tone, and file layout
- dependency manifests and lockfiles, scripts, `Makefile`/task runners, Dockerfiles and Compose files, CI workflows
- entry points, public interfaces, routes and middleware, CLI argument parsing
- config loaders and sample env files, schemas and migrations, tests and fixtures
- existing API specs, diagrams, and deployment manifests

Identify the real language, framework, runtime, package manager, and build tools **before** choosing any command or example.

### 3. Establish evidence and trace behavior

For each important factual claim, know which file supports it. Trace across files when needed. An endpoint, for example, involves route registration, middleware (auth may be applied there rather than in the handler), validation, the handler, persistence, and the serializer. A config key involves the sample file, the loader, and where it's consumed.

When code, tests, and docs disagree, describe current behavior from the code. Note the discrepancy, and flag a likely code defect if it matters to readers.

### 4. Plan the document

Choose a structure for this audience and purpose. Include only the sections the project needs. Prefer concise explanations with runnable examples over generic prose. Use tables, code blocks, links, and diagrams where they help someone navigate or understand. Guidance for each doc type is in [doc-types.md](doc-types.md).

### 5. Write or update

Create or edit only the files that need it. Keep commands and examples aligned with the repo, using real names, routes, fields, and scripts. Mark genuine uncertainty explicitly, for example *"Unverified: requires a running Redis; not tested."*, or omit the unsupported claim.

### 6. Validate

Do every check that's practical with the existing tooling: paths exist, internal links resolve, commands match the scripts and manifests, env var names match the code, routes and fields match the handlers, Mermaid syntax is valid, examples run if it's safe to run them, and there are no secrets. Use the procedures in [validation.md](validation.md).

### 7. Report

- the files created or updated, and the key content added or corrected
- discrepancies found between the docs and the implementation
- the validation you actually performed, and its results
- what remains unverified: commands, examples, assumptions, missing information
- recommended follow-ups, only if they're valuable

When the user asked for documentation to be **written or updated**, deliver the edited files with a short report, not a long audit.

## Writing standards

- **Describe this repo, not typical projects.** Never assume `npm run dev`, `make test`, or `--dry-run` exists. Check first.
- **Be clear rather than long.** Explain complex behavior thoroughly and cut filler, marketing language, unsupported performance claims, and invented guarantees.
- **Write for the audience.** Explain basics for newcomers, and skip them in advanced reference material.
- **Make it reproducible.** Commands and examples should work in the documented environment, with prerequisites and imports included.
- **Be consistent.** Use the established terminology, naming, formatting, and file organization.
- **Make it traceable.** Be able to point to the code or config behind every significant technical detail.
- **Label architecture claims.** Mark each one as **observed** (shown directly by the code or config), **inferred** (supported by several pieces of evidence), or **unknown**. Don't apply pattern labels like MVC, clean architecture, or microservices unless the code supports them.
- **Every diagram must earn its place** by making a real concept easier to understand.

## Documentation review format

Use this when **reviewing** docs without being asked to rewrite them:

**Overall assessment**: a short evaluation of accuracy, completeness, usability, and maintenance risk.

**Findings**: for each meaningful issue:
- **Severity:** Critical / High / Medium / Low / Info
- **Location:** the document and section
- **Issue:** what is inaccurate, missing, contradictory, or hard to use
- **Evidence:** the code, config, test, or doc that shows it
- **Impact:** how it affects readers, developers, or operators
- **Recommendation:** the specific correction

Make severity proportionate to impact. Install commands that fail, or docs that misrepresent a destructive operation, are **High** or **Critical**. Formatting inconsistencies are **Low**.

**Recommended changes**: the most valuable improvements, in priority order.

**Validation**: the checks performed, failures found, and limitations.

## Example invocations

- `/documentation-generator update the README for the current setup and scripts`
- `/documentation-generator document the /api/v1/orders endpoints`
- `/documentation-generator write an environment variable reference`
- `/documentation-generator audit docs/ against the code`
- "Write architecture notes for this repo with a component diagram."

## Supporting files

- [doc-types.md](doc-types.md): what to include and check for each doc type (README, API, architecture, setup, examples, configuration, CLI and operations, integrations, troubleshooting, maintenance).
- [validation.md](validation.md): practical checks for paths, links, commands, env vars, API accuracy, Mermaid, examples, and secrets.

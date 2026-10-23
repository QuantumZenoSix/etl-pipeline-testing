# Validation procedures

Run the checks that apply. Use **existing** project tooling, and don't install packages just to validate docs without asking. Report each check as **passed**, **failed** (with details), or **not performed** (with the reason).

## Paths and internal links

- For every relative path or link in the docs, confirm the target exists, such as with `ls` or the Glob tool.
- Check that anchor links (`#section`) match real headings.
- If the project already has a link checker, such as `markdown-link-check`, `lychee`, or `remark-validate-links`, run it.
- Don't check external URLs by fetching them unless the user asks. Note them as not checked.

## Commands

- Every documented command must map to something real: a package script (`package.json` `scripts`, `pyproject` scripts), a `Makefile` or `justfile` target, a script file, a CLI entry point, or a tool listed in the manifests.
- The package manager must match the lockfile: `package-lock.json` means npm, `pnpm-lock.yaml` means pnpm, `yarn.lock` means yarn, `poetry.lock` means poetry, `uv.lock` means uv, and so on.
- Run commands only when that's safe and practical. Read-only commands like `--help`, `--version`, a build, or tests in an isolated environment are usually fine. Never run deploys, migrations against shared databases, or destructive scripts.
- Label every command you didn't run as **unverified**.

## Environment variables and config

Cross-check in both directions:

1. **Used in code:** search for how the language reads env vars, for example `process.env.X`, `os.environ`/`os.getenv`, `ENV[...]`, `System.getenv`, `env::var`, config schema definitions (pydantic `BaseSettings`, zod, convict, Viper), and framework config files.
2. **Documented:** the README, `docs/`, `.env.example`/`.env.sample`, and Compose `environment:` blocks.
3. Report: used but undocumented, documented but unused, mismatched defaults, and required settings with no setup instructions.
4. Make sure no real secret values appear in sample files or docs. Look for high-entropy strings, `sk-`/`ghp_`/`AKIA` prefixes, and credentials inside connection strings. Report only the location.

## API accuracy

- Each documented route matches a registered route, with the same method and path, including router prefixes and API version.
- Request fields, types, and required flags match the validation schema or DTO.
- Status codes and error shapes match the handlers, error middleware, and tests.
- Auth requirements match the middleware or guards that actually apply to the route.
- If an OpenAPI spec exists, compare it with the implementation and with the prose docs, and use its validator if the project already has one.

## Mermaid diagrams

- If `mmdc` (mermaid-cli) or a project docs build (MkDocs, Docusaurus, and so on) is available, render or build to check the syntax.
- Otherwise, check by eye: the diagram type declaration is valid (`flowchart`, `sequenceDiagram`, `erDiagram`, ...), brackets and quotes are balanced, there are no reserved words like `end` as bare node IDs, and labels with special characters are quoted. Report the syntax as **not machine-validated**.
- Confirm that every node and edge corresponds to a real component or call.

## Code examples

- If it's safe, run, compile, or type-check the examples, or run the project's doctest or example tests.
- Check that imports, names, signatures, and return shapes match the source.
- If you didn't run an example, say so. Don't imply it's runtime-verified.

## Markdown

- Run the project's markdown linter or formatter if it has one configured, such as `markdownlint` or `prettier`.
- Check that the heading levels are consistent, code fences are closed and tagged with a language, and tables render.

## Final secrets check

Before reporting, scan every changed doc and example for tokens, passwords, internal hostnames, real customer or production identifiers, and personal data.

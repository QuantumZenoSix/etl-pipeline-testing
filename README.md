# ETL pipeline testing 

A small ETL pipeline project that turns an Apache `error.log` into a SQLite database and a dated CSV report of critical issues.
This project was not only intended to show experience is simple ETL scripting but to show how I was able to leverage AI tools like Claude Code to make a better application by using my [Claude Code config](https://github.com/QuantumZenoSix/claude-code-toolkit) as a base to build from.

## What it does

1. **Extract** – reads `error.log` and parses each line (timestamp, module, level, pid/tid, client IP, `AH` code, message).
2. **Filter** – keeps only critical levels: `emerg`, `alert`, `crit`, `error`.
3. **Transform** – normalises the fields (ISO timestamp, port stripped from the client address).
4. **Load** – stores the rows in `errors.db` (table `critical_errors`). Re-running is safe: lines already stored are skipped.
5. **Enrich** – looks up the country of stored client IPs that have none yet via [api.country.is](https://api.country.is/). IPs already resolved are not looked up again, and failed lookups are retried on the next run.
6. **Report** – writes `reports/critical_errors_<YYYY-MM-DD>.csv` from the database. The generation date is in the filename and in the `report_date` column.

CSV columns: `report_date, logged_at, level, module, error_code, client_ip, country, message`

## Usage

Requires Python 3.10+ and no third-party packages.

```
python3 etl.py                      # uses ./error.log, ./errors.db, ./reports/
python3 etl.py --log other.log --db other.db --out-dir out
```  

_output_
```shell
Extracted 10 critical entries from error.log
Stored 10 new rows in errors.db (0 skipped as already stored or duplicate lines)
Set the country on 0 rows
Report written to reports/critical_errors_2026-10-23.csv  
```  

Run the tests:

```
python3 -m unittest
```

## Notes

- `country` is left blank when it can't be determined (the sample `error.log` only contains such IPs, so its report has no countries).
- `country` may be blank because...
- - the line has no client IP
- - the IP is private/reserved (e.g. `192.168.x.x`, `203.0.113.x`)
- - the API has no data for it
- - the API call failed (a warning is printed; the pipeline continues)
- The report contains every critical row in the database, not just the current run's. Running it twice on the same day overwrites that day's file.
- Client IPs are sent to api.country.is (5 second timeout, one request per unique public IP per run). IPs still without a country are looked up again on every run, including ones the API has no data for.
- Text cells in the CSV that start with `=`, `+`, `-` or `@` are prefixed with a `'` so spreadsheets don't run them as formulas.
- Client addresses with an IPv6 scope id (`%...`) are treated as invalid and left without a client IP.
- Only two-letter uppercase country codes from the API are accepted.
- Lines that don't match the Apache error log format, or have an unparsable timestamp, are skipped with a warning. Undecodable bytes in the log are replaced rather than aborting the run.
- Timestamps are stored exactly as written in the log (no timezone conversion).
- Identical log lines (same timestamp, pid, tid and text) are stored once.

## Development history

This project was coded mostly using Claude Code with me fixing small bugs and/or adding editing small sections of code where necessary but saving the actual "bugs" for Claude Code to figure out. The idea was to test my Claude Code toolkit and deminstrate it's efficacy and my ability to leverage it into a sample project.

Here's a link to the toolkit that was dropped in here and used: [Claude-Code-Toolkit](https://github.com/QuantumZenoSix/claude-code-toolkit)

<br />

This project was built with the help of Claude Code (Sonnet 5.5). 


### Prompts I used and what they did

| Commit | Prompt | Effect |
|---|--------|--------|
| `5fe0e2d` | I want to build a small ETL pipeline project which (1) reads the @error.log file, (2) scans for critial issues (errors, emerg, etc), (3) uses the https://api.country.is/ api to determine the country of origin, (4) formats the error log content, (5) stores this data in a sqlite database, and finally (6) generates a csv report with the core details where the csv contains the date the report was generated. Also, write a simple README | Created `etl.py`, `test_etl.py`, and `.gitignore`. <br />Verified with 11 passing tests (which were automatically made by my `test-engineer` agent) and a real run on the sample log. |
| `7df57f1` | "`@architecture-reviewer (agent)`" Reiew the code design and architecture | Verdict: found some non-critical recommendations worth looking into (see findings below). No code changed. |
| `7df57f1` |  "`@test-engineer (agent)`" Write/improve existing tests based on these findings to confirm these issues | Added 17 tests (28 total). Six failed, each showing a real defect. The Debugger agent I set up kicked in automatically to look into these findings . |
| `7df57f1` | Fix `etl.py` so the failing tests (found the the test-engineer) tests pass using what you learned from the `debugger` agent and how the tests failed. | Reordered the pipeline to extract, load, then enrich. Fixed IPv6 port parsing, non-object API responses and the report on a fresh database. Test suite green (29 tests). |
| `0e1fdbd` | `claude-code-guide`: review for quality and accuracy | Found robustness gaps and weak tests (see findings below). |
| `0e1fdbd` | Fix any issues the review finds | Fixed the real ones and left the rest documented. Suite green (R35). Commit `0e1fdbd`. |
| `35bed28` | `performance-analyst`: analyze `etl.py` | Found one measured bottleneck: no index on `client_ip`. |
| `35bed28` | Add the index and a test for it | Added the index and a query-plan test (confirmed it fails without the index). Test suite green (36). |
| `6885e84` | `security-auditor`: look for security issues | Found IPv6 scope-id injection and CSV formula injection, plus hardening notes. |
| `6885e84` | Fix both issues, add the hardening, add tests | Fixed both, added hardening and 7 tests (confirmed 12 checks fail on the old code). Suite green (43). Commit `6885e84`. |

<br />

### Further intervention  
After this point the tests passed just fine.
However, given this is an ETL project, I realize data is always clean and production environments always find the wildest edge cases to I updated the `code-reviewer` agent to take this more seriously.  

Commit `12b8d67d`  

`- assume the input can be messy or even missing critical elements (important for ETL & data pipeline projects)`

Running test again I see further edge cases and improvements to be made:
```markdown
Where it breaks

1. An oversized pid or tid crashes every run (most serious). A line like [pid 99999999999999999999999] fails at load (etl.py:101-102, 171-175) because SQLite can't store the number. The whole batch is rolled back and nothing is saved. The line stays in the log, so every later run fails the same way until the log rotates. The fix is to range-check pid and tid in parse_line so the line is skipped like any other bad line.
2. A deeply nested JSON reply from the country API crashes enrichment. Python raises RecursionError (etl.py:137,143), which the error handler doesn't catch. Every lookup finished so far in that run is lost and the report isn't written. The fix is to add RecursionError to the caught exceptions.
```

This is why updating the Claude code toolkit is so important and something I've been learning to do more - keeping everything context/environment-aware.
Even the tech is relevant - the fact that were parsing (sample) Apache server logs for example is relevant as Apache always writes the port but perhaps other server logs don't and that would matter.  

---

Below is Claude summary on things

```markdown
#### Findings and how they were resolved

**Architecture review**
- Resolved: country lookups ran before the dedupe, so a failed lookup stayed blank forever and re-runs repeated every API call. Enrichment now runs after the load and only for IPs without a country.
- Resolved (re-checked): IPv6 clients with a short port, such as `2001:db8::1:8080`, were parsed as the wrong address.
- Resolved: a non-object API response raised `AttributeError`, and the report failed on a brand-new database.

**Quality and accuracy review**
- Resolved: dropped connections and undecodable API bodies crashed the run, contradicting the README; strict UTF-8 aborted the whole extract on one bad byte; the API's `country` value was not validated; `HTTPError` was never closed; a missing log file gave a raw traceback; the "already present" count included duplicate lines; dead code in `load_entries`.
- Resolved in the tests: a report test that returned a country for a private IP, a schema test that checked nothing, a duplicate test, and references to a review that is not in the repo.
- Resolved in the README: same-day overwrite, re-queried IPs, skipped bad-timestamp lines, naive timestamps and duplicate-line behaviour are now documented.

**Performance review**
- Resolved (agent's measurement): the per-IP `UPDATE` scanned the whole table each time. With 28,000 rows and about 14,000 distinct IPs it took 22 s; with an index on `client_ip` it took 0.054 s.

**Security review**
- Resolved (re-checked): IPv6 scope ids (`addr%anything`) passed the IP validation, so arbitrary text could reach the database, CSV, API URL and terminal warnings. They are now rejected.
- Resolved: CSV formula injection from log text starting with `=`, `+`, `-` or `@`. Those cells are now prefixed with a `'`.
- Resolved (hardening): country must be two uppercase letters, API responses are capped at 64 KB, SQLite sidecar files are git-ignored, and the README notes that IPs go to a third party.
- No issue found: SQL injection, regex slowdown on crafted lines, TLS verification, secrets in the repo.


### Final state
- 46 tests, all passing (up from 11).
- Commits from this work: `5fe0e2d`, `7df57f1`, `0e1fdbd`, `35bed28`, `6885e84`.
```

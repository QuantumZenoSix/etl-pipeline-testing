# etl-pipeline-sample

A small ETL pipeline that turns an Apache `error.log` into a SQLite database and a dated CSV report of critical issues.

## What it does

1. **Extract** – reads `error.log` and parses each line (timestamp, module, level, pid/tid, client IP, `AH` code, message).
2. **Filter** – keeps only critical levels: `emerg`, `alert`, `crit`, `error`.
3. **Enrich** – looks up the country of each client IP via [api.country.is](https://api.country.is/).
4. **Transform** – normalises the fields (ISO timestamp, port stripped from the client address).
5. **Load** – stores the rows in `errors.db` (table `critical_errors`). Re-running is safe: lines already stored are skipped.
6. **Report** – writes `reports/critical_errors_<YYYY-MM-DD>.csv` from the database. The generation date is in the filename and in the `report_date` column.

CSV columns: `report_date, logged_at, level, module, error_code, client_ip, country, message`

## Usage

Requires Python 3.10+ and no third-party packages.

```
python3 etl.py                      # uses ./error.log, ./errors.db, ./reports/
python3 etl.py --log other.log --db other.db --out-dir out
```

Run the tests:

```
python3 -m unittest
```

## Notes

- `country` is left blank when it can't be determined: the line has no client IP, the IP is private/reserved (e.g. `192.168.x.x`, `203.0.113.x`), the API has no data for it, or the API call failed (a warning is printed; the pipeline continues). The sample `error.log` only contains such IPs, so its report has no countries.
- The report contains every critical row in the database, not just the current run's.
- Client IPs are sent to api.country.is (5 second timeout, one request per unique public IP, no retries).
- Lines that don't match the Apache error log format are skipped with a warning.

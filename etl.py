"""Small ETL pipeline: Apache error.log -> critical entries -> country lookup -> SQLite -> CSV report."""

import argparse
import csv
import http.client
import ipaddress
import json
import re
import sqlite3
import sys
import urllib.error
import urllib.request
from contextlib import closing
from dataclasses import dataclass, asdict
from datetime import date, datetime
from pathlib import Path

CRITICAL_LEVELS = {"emerg", "alert", "crit", "error"}
COUNTRY_API_URL = "https://api.country.is/{ip}"
API_TIMEOUT_SECONDS = 5

# e.g. [Thu Oct 22 08:15:11.221843 2026] [authz_core:error] [pid 1024:tid 1081] [client 1.2.3.4:51234] AH01630: message
LOG_LINE = re.compile(
    r"^\[(?P<timestamp>[^\]]+)\]"
    r" \[(?P<module>[^:\]]+):(?P<level>\w+)\]"
    r" \[pid (?P<pid>\d+)(?::tid (?P<tid>\d+))?\]"
    r"(?: \[client (?P<client>[^\]]+)\])?"
    r"(?: (?P<code>AH\d+):)?"
    r"\s*(?P<message>.*)$"
)
TIMESTAMP_FORMAT = "%a %b %d %H:%M:%S.%f %Y"

SCHEMA = """
CREATE TABLE IF NOT EXISTS critical_errors (
    id          INTEGER PRIMARY KEY,
    logged_at   TEXT NOT NULL,
    module      TEXT NOT NULL,
    level       TEXT NOT NULL,
    pid         INTEGER NOT NULL,
    tid         INTEGER,
    client_ip   TEXT,
    error_code  TEXT,
    message     TEXT NOT NULL,
    country     TEXT,
    raw_line    TEXT NOT NULL UNIQUE
)
"""

CSV_COLUMNS = ["report_date", "logged_at", "level", "module", "error_code", "client_ip", "country", "message"]


@dataclass
class LogEntry:
    logged_at: str
    module: str
    level: str
    pid: int
    tid: int | None
    client_ip: str | None
    error_code: str | None
    message: str
    raw_line: str
    country: str | None = None


# --- Extract / Transform -----------------------------------------------------

def parse_client_ip(client: str | None) -> str | None:
    """Strip the port from Apache's `[client ip:port]` value (IPv4 or IPv6)."""
    if not client:
        return None
    # Apache always appends ":port". Strip it first: for IPv6 a short port such as
    # ":8080" is itself a valid group, so the whole string would parse as a wrong address.
    for candidate in (client.rsplit(":", 1)[0], client):
        try:
            return str(ipaddress.ip_address(candidate))
        except ValueError:
            continue
    return None


def parse_line(line: str) -> LogEntry | None:
    match = LOG_LINE.match(line)
    if not match:
        return None
    fields = match.groupdict()
    logged_at = datetime.strptime(fields["timestamp"], TIMESTAMP_FORMAT).isoformat(sep=" ")
    return LogEntry(
        logged_at=logged_at,
        module=fields["module"],
        level=fields["level"],
        pid=int(fields["pid"]),
        tid=int(fields["tid"]) if fields["tid"] else None,
        client_ip=parse_client_ip(fields["client"]),
        error_code=fields["code"],
        message=fields["message"].strip(),
        raw_line=line,
    )


def extract_critical_entries(log_path: Path) -> list[LogEntry]:
    entries = []
    with log_path.open(encoding="utf-8", errors="replace") as log_file:
        for line_number, raw in enumerate(log_file, start=1):
            line = raw.rstrip("\n")
            if not line.strip():
                continue
            try:
                entry = parse_line(line)
            except ValueError as exc:
                print(f"warning: line {line_number} skipped, bad timestamp: {exc}", file=sys.stderr)
                continue
            if entry is None:
                print(f"warning: line {line_number} skipped, unrecognised format", file=sys.stderr)
                continue
            if entry.level in CRITICAL_LEVELS:
                entries.append(entry)
    return entries


def lookup_country(ip: str) -> str | None:
    """Return the ISO country code for a public IP, or None if it can't be determined."""
    if not ipaddress.ip_address(ip).is_global:
        return None  # private/reserved ranges have no country
    try:
        with urllib.request.urlopen(COUNTRY_API_URL.format(ip=ip), timeout=API_TIMEOUT_SECONDS) as response:
            body = json.load(response)
    except urllib.error.HTTPError as exc:
        exc.close()
        if exc.code != 404:  # 404 means the API has no data for this IP
            print(f"warning: country lookup for {ip} failed: HTTP {exc.code}", file=sys.stderr)
        return None
    except (OSError, http.client.HTTPException, ValueError) as exc:
        # OSError covers URLError and timeouts, HTTPException covers dropped connections,
        # ValueError covers invalid JSON or an undecodable body.
        print(f"warning: country lookup for {ip} failed: {exc!r}", file=sys.stderr)
        return None
    country = body.get("country") if isinstance(body, dict) else None
    if not isinstance(country, str) or not country:
        print(f"warning: country lookup for {ip} failed: unexpected response", file=sys.stderr)
        return None
    return country


# --- Load --------------------------------------------------------------------

def open_db(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.execute(SCHEMA)
    return conn


def load_entries(db_path: Path, entries: list[LogEntry]) -> int:
    """Insert entries, skipping lines already stored. Returns the number of new rows."""
    columns = list(asdict(entries[0])) if entries else []
    with closing(open_db(db_path)) as conn, conn:
        if not entries:
            return 0
        before = conn.total_changes
        conn.executemany(
            f"INSERT OR IGNORE INTO critical_errors ({', '.join(columns)}) "
            f"VALUES ({', '.join(':' + c for c in columns)})",
            [asdict(e) for e in entries],
        )
        return conn.total_changes - before


def enrich_countries(db_path: Path) -> int:
    """Look up the country of stored IPs that don't have one yet. Returns the number of rows updated.

    Runs after the load so already-resolved IPs are never looked up again, and IPs whose
    earlier lookup failed are retried on the next run.
    """
    with closing(open_db(db_path)) as conn:
        pending_ips = [row[0] for row in conn.execute(
            "SELECT DISTINCT client_ip FROM critical_errors WHERE client_ip IS NOT NULL AND country IS NULL"
        )]
        # Look up outside any write transaction so slow API calls don't hold the database lock.
        found = [(lookup_country(ip), ip) for ip in pending_ips]
        with conn:
            cursor = conn.executemany(
                "UPDATE critical_errors SET country = ? WHERE client_ip = ? AND country IS NULL",
                [(country, ip) for country, ip in found if country],
            )
        return cursor.rowcount


# --- Report ------------------------------------------------------------------

def generate_report(db_path: Path, out_dir: Path, report_date: date) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    report_path = out_dir / f"critical_errors_{report_date.isoformat()}.csv"
    with closing(open_db(db_path)) as conn:
        rows = conn.execute(
            "SELECT logged_at, level, module, error_code, client_ip, country, message "
            "FROM critical_errors ORDER BY logged_at"
        ).fetchall()
    with report_path.open("w", newline="", encoding="utf-8") as report_file:
        writer = csv.writer(report_file)
        writer.writerow(CSV_COLUMNS)
        for logged_at, level, module, error_code, client_ip, country, message in rows:
            writer.writerow([
                report_date.isoformat(), logged_at, level, module,
                error_code or "", client_ip or "", country or "", message,
            ])
    return report_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--log", type=Path, default=Path("error.log"), help="Apache error log to read")
    parser.add_argument("--db", type=Path, default=Path("errors.db"), help="SQLite database file")
    parser.add_argument("--out-dir", type=Path, default=Path("reports"), help="directory for the CSV report")
    args = parser.parse_args()

    try:
        entries = extract_critical_entries(args.log)
    except FileNotFoundError:
        sys.exit(f"error: log file not found: {args.log}")
    print(f"Extracted {len(entries)} critical entries from {args.log}")

    inserted = load_entries(args.db, entries)
    print(f"Stored {inserted} new rows in {args.db} ({len(entries) - inserted} skipped as already stored or duplicate lines)")

    updated = enrich_countries(args.db)
    print(f"Set the country on {updated} rows")

    report_path = generate_report(args.db, args.out_dir, date.today())
    print(f"Report written to {report_path}")


if __name__ == "__main__":
    main()

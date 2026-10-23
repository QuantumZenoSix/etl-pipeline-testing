"""Small ETL pipeline: Apache error.log -> critical entries -> country lookup -> SQLite -> CSV report."""

import argparse
import csv
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
    for candidate in (client, client.rsplit(":", 1)[0]):
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
    with log_path.open(encoding="utf-8") as log_file:
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
            return json.load(response).get("country")
    except urllib.error.HTTPError as exc:
        if exc.code != 404:  # 404 means the API has no data for this IP
            print(f"warning: country lookup for {ip} failed: HTTP {exc.code}", file=sys.stderr)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        print(f"warning: country lookup for {ip} failed: {exc}", file=sys.stderr)
    return None


def add_countries(entries: list[LogEntry]) -> None:
    countries = {ip: lookup_country(ip) for ip in {e.client_ip for e in entries if e.client_ip}}
    for entry in entries:
        entry.country = countries.get(entry.client_ip)


# --- Load --------------------------------------------------------------------

def load_entries(db_path: Path, entries: list[LogEntry]) -> int:
    """Insert entries, skipping lines already stored. Returns the number of new rows."""
    columns = [c for c in asdict(entries[0]) if c != "id"] if entries else []
    with closing(sqlite3.connect(db_path)) as conn, conn:
        conn.execute(SCHEMA)
        if not entries:
            return 0
        before = conn.total_changes
        conn.executemany(
            f"INSERT OR IGNORE INTO critical_errors ({', '.join(columns)}) "
            f"VALUES ({', '.join(':' + c for c in columns)})",
            [asdict(e) for e in entries],
        )
        return conn.total_changes - before


# --- Report ------------------------------------------------------------------

def generate_report(db_path: Path, out_dir: Path, report_date: date) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    report_path = out_dir / f"critical_errors_{report_date.isoformat()}.csv"
    with closing(sqlite3.connect(db_path)) as conn:
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

    entries = extract_critical_entries(args.log)
    print(f"Extracted {len(entries)} critical entries from {args.log}")

    add_countries(entries)

    inserted = load_entries(args.db, entries)
    print(f"Stored {inserted} new rows in {args.db} ({len(entries) - inserted} already present)")

    report_path = generate_report(args.db, args.out_dir, date.today())
    print(f"Report written to {report_path}")


if __name__ == "__main__":
    main()

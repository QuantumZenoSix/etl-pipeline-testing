import contextlib
import csv
import http.client
import io
import sqlite3
import tempfile
import unittest
import urllib.error
from contextlib import closing
from datetime import date
from pathlib import Path
from unittest import mock

import etl

CLIENT_ERROR = (
    "[Thu Oct 22 08:27:48.192837 2026] [php:error] [pid 1024:tid 1130] [client 203.0.113.25:60122] "
    "PHP Fatal error: Uncaught RuntimeException: Database connection failed"
)
CODED_ERROR = (
    "[Thu Oct 22 08:15:11.221843 2026] [authz_core:error] [pid 1024:tid 1081] [client 192.168.1.45:51234] "
    "AH01630: client denied by server configuration: /var/www/html/admin"
)
EMERG = "[Thu Oct 22 08:30:15.671293 2026] [core:emerg] [pid 1024:tid 1024] AH00020: Configuration Failed, exiting"
NOTICE = "[Thu Oct 22 08:14:02.114523 2026] [core:notice] [pid 1024:tid 1024] AH00094: Command line: '/usr/sbin/apache2'"
WARN = "[Thu Oct 22 08:18:07.331245 2026] [core:warn] [pid 1024:tid 1098] AH00045: child process 1102 still did not exit"


class ParseLineTest(unittest.TestCase):
    def test_parses_all_fields(self):
        entry = etl.parse_line(CODED_ERROR)
        self.assertEqual(entry.logged_at, "2026-10-22 08:15:11.221843")
        self.assertEqual((entry.module, entry.level), ("authz_core", "error"))
        self.assertEqual((entry.pid, entry.tid), (1024, 1081))
        self.assertEqual(entry.client_ip, "192.168.1.45")
        self.assertEqual(entry.error_code, "AH01630")
        self.assertEqual(entry.message, "client denied by server configuration: /var/www/html/admin")

    def test_line_without_client_or_code(self):
        entry = etl.parse_line(CLIENT_ERROR)
        self.assertIsNone(entry.error_code)
        self.assertTrue(entry.message.startswith("PHP Fatal error"))
        entry = etl.parse_line("[Thu Oct 22 08:30:15.671293 2026] [core:emerg] [pid 1] boom")
        self.assertIsNone(entry.client_ip)

    def test_unrecognised_line_returns_none(self):
        self.assertIsNone(etl.parse_line("not an apache line"))


class LookupCountryTest(unittest.TestCase):
    def test_private_ip_skips_api(self):
        with mock.patch("etl.urllib.request.urlopen") as urlopen:
            self.assertIsNone(etl.lookup_country("192.168.1.45"))
        urlopen.assert_not_called()

    def test_public_ip_returns_country(self):
        response = mock.MagicMock()
        response.__enter__.return_value = mock.MagicMock(read=lambda: b'{"ip":"8.8.8.8","country":"US"}')
        with mock.patch("etl.urllib.request.urlopen", return_value=response):
            self.assertEqual(etl.lookup_country("8.8.8.8"), "US")

    def test_network_failure_returns_none(self):
        with mock.patch("etl.urllib.request.urlopen", side_effect=urllib.error.URLError("down")):
            self.assertIsNone(etl.lookup_country("8.8.8.8"))


class PipelineTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        self.log = self.tmp / "error.log"
        self.log.write_text("\n".join([NOTICE, CODED_ERROR, WARN, "garbage", CLIENT_ERROR, EMERG]) + "\n")

    def test_extract_keeps_only_critical_levels(self):
        entries = etl.extract_critical_entries(self.log)
        self.assertEqual([e.level for e in entries], ["error", "error", "emerg"])

    def test_load_is_idempotent(self):
        db = self.tmp / "errors.db"
        entries = etl.extract_critical_entries(self.log)
        self.assertEqual(etl.load_entries(db, entries), 3)
        self.assertEqual(etl.load_entries(db, entries), 0)

    def test_load_with_no_entries_creates_schema(self):
        db = self.tmp / "errors.db"
        self.assertEqual(etl.load_entries(db, []), 0)
        with closing(sqlite3.connect(db)) as conn:
            tables = [row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")]
        self.assertIn("critical_errors", tables)

    def test_report_contains_generation_date(self):
        db = self.tmp / "errors.db"
        entries = etl.extract_critical_entries(self.log)
        etl.load_entries(db, entries)
        # Mirror the real lookup: private IPs have no country.
        with mock.patch("etl.lookup_country", side_effect=lambda ip: "AU" if ip == "203.0.113.25" else None):
            etl.enrich_countries(db)

        path = etl.generate_report(db, self.tmp / "reports", date(2026, 10, 22))

        self.assertEqual(path.name, "critical_errors_2026-10-22.csv")
        with path.open(newline="") as f:
            rows = list(csv.DictReader(f))
        self.assertEqual(len(rows), 3)
        self.assertEqual({r["report_date"] for r in rows}, {"2026-10-22"})
        self.assertEqual(rows[0]["country"], "")  # private IP
        self.assertEqual(rows[1]["country"], "AU")
        self.assertEqual(rows[2]["client_ip"], "")  # emerg line has no client


# --- Enrichment, parsing and robustness ---------------------------------------

PUBLIC_ERROR = (
    "[Thu Oct 22 08:40:00.000001 2026] [php:error] [pid 1024:tid 1140] [client 8.8.8.8:40000] "
    "AH00001: something broke"
)
BAD_TIMESTAMP = "[Xyz Foo 99 99:99:99.000000 2026] [core:error] [pid 1] boom"


def fake_response(body: bytes):
    response = mock.MagicMock()
    response.__enter__.return_value = mock.MagicMock(read=lambda: body)
    return response


def http_error(code: int):
    return urllib.error.HTTPError("https://api.country.is/8.8.8.8", code, "msg", {}, None)


def run_pipeline(log: Path, db: Path) -> int:
    """Same flow as etl.main(): extract -> load_entries -> enrich_countries."""
    entries = etl.extract_critical_entries(log)
    inserted = etl.load_entries(db, entries)
    etl.enrich_countries(db)
    return inserted


class EnrichmentIdempotencyTest(unittest.TestCase):
    """Failed lookups are retried on the next run; resolved IPs are never looked up again."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        self.log = self.tmp / "error.log"
        self.log.write_text(PUBLIC_ERROR + "\n")
        self.db = self.tmp / "errors.db"

    def stored_country(self):
        with closing(sqlite3.connect(self.db)) as conn:
            return conn.execute("SELECT country FROM critical_errors").fetchone()[0]

    def test_country_backfilled_after_transient_lookup_failure(self):
        with mock.patch("etl.lookup_country", return_value=None):
            run_pipeline(self.log, self.db)
        self.assertIsNone(self.stored_country())

        with mock.patch("etl.lookup_country", return_value="US"):
            run_pipeline(self.log, self.db)

        self.assertEqual(self.stored_country(), "US")

    def test_rerun_on_unchanged_log_makes_no_new_lookups(self):
        with mock.patch("etl.lookup_country", return_value="US") as lookup:
            run_pipeline(self.log, self.db)
            calls_after_first_run = lookup.call_count
            run_pipeline(self.log, self.db)

        self.assertEqual(calls_after_first_run, 1)
        self.assertEqual(lookup.call_count, calls_after_first_run)


class ParseClientIpTest(unittest.TestCase):
    """Apache writes IPv6 clients unbracketed, so a short port like :8080 looks like an address group."""

    def test_ipv6_with_short_port(self):
        self.assertEqual(etl.parse_client_ip("2001:db8::1:8080"), "2001:db8::1")

    def test_ipv6_loopback_with_short_port(self):
        self.assertEqual(etl.parse_client_ip("::1:80"), "::1")

    def test_ipv6_with_long_port(self):
        self.assertEqual(etl.parse_client_ip("2001:db8::1:51234"), "2001:db8::1")

    def test_ipv4_with_and_without_port(self):
        self.assertEqual(etl.parse_client_ip("203.0.113.25:80"), "203.0.113.25")
        self.assertEqual(etl.parse_client_ip("203.0.113.25"), "203.0.113.25")

    def test_missing_or_garbage_client_returns_none(self):
        self.assertIsNone(etl.parse_client_ip(None))
        self.assertIsNone(etl.parse_client_ip("not-an-ip:80"))


class LookupCountryErrorHandlingTest(unittest.TestCase):
    """Every API failure mode returns None so the pipeline keeps going."""

    def lookup_capturing_stderr(self, **urlopen_kwargs):
        stderr = io.StringIO()
        with mock.patch("etl.urllib.request.urlopen", **urlopen_kwargs), contextlib.redirect_stderr(stderr):
            result = etl.lookup_country("8.8.8.8")
        return result, stderr.getvalue()

    def test_http_404_returns_none_silently(self):
        result, stderr = self.lookup_capturing_stderr(side_effect=http_error(404))
        self.assertIsNone(result)
        self.assertEqual(stderr, "")

    def test_http_429_returns_none_with_warning(self):
        result, stderr = self.lookup_capturing_stderr(side_effect=http_error(429))
        self.assertIsNone(result)
        self.assertIn("HTTP 429", stderr)

    def test_http_500_returns_none_with_warning(self):
        result, stderr = self.lookup_capturing_stderr(side_effect=http_error(500))
        self.assertIsNone(result)
        self.assertIn("HTTP 500", stderr)

    def test_timeout_returns_none_with_warning(self):
        result, stderr = self.lookup_capturing_stderr(side_effect=TimeoutError("timed out"))
        self.assertIsNone(result)
        self.assertIn("warning", stderr)

    def test_non_dict_json_body_returns_none(self):
        result, _ = self.lookup_capturing_stderr(return_value=fake_response(b'["US"]'))
        self.assertIsNone(result)

    def test_malformed_json_body_returns_none(self):
        result, _ = self.lookup_capturing_stderr(return_value=fake_response(b"<html>oops"))
        self.assertIsNone(result)

    def test_undecodable_body_returns_none(self):
        result, stderr = self.lookup_capturing_stderr(return_value=fake_response(b"\xff\xfe"))
        self.assertIsNone(result)
        self.assertIn("warning", stderr)

    def test_dropped_connection_returns_none(self):
        result, stderr = self.lookup_capturing_stderr(side_effect=http.client.RemoteDisconnected("closed"))
        self.assertIsNone(result)
        self.assertIn("warning", stderr)

    def test_non_string_country_returns_none(self):
        result, _ = self.lookup_capturing_stderr(return_value=fake_response(b'{"country": 123}'))
        self.assertIsNone(result)

    def test_requests_expected_url_with_timeout(self):
        with mock.patch("etl.urllib.request.urlopen", return_value=fake_response(b'{"country":"US"}')) as urlopen:
            etl.lookup_country("8.8.8.8")
        urlopen.assert_called_once_with("https://api.country.is/8.8.8.8", timeout=etl.API_TIMEOUT_SECONDS)


class EnrichCountriesTest(unittest.TestCase):
    def test_one_lookup_per_unique_ip_and_no_client_left_none(self):
        entries = [
            etl.parse_line(PUBLIC_ERROR),
            etl.parse_line(PUBLIC_ERROR.replace("pid 1024", "pid 2048")),  # same IP, different line
            etl.parse_line(CLIENT_ERROR),
            etl.parse_line(EMERG),  # no client
        ]
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "errors.db"
            etl.load_entries(db, entries)
            with mock.patch("etl.lookup_country", side_effect=lambda ip: {"8.8.8.8": "US"}.get(ip)) as lookup:
                updated = etl.enrich_countries(db)
            with closing(sqlite3.connect(db)) as conn:
                countries = [r[0] for r in conn.execute("SELECT country FROM critical_errors ORDER BY id")]

        self.assertEqual(sorted(c.args[0] for c in lookup.call_args_list), ["203.0.113.25", "8.8.8.8"])
        self.assertEqual(countries, ["US", "US", None, None])
        self.assertEqual(updated, 2)

    def test_private_ip_makes_no_http_request(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "errors.db"
            etl.load_entries(db, [etl.parse_line(CODED_ERROR)])
            with mock.patch("etl.urllib.request.urlopen") as urlopen:
                self.assertEqual(etl.enrich_countries(db), 0)
        urlopen.assert_not_called()

    def test_nothing_to_enrich_returns_zero(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(etl.enrich_countries(Path(tmp) / "errors.db"), 0)


class ReportOnEmptyDbTest(unittest.TestCase):
    def test_report_on_brand_new_db_without_table(self):
        """A fresh database yields a header-only report, not 'no such table'."""
        with tempfile.TemporaryDirectory() as tmp:
            path = etl.generate_report(Path(tmp) / "new.db", Path(tmp), date(2026, 10, 22))
            with path.open(newline="") as f:
                rows = list(csv.reader(f))
        self.assertEqual(rows, [etl.CSV_COLUMNS])


class ExtractRobustnessTest(unittest.TestCase):
    """Bad input lines, a missing log, and duplicate lines."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)

    def test_unparsable_timestamp_line_is_skipped_with_warning(self):
        log = self.tmp / "error.log"
        log.write_text("\n".join([BAD_TIMESTAMP, EMERG]) + "\n")
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            entries = etl.extract_critical_entries(log)
        self.assertEqual([e.level for e in entries], ["emerg"])
        self.assertIn("line 1 skipped", stderr.getvalue())

    def test_undecodable_bytes_do_not_abort_extract(self):
        log = self.tmp / "error.log"
        log.write_bytes(EMERG.encode() + b"\n" + CODED_ERROR.encode().replace(b"denied", b"d\xffnied") + b"\n")
        self.assertEqual([e.level for e in etl.extract_critical_entries(log)], ["emerg", "error"])

    def test_missing_log_file_exits_with_clear_message(self):
        argv = ["etl.py", "--log", str(self.tmp / "nope.log"), "--db", str(self.tmp / "e.db")]
        with mock.patch("sys.argv", argv), self.assertRaises(SystemExit) as raised:
            etl.main()
        self.assertIn("log file not found", str(raised.exception))

    def test_identical_raw_lines_collapse_into_one_row(self):
        # Documents CURRENT behaviour (raw_line UNIQUE): two distinct events with identical text are merged.
        log = self.tmp / "error.log"
        log.write_text(EMERG + "\n" + EMERG + "\n")
        db = self.tmp / "errors.db"
        entries = etl.extract_critical_entries(log)
        self.assertEqual(len(entries), 2)
        self.assertEqual(etl.load_entries(db, entries), 1)


if __name__ == "__main__":
    unittest.main()

import csv
import tempfile
import unittest
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

    def test_ipv6_client(self):
        self.assertEqual(etl.parse_client_ip("2001:db8::1:51234"), "2001:db8::1")
        self.assertEqual(etl.parse_client_ip("203.0.113.25:80"), "203.0.113.25")


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
        with mock.patch("etl.urllib.request.urlopen", side_effect=etl.urllib.error.URLError("down")):
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
        etl.generate_report(db, self.tmp, date(2026, 10, 22))

    def test_report_contains_generation_date(self):
        db = self.tmp / "errors.db"
        entries = etl.extract_critical_entries(self.log)
        with mock.patch("etl.lookup_country", return_value="AU"):
            etl.add_countries(entries)
        etl.load_entries(db, entries)

        path = etl.generate_report(db, self.tmp / "reports", date(2026, 10, 22))

        self.assertEqual(path.name, "critical_errors_2026-10-22.csv")
        with path.open(newline="") as f:
            rows = list(csv.DictReader(f))
        self.assertEqual(len(rows), 3)
        self.assertEqual({r["report_date"] for r in rows}, {"2026-10-22"})
        self.assertEqual(rows[0]["country"], "AU")
        self.assertEqual(rows[2]["client_ip"], "")  # emerg line has no client


if __name__ == "__main__":
    unittest.main()

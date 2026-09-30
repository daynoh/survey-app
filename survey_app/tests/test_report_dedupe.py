"""Unit tests for the one-report-per-person-per-period dedupe (mocked frappe)."""

import contextlib
import unittest
from datetime import date
from unittest.mock import MagicMock, patch

import frappe
from frappe import _dict

import survey_app.individual_report as ir


@contextlib.contextmanager
def fake_frappe(settings=None):
	frappe.local.flags = getattr(frappe.local, "flags", None) or frappe._dict()
	frappe.local.flags.in_test = True  # skip frappe's typing-validation site checks
	frappe.local.session = frappe._dict(user="Administrator")  # survey_admin_required short-circuits
	fake = MagicMock()
	fake._dict = frappe._dict
	settings_doc = settings or _dict(report_frequency="Monthly")
	fake.get_all.return_value = ["EMP-1"]

	def _get_doc(*a):
		# settings doc for "Value Scoring Settings"; fresh mock doc for inserts
		return settings_doc if (a and a[0] == "Value Scoring Settings") else MagicMock()

	fake.get_doc.side_effect = _get_doc
	fake.log_error.return_value = None
	with patch.object(ir, "frappe", fake), patch.object(
		ir, "_report_period", return_value=(date(2026, 9, 1), date(2026, 9, 30))
	), patch.object(ir, "formatdate", lambda v, *a, **k: str(v)), patch.object(
		ir, "now_datetime", lambda: __import__("datetime").datetime(2026, 9, 30, 18, 0)
	):
		yield fake


class TestIndividualReportDedupe(unittest.TestCase):
	def test_bulk_send_skips_already_sent(self):
		"""Three force-runs on 30 Sep re-emailed the same report; bulk sends must
		now skip employees who already have this period's report logged."""
		with fake_frappe() as fake, patch.object(
			ir, "_report_already_sent", return_value="SRLOG-0001"
		) as already, patch.object(
			ir, "build_employee_report", return_value=_dict(has_data=1, email="a@x", html="<p/>", employee_name="A")
		), patch("survey_app.email_log.send_survey_email") as send_mail:
			result = ir.send_individual_reports(force=1)

		self.assertEqual(result["sent"], 0)
		self.assertEqual(result["skipped"], 1)
		self.assertEqual(result["details"]["skipped"][0]["reason"], "already_sent")
		send_mail.assert_not_called()
		# the dedupe check keyed on the right employee/period/report type
		args = already.call_args.args
		self.assertEqual(args[0], "EMP-1")
		self.assertEqual(args[1], date(2026, 9, 1))
		self.assertEqual(args[2], date(2026, 9, 30))
		self.assertEqual(args[3], "Progress")

	def test_single_employee_preview_still_resends(self):
		"""HR forcing a single-employee preview may re-send even when logged."""
		with fake_frappe() as fake, patch.object(
			ir, "_report_already_sent", return_value="SRLOG-0001"
		), patch.object(
			ir,
			"build_employee_report",
			return_value=_dict(has_data=1, email="a@x", html="<p/>", employee_name="A"),
		), patch("survey_app.email_log.send_survey_email", return_value=_dict(status="queued")) as send_mail:
			result = ir.send_individual_reports(force=1, employee="EMP-1")

		self.assertEqual(result["sent"], 1)
		send_mail.assert_called_once()

	def test_first_send_of_period_goes_through(self):
		with fake_frappe() as fake, patch.object(
			ir, "_report_already_sent", return_value=None
		), patch.object(
			ir,
			"build_employee_report",
			return_value=_dict(has_data=1, email="a@x", html="<p/>", employee_name="A"),
		), patch("survey_app.email_log.send_survey_email", return_value=_dict(status="queued")) as send_mail:
			result = ir.send_individual_reports(force=1)

		self.assertEqual(result["sent"], 1)
		send_mail.assert_called_once()


class TestDigestDedupe(unittest.TestCase):
	def test_digest_helper_queries_exact_recipient_type_subject(self):
		fake = MagicMock()
		fake.db.exists.return_value = "ELOG-1"
		with patch.object(ir, "frappe", fake):
			out = ir._digest_already_sent("mgr@x", "Manager Report", "Team Performance Digest — A (1 Sep 2026 – 30 Sep 2026)")
		self.assertEqual(out, "ELOG-1")
		fake.db.exists.assert_called_once_with(
			"Survey Email Log",
			{"recipient": "mgr@x", "email_type": "Manager Report", "subject": "Team Performance Digest — A (1 Sep 2026 – 30 Sep 2026)"},
		)

	def test_report_helper_queries_sent_or_pending_only(self):
		fake = MagicMock()
		fake.db.exists.return_value = None
		with patch.object(ir, "frappe", fake):
			out = ir._report_already_sent("EMP-1", date(2026, 9, 1), date(2026, 9, 30), "Progress")
		self.assertIsNone(out)
		filters = fake.db.exists.call_args.args[1]
		self.assertEqual(filters["employee"], "EMP-1")
		self.assertEqual(filters["report_type"], "Progress")
		self.assertEqual(filters["status"], ("in", ("Pending", "Sent")))

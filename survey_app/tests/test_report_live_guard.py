"""The 360 report must always run live (prepared-report gate regression)."""

import unittest
from contextlib import contextmanager
from unittest.mock import MagicMock, patch

import frappe
from frappe import _dict

import survey_app.survey_config as config

REPORT = "Employee 360 Degree Survey Response"


@contextmanager
def fake_env(exists=True, prepared=1):
	frappe.local.flags = getattr(frappe.local, "flags", None) or _dict()
	frappe.local.flags.in_test = True  # skip frappe's typing-validation site checks
	fake = MagicMock()
	fake.db.exists.return_value = exists
	fake.db.get_value.return_value = prepared
	with patch.object(config, "frappe", fake):
		yield fake


class TestReportLiveGuard(unittest.TestCase):
	def test_rearms_off(self):
		with fake_env(prepared=1) as fake:
			config.ensure_360_report_live()
		fake.db.set_value.assert_called_once_with("Report", REPORT, "prepared_report", 0)
		fake.db.commit.assert_called_once()

	def test_noop_when_already_live(self):
		with fake_env(prepared=0) as fake:
			config.ensure_360_report_live()
		fake.db.set_value.assert_not_called()

	def test_noop_when_report_missing(self):
		with fake_env(exists=False) as fake:
			config.ensure_360_report_live()
		fake.db.set_value.assert_not_called()

class TestDecoratorsIntact(unittest.TestCase):
	"""A helper inserted between a decorator block and its def silently steals
	the decorators (this bit us three times); pin the placement."""

	def test_install_workspace_keeps_admin_guard(self):
		import inspect

		source = inspect.getsource(config.install_workspace)
		self.assertIn("@survey_admin_required", source)

	def test_guard_is_not_whitelisted(self):
		import inspect

		source = inspect.getsource(config.ensure_360_report_live)
		self.assertNotIn("@frappe.whitelist()", source)

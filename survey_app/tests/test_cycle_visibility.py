from unittest import TestCase
from unittest.mock import patch

from survey_app.my_surveys import _get_assignments, _get_result_periods
from survey_app.survey_analytics import build_conditions
from survey_app.cycle_scope import hide_previous_cycle_data
from survey_app.survey_app.report.employee_360_degree_survey_respose.employee_360_degree_survey_respose import (
	get_conditions as get_report_conditions,
)


class TestCurrentCycleVisibility(TestCase):
	def setUp(self):
		self.current_scope = {
			"include_history": False,
			"history_hidden": True,
			"current_cycle": {"name": "SCY-CURRENT", "title": "Current Cycle"},
		}

	def test_analytics_defaults_to_current_cycle(self):
		conditions, values = build_conditions({}, scope=self.current_scope)

		self.assertIn("scope_cycle_pair.parent = %(current_cycle)s", conditions)
		self.assertEqual(values["current_cycle"], "SCY-CURRENT")

	def test_analytics_history_override_removes_cycle_constraint(self):
		history_scope = {
			"include_history": True,
			"history_hidden": False,
			"current_cycle": {"name": "SCY-CURRENT"},
		}
		conditions, values = build_conditions({}, scope=history_scope)

		self.assertNotIn("scope_cycle_pair.parent", conditions)
		self.assertNotIn("current_cycle", values)

	def test_standard_360_report_defaults_to_current_cycle(self):
		with patch(
			"survey_app.survey_app.report.employee_360_degree_survey_respose."
			"employee_360_degree_survey_respose.get_cycle_scope",
			return_value=self.current_scope,
		):
			conditions, values = get_report_conditions({})

		self.assertIn("report_cycle_pair.parent = %(current_cycle)s", conditions)
		self.assertEqual(values["current_cycle"], "SCY-CURRENT")

	@patch("survey_app.cycle_scope.frappe.db.exists", side_effect=[True, False])
	def test_visibility_defaults_to_hidden_before_setting_is_migrated(self, _exists):
		self.assertTrue(hide_previous_cycle_data())

	@patch("survey_app.cycle_scope.frappe.db.sql", return_value=[])
	@patch("survey_app.cycle_scope.frappe.db.exists", return_value=True)
	def test_visibility_defaults_to_hidden_for_missing_upgraded_setting(self, _exists, _db_sql):
		self.assertTrue(hide_previous_cycle_data())

	@patch("survey_app.cycle_scope.frappe.db.sql", return_value=[("",)])
	@patch("survey_app.cycle_scope.frappe.db.exists", return_value=True)
	def test_visibility_defaults_to_hidden_for_blank_upgraded_setting(self, _exists, _db_sql):
		self.assertTrue(hide_previous_cycle_data())

	@patch("survey_app.cycle_scope.frappe.db.sql", return_value=[("0",)])
	@patch("survey_app.cycle_scope.frappe.db.exists", return_value=True)
	def test_visibility_honours_explicit_history_setting(self, _exists, _db_sql):
		self.assertFalse(hide_previous_cycle_data())

	@patch("survey_app.my_surveys._get_legacy_bounds")
	@patch("survey_app.my_surveys.frappe.db.sql", return_value=[])
	@patch("survey_app.my_surveys.frappe.db.exists", return_value=True)
	def test_employee_periods_exclude_legacy_and_other_cycles(
		self,
		_exists,
		db_sql,
		get_legacy_bounds,
	):
		periods = _get_result_periods(
			"EMP-1",
			current_cycle="SCY-CURRENT",
			current_cycle_only=True,
		)

		self.assertEqual(periods, [])
		query, values = db_sql.call_args.args[:2]
		self.assertIn("AND sc.name = %(current_cycle)s", query)
		self.assertEqual(values["current_cycle"], "SCY-CURRENT")
		get_legacy_bounds.assert_not_called()

	@patch("survey_app.my_surveys.frappe.db.sql", return_value=[])
	def test_employee_assignments_are_joined_to_current_cycle(self, db_sql):
		assignments = _get_assignments(
			"employee@example.com",
			current_cycle="SCY-CURRENT",
			current_cycle_only=True,
		)

		query, values = db_sql.call_args.args[:2]
		self.assertIn("INNER JOIN `tabSurvey Cycle Pair` assignment_cycle_pair", query)
		self.assertIn("assignment_cycle_pair.parent = %(current_cycle)s", query)
		self.assertEqual(values["current_cycle"], "SCY-CURRENT")
		self.assertEqual(assignments["pending_count"], 0)
		self.assertEqual(assignments["completed_count"], 0)

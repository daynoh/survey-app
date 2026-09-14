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


class TestListScopingAndSubmissionGuards(TestCase):
	@patch("survey_app.cycle_scope.frappe")
	@patch("survey_app.cycle_scope.hide_previous_cycle_data", return_value=True)
	@patch("survey_app.cycle_scope.get_current_cycle", return_value={"name": "SCY-CURRENT"})
	def test_survey_list_scopes_to_current_cycle_when_history_hidden(self, _current, _hide, frappe_api):
		from survey_app import cycle_scope

		frappe_api.db.escape.side_effect = lambda value: f"'{value}'"
		condition = cycle_scope.survey_list_conditions()
		self.assertIn("`tabSurvey`.`cycle` = 'SCY-CURRENT'", condition)

	@patch("survey_app.cycle_scope.frappe")
	@patch("survey_app.cycle_scope.hide_previous_cycle_data", return_value=True)
	@patch("survey_app.cycle_scope.get_current_cycle", return_value=None)
	def test_survey_list_hides_everything_without_a_current_cycle(self, _current, _hide, _frappe_api):
		from survey_app import cycle_scope

		self.assertEqual(cycle_scope.survey_list_conditions(), "1 = 0")

	@patch("survey_app.cycle_scope.frappe")
	@patch("survey_app.cycle_scope.hide_previous_cycle_data", return_value=False)
	@patch("survey_app.cycle_scope.get_current_cycle", return_value={"name": "SCY-CURRENT"})
	def test_survey_list_always_hides_legacy_when_history_visible(self, _current, _hide, _frappe_api):
		from survey_app import cycle_scope

		condition = cycle_scope.survey_list_conditions()
		self.assertIn("IFNULL(`tabSurvey`.`cycle`, '') != ''", condition)

	@patch("survey_app.cycle_scope.frappe")
	@patch("survey_app.cycle_scope.hide_previous_cycle_data", return_value=True)
	@patch("survey_app.cycle_scope.get_current_cycle", return_value={"name": "SCY-CURRENT"})
	def test_response_list_scopes_via_survey_subquery(self, _current, _hide, frappe_api):
		from survey_app import cycle_scope

		frappe_api.db.escape.side_effect = lambda value: f"'{value}'"
		condition = cycle_scope.survey_response_list_conditions()
		self.assertIn("`tabSurvey Response`.`survey` IN", condition)
		self.assertIn("`tabSurvey`.`cycle` = 'SCY-CURRENT'", condition)

	@patch("survey_app.cycle_scope.get_current_cycle", return_value={"name": "SCY-CURRENT"})
	@patch("survey_app.survey_app.doctype.survey_questions.survey_questions.frappe")
	def test_submit_rejects_second_submission(self, frappe_api, _current):
		from inspect import unwrap

		import frappe as real_frappe

		from survey_app.survey_app.doctype.survey_questions.survey_questions import submit_survey

		frappe_api._dict.side_effect = real_frappe._dict
		frappe_api.db.exists.side_effect = lambda doctype, *args, **kwargs: True
		frappe_api.get_doc.return_value = real_frappe._dict(
			name="SURV-001", cycle="SCY-CURRENT", questions=[]
		)
		frappe_api.ValidationError = real_frappe.ValidationError
		frappe_api.throw.side_effect = real_frappe.ValidationError

		with self.assertRaises(real_frappe.ValidationError):
			unwrap(submit_survey)("SURV-001", {"q1": 4})
		self.assertIn("already been submitted", frappe_api.throw.call_args[0][0])

	@patch("survey_app.cycle_scope.get_current_cycle", return_value={"name": "SCY-CURRENT"})
	@patch("survey_app.survey_app.doctype.survey_questions.survey_questions.frappe")
	def test_submit_rejects_surveys_outside_the_current_cycle(self, frappe_api, _current):
		from inspect import unwrap

		import frappe as real_frappe

		from survey_app.survey_app.doctype.survey_questions.survey_questions import submit_survey

		frappe_api._dict.side_effect = real_frappe._dict
		frappe_api.db.exists.side_effect = lambda doctype, *args, **kwargs: doctype == "Survey"
		frappe_api.get_doc.return_value = real_frappe._dict(name="LEGACY-1", cycle="", questions=[])
		frappe_api.ValidationError = real_frappe.ValidationError
		frappe_api.throw.side_effect = real_frappe.ValidationError

		with self.assertRaises(real_frappe.ValidationError):
			unwrap(submit_survey)("LEGACY-1", {"q1": 4})
		self.assertIn("no longer available", frappe_api.throw.call_args[0][0])

	@patch("survey_app.cycle_scope.get_current_cycle", return_value={"name": "SCY-CURRENT"})
	@patch("survey_app.survey_app.doctype.survey_questions.survey_questions.frappe")
	def test_get_survey_json_reports_completed(self, frappe_api, _current):
		from inspect import unwrap

		import frappe as real_frappe

		from survey_app.survey_app.doctype.survey_questions.survey_questions import get_survey_json

		frappe_api._dict.side_effect = real_frappe._dict
		frappe_api.get_doc.return_value = real_frappe._dict(
			title="Review", sub_title="", cycle="SCY-CURRENT", questions=[]
		)
		frappe_api.db.exists.return_value = True

		result = unwrap(get_survey_json)("SURV-001")
		self.assertTrue(result["completed"])

	@patch("survey_app.email_log.send_survey_email")
	@patch("survey_app.outstanding.frappe")
	def test_reminder_skips_when_same_pair_already_answered_elsewhere(self, frappe_api, send_email):
		import frappe as real_frappe

		from survey_app.outstanding import _send_one_reminder

		frappe_api.db.exists.return_value = True
		frappe_api.get_doc.return_value = real_frappe._dict(
			name="SURV-002", rated_by="user@x.com", employee_score="EMP-002"
		)
		frappe_api.db.sql.return_value = [(1,)]

		result = _send_one_reminder("SURV-002")

		self.assertEqual(result["status"], "already_completed")
		send_email.assert_not_called()

from inspect import signature
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from survey_app.my_surveys import (
	_get_result_trend,
	_get_results,
	_normalise_activity_filter,
	get_my_dashboard,
)
from survey_app.performance import aggregate_rows, build_employee_scorecard, percentile_rank
from survey_app.permissions import require_survey_admin


class TestMySurveysDashboard(FrappeTestCase):
	def tearDown(self):
		frappe.set_user("Administrator")
		super().tearDown()

	def test_guest_is_rejected(self):
		frappe.set_user("Guest")
		with self.assertRaises(frappe.PermissionError):
			get_my_dashboard()

	def test_api_does_not_accept_an_employee_identifier(self):
		self.assertEqual(
			list(signature(get_my_dashboard).parameters),
			["period_key", "from_date", "to_date"],
		)

	@patch.object(frappe.db, "get_value", return_value=None)
	def test_unmapped_user_receives_safe_state(self, _get_value):
		frappe.set_user("unmapped.employee@example.com")
		result = get_my_dashboard()
		self.assertEqual(result["state"], "no_employee")
		self.assertIsNone(result["profile"])

	@patch.object(frappe.db, "get_value")
	def test_inactive_employee_receives_safe_state(self, get_value):
		frappe.set_user("inactive.employee@example.com")
		get_value.return_value = frappe._dict(
			{
				"name": "EMP-INACTIVE",
				"employee_name": "Inactive Employee",
				"designation": "",
				"department": "",
				"image": "",
				"status": "Left",
			}
		)
		result = get_my_dashboard()
		self.assertEqual(result["state"], "inactive_employee")
		self.assertEqual(result["profile"]["status"], "Left")

	def test_open_cycle_results_remain_locked(self):
		results = _get_results(
			"EMP-PRIVATE",
			selected_period=None,
			active_cycle={"name": "SCY-OPEN", "is_reviewee": True},
		)
		self.assertEqual(results["state"], "locked")
		self.assertNotIn("overall_pct", results)

	@patch("survey_app.my_surveys._get_results")
	@patch("survey_app.my_surveys._get_result_trend")
	@patch("survey_app.my_surveys._get_result_periods")
	@patch("survey_app.my_surveys._get_active_cycle")
	@patch("survey_app.my_surveys._get_assignments")
	@patch.object(frappe.db, "get_value")
	def test_session_user_is_the_only_employee_lookup(
		self,
		get_value,
		get_assignments,
		get_active_cycle,
		get_result_periods,
		get_result_trend,
		get_results,
	):
		user = "dashboard.employee@example.com"
		frappe.set_user(user)
		get_value.return_value = frappe._dict(
			{
				"name": "EMP-PRIVATE",
				"employee_name": "Private Employee",
				"designation": "Analyst",
				"department": "Operations",
				"image": "",
				"status": "Active",
			}
		)
		get_assignments.return_value = {
				"pending_count": 0,
				"completed_count": 0,
				"pending": [],
				"recent_completed": [],
				"filter_active": False,
		}
		get_active_cycle.return_value = None
		get_result_periods.return_value = []
		get_results.return_value = {"state": "empty"}
		get_result_trend.return_value = []

		result = get_my_dashboard(from_date="2026-07-01", to_date="2026-07-31")

		get_value.assert_called_once_with(
			"Employee",
			{"user_id": user},
			["name", "employee_name", "designation", "department", "image", "status"],
			as_dict=True,
		)
		get_assignments.assert_called_once_with(user, "2026-07-01", "2026-07-31")
		get_active_cycle.assert_called_once_with("EMP-PRIVATE")
		get_result_periods.assert_called_once_with("EMP-PRIVATE")
		self.assertEqual(result["profile"]["employee_name"], "Private Employee")
		self.assertNotIn("name", result["profile"])
		self.assertEqual(result["activity_filter"]["from_date"], "2026-07-01")

	@patch("survey_app.my_surveys._get_result_periods")
	@patch("survey_app.my_surveys._get_active_cycle", return_value=None)
	@patch("survey_app.my_surveys._get_assignments")
	@patch.object(frappe.db, "get_value")
	def test_foreign_or_unknown_period_is_rejected(
		self,
		get_value,
		get_assignments,
		_get_active_cycle,
		get_result_periods,
	):
		frappe.set_user("dashboard.employee@example.com")
		get_value.return_value = frappe._dict(
			{
				"name": "EMP-PRIVATE",
				"employee_name": "Private Employee",
				"designation": "",
				"department": "",
				"image": "",
				"status": "Active",
			}
		)
		get_assignments.return_value = {
			"pending_count": 0,
			"completed_count": 0,
			"pending": [],
			"recent_completed": [],
			"filter_active": False,
		}
		get_result_periods.return_value = [
			{"key": "SCY-ALLOWED", "type": "cycle", "label": "Allowed"}
		]

		with self.assertRaises(frappe.PermissionError):
			get_my_dashboard("SCY-ANOTHER-EMPLOYEE")

	def test_activity_filter_validates_and_normalises_dates(self):
		self.assertEqual(
			_normalise_activity_filter("2026-07-01", "2026-07-31"),
			{"from_date": "2026-07-01", "to_date": "2026-07-31", "active": True},
		)
		self.assertEqual(
			_normalise_activity_filter(),
			{"from_date": "", "to_date": "", "active": False},
		)
		with self.assertRaises(frappe.ValidationError):
			_normalise_activity_filter("2026-08-01", "2026-07-01")

	@patch("survey_app.my_surveys._get_results")
	def test_result_trend_contains_released_aggregate_points_only(self, get_results):
		get_results.side_effect = [
			{"state": "empty"},
			{
				"state": "released",
				"overall_pct": 84.0,
				"org_overall_avg": 78.0,
				"reviewer_count": 4,
			},
		]
		periods = [
			{"key": "SCY-NEW", "label": "New", "period_end": "2026-06-30"},
			{"key": "SCY-OLD", "label": "Old", "period_end": "2026-03-31"},
		]

		trend = _get_result_trend("EMP-PRIVATE", periods)

		self.assertEqual(len(trend), 1)
		self.assertEqual(trend[0]["key"], "SCY-NEW")
		self.assertEqual(trend[0]["overall_pct"], 84.0)
		self.assertNotIn("categories", trend[0])

	def test_score_aggregation_and_percentile(self):
		rows = [
			frappe._dict(
				category="Leadership", selection_score=0, column_score=4, response_name="RESP-1"
			),
			frappe._dict(
				category="Leadership", selection_score=0, column_score=3, response_name="RESP-2"
			),
			frappe._dict(
				category="Teamwork", selection_score=5, column_score=0, response_name="RESP-2"
			),
		]
		aggregated = aggregate_rows(rows)
		self.assertTrue(aggregated["has_data"])
		self.assertEqual(aggregated["overall_pct"], 80.0)
		self.assertEqual(aggregated["response_count"], 2)
		self.assertEqual(percentile_rank(80, [40, 60, 80, 90]), 62.0)

	@patch("survey_app.performance.frappe.db.count", return_value=3)
	@patch("survey_app.performance._has_cycle_pairs", return_value=True)
	@patch("survey_app.performance.get_org_benchmarks")
	@patch("survey_app.performance._previous_closed_cycle")
	@patch("survey_app.performance.get_score_rows")
	def test_cycle_scorecard_uses_previous_closed_cycle(
		self,
		get_score_rows,
		previous_closed_cycle,
		get_org_benchmarks,
		_has_cycle_pairs,
		_db_count,
	):
		current = [
			frappe._dict(
				category="Leadership", selection_score=0, column_score=4, response_name="RESP-1"
			)
		]
		previous = [
			frappe._dict(
				category="Leadership", selection_score=0, column_score=3, response_name="RESP-0"
			)
		]
		get_score_rows.side_effect = [current, previous]
		previous_closed_cycle.return_value = frappe._dict(
			name="SCY-PREVIOUS", period_start="2026-01-01", period_end="2026-03-31"
		)
		get_org_benchmarks.return_value = {
			"overall_scores": [60.0, 80.0, 90.0],
			"overall_avg": 76.7,
			"employee_count": 3,
			"category_scores": {"Leadership": [60.0, 80.0, 90.0]},
		}

		scorecard = build_employee_scorecard(
			"EMP-PRIVATE",
			"2026-04-01",
			"2026-06-30",
			cycle="SCY-CURRENT",
		)

		self.assertEqual(scorecard["overall_pct"], 80.0)
		self.assertEqual(scorecard["delta"], 20.0)
		self.assertEqual(scorecard["reviewer_count"], 1)
		self.assertEqual(scorecard["expected_reviews"], 3)
		self.assertEqual(scorecard["categories"][0]["org_avg"], 76.7)

	def test_survey_admin_guard_rejects_employee_and_accepts_hr(self):
		frappe.set_user("dashboard.employee@example.com")
		with patch("survey_app.permissions.frappe.get_roles", return_value=["All", "Employee"]):
			with self.assertRaises(frappe.PermissionError):
				require_survey_admin()

		with patch("survey_app.permissions.frappe.get_roles", return_value=["All", "HR Manager"]):
			require_survey_admin()

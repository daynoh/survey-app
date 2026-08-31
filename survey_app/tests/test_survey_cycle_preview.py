from inspect import unwrap
from unittest import TestCase
from unittest.mock import patch

import frappe

from survey_app.survey_cycle import preview_cycle_assignments


class TestSurveyCycleAssignmentPreview(TestCase):
	@patch("survey_app.survey_cycle.build_required_pairs")
	@patch("survey_app.survey_cycle.resolve_org_roles")
	@patch("survey_app.survey_cycle.frappe")
	def test_calculated_preview_includes_names_departments_and_loads(
		self,
		frappe_api,
		resolve_org_roles,
		build_required_pairs,
	):
		frappe_api.db.get_value.return_value = None
		frappe_api._dict.side_effect = frappe._dict
		resolve_org_roles.return_value = {"warnings": ["Missing team leader"]}
		build_required_pairs.return_value = [
			{"reviewer": "EMP-001", "reviewee": "EMP-002", "rule_type": "Nearness"},
			{"reviewer": "EMP-001", "reviewee": "EMP-003", "rule_type": "Peer"},
		]
		frappe_api.get_all.return_value = [
			frappe._dict(name="EMP-001", employee_name="Reviewer One", department="Finance"),
			frappe._dict(name="EMP-002", employee_name="Reviewee Two", department="HR"),
			frappe._dict(name="EMP-003", employee_name="Reviewee Three", department="Finance"),
		]

		result = unwrap(preview_cycle_assignments)()

		self.assertEqual(result["source"], "calculated")
		self.assertFalse(result["is_cycle_plan"])
		self.assertEqual(result["summary"]["total_pairs"], 2)
		self.assertEqual(result["summary"]["maximum_load"], 2)
		self.assertEqual(result["summary"]["reviewees"], 2)
		self.assertEqual(result["rows"][0]["reviewer_name"], "Reviewer One")
		self.assertEqual(result["rows"][0]["reviewer_department"], "Finance")
		self.assertEqual(result["rows"][0]["reviewer_cycle_load"], 2)
		self.assertEqual(result["by_rule"], {"Nearness": 1, "Peer": 1})
		self.assertEqual(result["warnings"], ["Missing team leader"])

	@patch("survey_app.survey_cycle.resolve_org_roles", return_value={"warnings": []})
	@patch("survey_app.survey_cycle.frappe")
	def test_open_cycle_preview_uses_stored_pairs(
		self,
		frappe_api,
		_resolve_org_roles,
	):
		frappe_api.db.get_value.return_value = "SCY-2026-00001"
		frappe_api._dict.side_effect = frappe._dict
		frappe_api.get_doc.return_value = frappe._dict(
			name="SCY-2026-00001",
			title="Q3 Baseline",
			status="Open",
			current_batch=1,
			pairs=[
				frappe._dict(
					reviewer="EMP-010",
					reviewee="EMP-011",
					rule_type="TeamLeader",
					status="Assigned",
					batch_no=1,
				)
			],
		)
		frappe_api.get_all.return_value = [
			frappe._dict(name="EMP-010", employee_name="Team Leader", department="Legal"),
			frappe._dict(name="EMP-011", employee_name="Team Member", department="Legal"),
		]

		result = unwrap(preview_cycle_assignments)()

		self.assertTrue(result["is_cycle_plan"])
		self.assertEqual(result["cycle"]["name"], "SCY-2026-00001")
		self.assertEqual(result["rows"][0]["status"], "Assigned")
		self.assertEqual(result["rows"][0]["batch_no"], 1)
		self.assertEqual(result["rows"][0]["reviewee_coverage"], 1)

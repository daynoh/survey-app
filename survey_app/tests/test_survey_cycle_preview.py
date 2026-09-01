from inspect import unwrap
from unittest import TestCase
from unittest.mock import MagicMock, patch

import frappe

from survey_app.survey_cycle import (
	get_unsent_invitations,
	preview_cycle_assignments,
	preview_cycle_load,
	purge_excluded_pairs,
	resend_survey_invitation,
)


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
		frappe_api.get_doc.return_value = frappe._dict()
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
		self.assertIsNone(result["exclusion_conflicts"])
		self.assertEqual(result["excluded_people"], [])

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

	@patch("survey_app.survey_cycle._batches_remaining", return_value=13)
	@patch("survey_app.survey_cycle._cycle_period", return_value=("2026-07-01", "2026-09-30"))
	@patch("survey_app.survey_cycle.build_required_pairs")
	@patch("survey_app.survey_cycle.resolve_org_roles")
	@patch("survey_app.survey_cycle.frappe")
	def test_load_preview_includes_review_only_employees(
		self,
		frappe_api,
		resolve_org_roles,
		build_required_pairs,
		_cycle_period,
		_batches_remaining,
	):
		frappe_api._dict.side_effect = frappe._dict
		frappe_api.get_doc.return_value = frappe._dict(
			generation_frequency="Weekly",
			completeness_cycle="Quarterly",
		)
		resolve_org_roles.return_value = {"warnings": []}
		build_required_pairs.return_value = [
			{"reviewer": "EMP-001", "reviewee": "EMP-002", "rule_type": "Peer"},
			{"reviewer": "EMP-001", "reviewee": "EMP-003", "rule_type": "Nearness"},
			{"reviewer": "EMP-002", "reviewee": "EMP-003", "rule_type": "Peer"},
		]
		frappe_api.get_all.return_value = [
			frappe._dict(name="EMP-001", employee_name="Alice", department="Finance"),
			frappe._dict(name="EMP-002", employee_name="Bob", department="Finance"),
			frappe._dict(name="EMP-003", employee_name="MD Person", department="EXCO"),
		]

		result = unwrap(preview_cycle_load)()

		rows = {row["reviewer"]: row for row in result["load"]}
		self.assertFalse(rows["EMP-001"]["review_only"])
		self.assertEqual(rows["EMP-001"]["reviews_received"], 0)
		self.assertEqual(rows["EMP-003"]["required_surveys"], 0)
		self.assertTrue(rows["EMP-003"]["review_only"])
		self.assertEqual(rows["EMP-003"]["reviews_received"], 2)

	@patch("survey_app.survey_cycle.resolve_org_roles", return_value={"warnings": []})
	@patch("survey_app.survey_cycle.frappe")
	def test_cycle_preview_flags_exclusion_conflicts(self, frappe_api, _resolve_org_roles):
		frappe_api._dict.side_effect = frappe._dict
		cycle_doc = frappe._dict(
			name="SCY-2026-00001",
			title="Q3",
			status="Open",
			current_batch=0,
			pairs=[
				frappe._dict(reviewer="EMP-010", reviewee="EMP-011", rule_type="TeamLeader", status="Planned", batch_no=0),
				frappe._dict(reviewer="EMP-011", reviewee="EMP-012", rule_type="Peer", status="Assigned", batch_no=1),
				frappe._dict(reviewer="EMP-012", reviewee="EMP-010", rule_type="Peer", status="Planned", batch_no=0),
			],
		)

		def fake_get_doc(doctype, name=None, **kwargs):
			if doctype == "Value Scoring Settings":
				excluded = [frappe._dict(user="excluded@actserv.co.ke")]
				return frappe._dict(exclude_rated=excluded, exclude_rating=excluded)
			return cycle_doc

		frappe_api.get_doc.side_effect = fake_get_doc
		frappe_api.db.get_value.return_value = "SCY-2026-00001"

		def fake_get_all(doctype, filters=None, fields=None, **kwargs):
			if filters and "user_id" in filters:
				return ["EMP-011"]
			if filters and "name" in filters:
				rows = {
					"EMP-010": frappe._dict(name="EMP-010", employee_name="Clean One", department="Finance"),
					"EMP-011": frappe._dict(name="EMP-011", employee_name="Excluded Person", department="HR"),
					"EMP-012": frappe._dict(name="EMP-012", employee_name="Clean Two", department="HR"),
				}
				return [rows[n] for n in filters["name"][1] if n in rows]
			return []

		frappe_api.get_all.side_effect = fake_get_all

		result = unwrap(preview_cycle_assignments)()

		conflicts = result["exclusion_conflicts"]
		self.assertEqual(conflicts["total"], 2)
		self.assertEqual(conflicts["planned"], 1)
		self.assertEqual(conflicts["assigned"], 1)
		self.assertEqual(conflicts["employees"], ["EMP-011"])
		self.assertTrue(any("excluded" in w for w in result["warnings"]))
		self.assertEqual(len(result["excluded_people"]), 1)
		person = result["excluded_people"][0]
		self.assertEqual(person["employee"], "EMP-011")
		self.assertTrue(person["cannot_rate"])
		self.assertTrue(person["cannot_be_rated"])
		self.assertTrue(any(row["reviewer"] == "EMP-011" for row in result["load"]))

	@patch("survey_app.survey_cycle.resolve_org_roles", return_value={"md": None, "team_leaders": [], "warnings": []})
	@patch("survey_app.survey_cycle.frappe")
	def test_purge_excluded_pairs_removes_only_planned(self, frappe_api, _resolve_org_roles):
		frappe_api._dict.side_effect = frappe._dict
		cycle_doc = frappe._dict(
			name="SCY-2026-00001",
			total_pairs=3,
			flags=frappe._dict(),
			pairs=[
				frappe._dict(reviewer="EMP-010", reviewee="EMP-011", rule_type="TeamLeader", status="Planned", batch_no=0),
				frappe._dict(reviewer="EMP-011", reviewee="EMP-012", rule_type="Peer", status="Assigned", batch_no=1),
				frappe._dict(reviewer="EMP-012", reviewee="EMP-010", rule_type="Peer", status="Planned", batch_no=0),
			],
		)
		cycle_doc.save = MagicMock()

		def fake_get_doc(doctype, name=None, **kwargs):
			if doctype == "Value Scoring Settings":
				excluded = [frappe._dict(user="excluded@actserv.co.ke")]
				return frappe._dict(exclude_rated=excluded, exclude_rating=excluded)
			return cycle_doc

		frappe_api.get_doc.side_effect = fake_get_doc
		frappe_api.db.get_value.return_value = "SCY-2026-00001"
		frappe_api.get_all.side_effect = (
			lambda doctype, filters=None, fields=None, **kwargs: ["EMP-011"] if filters and "user_id" in filters else []
		)

		result = unwrap(purge_excluded_pairs)()

		self.assertEqual(result["cycle"], "SCY-2026-00001")
		self.assertEqual(result["removed"], 1)
		self.assertEqual(result["kept_assigned_or_completed"], 1)
		self.assertEqual(result["remaining_pairs"], 2)
		self.assertEqual(len(cycle_doc.pairs), 2)
		self.assertEqual(cycle_doc.total_pairs, 2)
		cycle_doc.save.assert_called_once()
		frappe_api.db.commit.assert_called_once()

	@patch("survey_app.survey_cycle.resolve_org_roles", return_value={"md": None, "team_leaders": [], "warnings": []})
	@patch("survey_app.survey_cycle.frappe")
	def test_cycle_preview_flags_exco_circle_conflicts(self, frappe_api, _resolve_org_roles):
		frappe_api._dict.side_effect = frappe._dict
		cycle_doc = frappe._dict(
			name="SCY-2026-00001",
			title="Q3",
			status="Open",
			current_batch=0,
			pairs=[
				frappe._dict(reviewer="EMP-010", reviewee="EMP-011", rule_type="Peer", status="Planned", batch_no=0),
				frappe._dict(reviewer="EMP-011", reviewee="EMP-012", rule_type="Nearness", status="Planned", batch_no=0),
				frappe._dict(reviewer="EMP-012", reviewee="EMP-011", rule_type="Peer", status="Assigned", batch_no=1),
				frappe._dict(reviewer="EMP-010", reviewee="EMP-012", rule_type="Peer", status="Planned", batch_no=0),
			],
		)

		def fake_get_doc(doctype, name=None, **kwargs):
			if doctype == "Value Scoring Settings":
				return frappe._dict(
					exclude_rated=[],
					exclude_rating=[],
					exco_oversight=[frappe._dict(employee="EMP-011", department="Finance")],
				)
			return cycle_doc

		frappe_api.get_doc.side_effect = fake_get_doc
		frappe_api.db.get_value.return_value = "SCY-2026-00001"

		def fake_get_all(doctype, filters=None, fields=None, **kwargs):
			if filters and "name" in filters:
				rows = {
					"EMP-010": frappe._dict(name="EMP-010", employee_name="Teammate One", department="Finance"),
					"EMP-011": frappe._dict(name="EMP-011", employee_name="Exco Person", department="Finance"),
					"EMP-012": frappe._dict(name="EMP-012", employee_name="Outsider", department="HR"),
				}
				return [rows[n] for n in filters["name"][1] if n in rows]
			return []

		frappe_api.get_all.side_effect = fake_get_all

		result = unwrap(preview_cycle_assignments)()

		conflicts = result["exco_conflicts"]
		self.assertEqual(conflicts["total"], 2)
		self.assertEqual(conflicts["planned"], 1)
		self.assertEqual(conflicts["assigned"], 1)
		self.assertEqual(conflicts["employees"], ["EMP-011"])
		self.assertTrue(any("EXCO" in w for w in result["warnings"]))

	@patch("survey_app.survey_cycle.resolve_org_roles", return_value={"md": None, "team_leaders": [], "warnings": []})
	@patch("survey_app.survey_cycle.frappe")
	def test_purge_drops_planned_pairs_outside_the_exco_circle(self, frappe_api, _resolve_org_roles):
		frappe_api._dict.side_effect = frappe._dict
		cycle_doc = frappe._dict(
			name="SCY-2026-00001",
			total_pairs=3,
			flags=frappe._dict(),
			pairs=[
				frappe._dict(reviewer="EMP-011", reviewee="EMP-012", rule_type="Nearness", status="Planned", batch_no=0),
				frappe._dict(reviewer="EMP-010", reviewee="EMP-011", rule_type="Peer", status="Planned", batch_no=0),
				frappe._dict(reviewer="EMP-012", reviewee="EMP-011", rule_type="Peer", status="Assigned", batch_no=1),
			],
		)
		cycle_doc.save = MagicMock()

		def fake_get_doc(doctype, name=None, **kwargs):
			if doctype == "Value Scoring Settings":
				return frappe._dict(
					exclude_rated=[],
					exclude_rating=[],
					exco_oversight=[frappe._dict(employee="EMP-011", department="Finance")],
				)
			return cycle_doc

		frappe_api.get_doc.side_effect = fake_get_doc
		frappe_api.db.get_value.return_value = "SCY-2026-00001"

		def fake_get_all(doctype, filters=None, fields=None, **kwargs):
			if filters and "name" in filters:
				rows = {
					"EMP-010": frappe._dict(name="EMP-010", employee_name="Teammate One", department="Finance"),
					"EMP-011": frappe._dict(name="EMP-011", employee_name="Exco Person", department="Finance"),
					"EMP-012": frappe._dict(name="EMP-012", employee_name="Outsider", department="HR"),
				}
				return [rows[n] for n in filters["name"][1] if n in rows]
			return []

		frappe_api.get_all.side_effect = fake_get_all

		result = unwrap(purge_excluded_pairs)()

		self.assertEqual(result["removed"], 1)
		self.assertEqual(result["exco_removed"], 1)
		self.assertEqual(result["kept_assigned_or_completed"], 1)
		self.assertEqual(result["remaining_pairs"], 2)
		cycle_doc.save.assert_called_once()
		frappe_api.db.commit.assert_called_once()


class TestCycleLoadBatchWindow(TestCase):
	@patch("survey_app.survey_cycle._batches_remaining", return_value=4)
	@patch("survey_app.survey_cycle._cycle_period", return_value=("2026-07-01", "2026-09-30"))
	@patch("survey_app.survey_cycle.build_required_pairs")
	@patch("survey_app.survey_cycle.resolve_org_roles")
	@patch("survey_app.survey_cycle.frappe")
	def test_load_preview_compresses_batches_to_calendar_window(
		self,
		frappe_api,
		resolve_org_roles,
		build_required_pairs,
		_cycle_period,
		_batches_remaining,
	):
		frappe_api._dict.side_effect = frappe._dict
		frappe_api.get_doc.return_value = frappe._dict(
			generation_frequency="Weekly",
			completeness_cycle="Quarterly",
		)
		resolve_org_roles.return_value = {"warnings": []}
		build_required_pairs.return_value = [
			{"reviewer": "EMP-001", "reviewee": "EMP-002", "rule_type": "Peer"},
		]
		frappe_api.get_all.return_value = [
			frappe._dict(name="EMP-001", employee_name="Alice", department="Finance"),
			frappe._dict(name="EMP-002", employee_name="Bob", department="Finance"),
		]

		result = unwrap(preview_cycle_load)()

		self.assertEqual(result["batches_total"], 13)
		self.assertEqual(result["calendar_batches_left"], 4)
		self.assertEqual(result["batches_in_cycle"], 4)
		self.assertTrue(result["batch_window_note"])
		self.assertIn("2026-09-30", result["batch_window_note"])


class TestApplyRulesAndUnsentInvitations(TestCase):
	@patch("survey_app.survey_cycle.resolve_org_roles", return_value={"md": None, "team_leaders": [], "warnings": []})
	@patch("survey_app.survey_cycle.frappe")
	def test_purge_grafts_missing_exco_circle_pairs(self, frappe_api, _resolve_org_roles):
		frappe_api._dict.side_effect = frappe._dict
		cycle_doc = frappe._dict(
			name="SCY-2026-00001",
			total_pairs=2,
			flags=frappe._dict(),
			pairs=[
				frappe._dict(reviewer="EMP-011", reviewee="EMP-012", rule_type="Nearness", status="Planned", batch_no=0),
				frappe._dict(reviewer="EMP-010", reviewee="EMP-011", rule_type="Peer", status="Planned", batch_no=0),
			],
		)
		cycle_doc.save = MagicMock()

		def fake_get_doc(doctype, name=None, **kwargs):
			if doctype == "Value Scoring Settings":
				return frappe._dict(
					exclude_rated=[],
					exclude_rating=[],
					exco_oversight=[frappe._dict(employee="EMP-011", department="Finance")],
				)
			return cycle_doc

		frappe_api.get_doc.side_effect = fake_get_doc
		frappe_api.db.get_value.return_value = "SCY-2026-00001"

		def fake_get_all(doctype, filters=None, fields=None, **kwargs):
			if filters and "name" in filters:
				rows = {
					"EMP-010": frappe._dict(name="EMP-010", employee_name="Teammate", department="Finance"),
					"EMP-011": frappe._dict(name="EMP-011", employee_name="Exco", department="Finance"),
					"EMP-012": frappe._dict(name="EMP-012", employee_name="Outsider", department="HR"),
				}
				return [rows[n] for n in filters["name"][1] if n in rows]
			if filters and "status" in filters:
				return [
					frappe._dict(name="EMP-010", employee_name="Teammate", department="Finance"),
					frappe._dict(name="EMP-011", employee_name="Exco", department="Finance"),
					frappe._dict(name="EMP-012", employee_name="Outsider", department="HR"),
				]
			return []

		frappe_api.get_all.side_effect = fake_get_all

		result = unwrap(purge_excluded_pairs)()

		self.assertEqual(result["removed"], 1)
		self.assertEqual(result["grafted"], 1)
		self.assertEqual(result["remaining_pairs"], 2)
		self.assertEqual(cycle_doc.total_pairs, 2)
		cycle_doc.save.assert_called_once()

	@patch("survey_app.survey_cycle.frappe")
	def test_get_unsent_invitations_flags_missing_invites(self, frappe_api):
		frappe_api._dict.side_effect = frappe._dict
		cycle_doc = frappe._dict(
			name="SCY-2026-00001",
			pairs=[
				frappe._dict(reviewer="EMP-010", reviewee="EMP-012", rule_type="Peer", status="Assigned", batch_no=1, survey="SURV-001"),
				frappe._dict(reviewer="EMP-011", reviewee="EMP-012", rule_type="Peer", status="Assigned", batch_no=1, survey="SURV-002"),
				frappe._dict(reviewer="EMP-010", reviewee="EMP-011", rule_type="Peer", status="Planned", batch_no=0, survey=None),
			],
		)

		def fake_get_doc(doctype, name=None, **kwargs):
			return cycle_doc

		frappe_api.get_doc.side_effect = fake_get_doc
		frappe_api.db.get_value.return_value = "SCY-2026-00001"

		def fake_get_value(doctype, name, fields=None, **kwargs):
			if doctype == "Employee":
				data = {
					"EMP-010": frappe._dict(employee_name="Has User", user_id="has.user@x.com"),
					"EMP-011": frappe._dict(employee_name="No User", user_id=None),
					"EMP-012": frappe._dict(employee_name="Reviewee", user_id=None),
				}
				return data.get(name)
			if doctype == "User":
				return frappe._dict(enabled=1, name=name)
			return None

		frappe_api.db.get_value.side_effect = fake_get_value

		def fake_get_all(doctype, filters=None, fields=None, **kwargs):
			if doctype == "Survey Email Log":
				return ["SURV-001"]
			return []

		frappe_api.get_all.side_effect = fake_get_all

		result = unwrap(get_unsent_invitations)()

		self.assertEqual(result["total"], 1)
		row = result["rows"][0]
		self.assertEqual(row["survey"], "SURV-002")
		self.assertEqual(row["reviewer"], "EMP-011")
		self.assertFalse(row["resendable"])
		self.assertIn("No ERP user", row["reason"])

	@patch("survey_app.survey_cycle.send_survey_notification_and_task")
	@patch("survey_app.survey_cycle.frappe")
	def test_resend_survey_invitation_requires_linked_user(self, frappe_api, _send_notification):
		frappe_api._dict.side_effect = frappe._dict

		def fake_get_value(doctype, name, fields=None, **kwargs):
			if doctype == "Employee" and fields == "user_id":
				return None
			return True

		frappe_api.db.get_value.side_effect = fake_get_value
		frappe_api.db.exists.return_value = True

		with self.assertRaises(frappe.ValidationError):
			unwrap(resend_survey_invitation)("SURV-001", "EMP-011", "EMP-012", cycle="SCY-2026-00001")
		_send_notification.assert_not_called()

		def fake_get_value_ok(doctype, name, fields=None, **kwargs):
			if doctype == "Employee" and fields == "user_id":
				return "has.user@x.com"
			return True

		frappe_api.db.get_value.side_effect = fake_get_value_ok
		result = unwrap(resend_survey_invitation)("SURV-001", "EMP-010", "EMP-012", cycle="SCY-2026-00001")
		self.assertEqual(result["status"], "sent")
		_send_notification.assert_called_once()

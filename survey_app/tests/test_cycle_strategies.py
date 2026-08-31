from collections import Counter
from unittest import TestCase
from unittest.mock import patch

import frappe

from survey_app import survey_cycle


class TestCycleStrategies(TestCase):
	def setUp(self):
		self.employees = [
			frappe._dict(name="A1", employee_name="A1", department="A"),
			frappe._dict(name="A2", employee_name="A2", department="A"),
			frappe._dict(name="A3", employee_name="A3", department="A"),
			frappe._dict(name="B1", employee_name="B1", department="B"),
			frappe._dict(name="B2", employee_name="B2", department="B"),
			frappe._dict(name="B3", employee_name="B3", department="B"),
		]
		self.factors = [
			frappe._dict(department="A", department2="B", factor=1),
			frappe._dict(department="B", department2="A", factor=1),
		]
		self.roles = {"md": None, "team_leaders": [], "warnings": []}

	def _strategy_context(self, target=4, cap=5, baseline_target=10):
		settings = frappe._dict(
			balanced_reviews_per_employee=target,
			balanced_max_surveys_per_reviewer=cap,
			max_surveys_per_employee=baseline_target,
		)
		return (
			patch.object(survey_cycle, "_settings", return_value=settings),
			patch.object(survey_cycle, "_excluded_employees", return_value=(set(), set())),
			patch.object(survey_cycle, "_active_employees", return_value=self.employees),
			patch.object(survey_cycle.frappe, "get_all", return_value=self.factors),
		)

	def test_balanced_coverage_hits_target_without_exceeding_reviewer_cap(self):
		patches = self._strategy_context()
		with patches[0], patches[1], patches[2], patches[3]:
			pairs = survey_cycle.build_required_pairs(
				self.roles,
				strategy=survey_cycle.BALANCED_STRATEGY,
				cycle_key="balanced-test-cycle",
			)

		self.assertEqual(len(pairs), 24)
		self.assertEqual(len({(pair["reviewer"], pair["reviewee"]) for pair in pairs}), 24)
		self.assertEqual(set(Counter(pair["reviewee"] for pair in pairs).values()), {4})
		self.assertLessEqual(max(Counter(pair["reviewer"] for pair in pairs).values()), 5)

	def test_full_baseline_preserves_all_peer_and_eligible_external_pairs(self):
		patches = self._strategy_context()
		with patches[0], patches[1], patches[2], patches[3]:
			pairs = survey_cycle.build_required_pairs(
				self.roles,
				strategy=survey_cycle.FULL_BASELINE_STRATEGY,
				cycle_key="baseline-test-cycle",
			)

		# Twelve directed peer pairs plus every directed cross-department pair (18 total).
		self.assertEqual(len(pairs), 30)
		self.assertEqual(len({(pair["reviewer"], pair["reviewee"]) for pair in pairs}), 30)
		self.assertEqual(Counter(pair["rule_type"] for pair in pairs), {"Peer": 12, "Nearness": 18})

	def test_mandatory_leadership_assignments_can_exceed_balanced_safety_cap(self):
		roles = {
			"md": None,
			"team_leaders": [{"department": "A", "employee": "A1"}],
			"warnings": [],
		}
		patches = self._strategy_context(target=1, cap=1)
		with patches[0], patches[1], patches[2], patches[3]:
			pairs = survey_cycle.build_required_pairs(
				roles,
				strategy=survey_cycle.BALANCED_STRATEGY,
				cycle_key="leadership-test-cycle",
			)

		leader_assignments = [pair for pair in pairs if pair["reviewer"] == "A1"]
		self.assertEqual(len(leader_assignments), 2)
		self.assertEqual(
			{pair["reviewee"] for pair in leader_assignments if pair["rule_type"] == "TeamLeader"},
			{"A2", "A3"},
		)

	def test_cycle_strategy_locks_after_assignment_or_batch_activity(self):
		self.assertFalse(
			survey_cycle._cycle_strategy_locked(
				frappe._dict(current_batch=0, assigned_pairs=0, pairs=[frappe._dict(status="Planned")])
			)
		)
		self.assertTrue(
			survey_cycle._cycle_strategy_locked(
				frappe._dict(current_batch=1, assigned_pairs=0, pairs=[frappe._dict(status="Planned")])
			)
		)

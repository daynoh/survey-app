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

	# ------------------------------------------------------------------
	# EXCO oversight circle
	# ------------------------------------------------------------------

	def _exco_employees(self):
		return self.employees + [
			frappe._dict(name="X1", employee_name="Exco One", department="A"),
			frappe._dict(name="X2", employee_name="Exco Two", department="B"),
		]

	def _exco_patches(
		self,
		exco_oversight,
		excluded=(set(), set()),
		employees=None,
		target=4,
		cap=10,
		baseline_target=10,
	):
		settings = frappe._dict(
			balanced_reviews_per_employee=target,
			balanced_max_surveys_per_reviewer=cap,
			max_surveys_per_employee=baseline_target,
			exco_oversight=exco_oversight,
		)
		return (
			patch.object(survey_cycle, "_settings", return_value=settings),
			patch.object(survey_cycle, "_excluded_employees", return_value=excluded),
			patch.object(survey_cycle, "_active_employees", return_value=employees or self._exco_employees()),
			patch.object(survey_cycle.frappe, "get_all", return_value=self.factors),
		)

	def _exco_rows(self):
		return [
			frappe._dict(employee="X1", department="A"),
			frappe._dict(employee="X2", department="B"),
		]

	def test_full_baseline_keeps_exco_out_of_generic_pools_and_adds_circle_pairs(self):
		patches = self._exco_patches(self._exco_rows())
		with patches[0], patches[1], patches[2], patches[3]:
			pairs = survey_cycle.build_required_pairs(
				self.roles,
				strategy=survey_cycle.FULL_BASELINE_STRATEGY,
				cycle_key="baseline-exco-cycle",
			)

		exco = {"X1", "X2"}
		self.assertEqual(
			Counter(pair["rule_type"] for pair in pairs),
			{"Peer": 12, "Nearness": 18, "Exco Oversight": 12, "Exco Peer": 2},
		)
		for pair in pairs:
			if pair["rule_type"] in ("Peer", "Nearness"):
				self.assertNotIn(pair["reviewer"], exco)
				self.assertNotIn(pair["reviewee"], exco)
		# Whole supervised team, both ways, for each EXCO member.
		x1_oversight = {
			(pair["reviewer"], pair["reviewee"])
			for pair in pairs
			if pair["rule_type"] == "Exco Oversight" and "X1" in (pair["reviewer"], pair["reviewee"])
		}
		self.assertEqual(
			x1_oversight,
			{("X1", "A1"), ("A1", "X1"), ("X1", "A2"), ("A2", "X1"), ("X1", "A3"), ("A3", "X1")},
		)
		self.assertIn(("X1", "X2"), {(p["reviewer"], p["reviewee"]) for p in pairs if p["rule_type"] == "Exco Peer"})

	def test_balanced_exco_pairs_are_mandatory_and_within_circle(self):
		patches = self._exco_patches(self._exco_rows(), target=1, cap=1)
		with patches[0], patches[1], patches[2], patches[3]:
			pairs = survey_cycle.build_required_pairs(
				self.roles,
				strategy=survey_cycle.BALANCED_STRATEGY,
				cycle_key="balanced-exco-cycle",
			)

		x1_given = {pair["reviewee"] for pair in pairs if pair["reviewer"] == "X1"}
		x1_received = {pair["reviewer"] for pair in pairs if pair["reviewee"] == "X1"}
		# Mandatory circle pairs bypass the cap of 1 and stay inside the circle.
		self.assertEqual(x1_given, {"A1", "A2", "A3", "X2"})
		self.assertEqual(x1_received, {"A1", "A2", "A3", "X2"})
		for pair in pairs:
			if "X1" in (pair["reviewer"], pair["reviewee"]):
				self.assertTrue(pair["rule_type"].startswith("Exco"))

	def test_exco_members_review_the_md_who_never_reviews_back(self):
		roles = {
			"md": {"name": "MD1", "employee_name": "MD", "department": "MD", "source": "Manual"},
			"team_leaders": [],
			"warnings": [],
		}
		patches = self._exco_patches(self._exco_rows())
		with patches[0], patches[1], patches[2], patches[3]:
			pairs = survey_cycle.build_required_pairs(
				roles,
				strategy=survey_cycle.BALANCED_STRATEGY,
				cycle_key="exco-md-cycle",
			)

		exco_to_md = {
			(pair["reviewer"], pair["reviewee"])
			for pair in pairs
			if pair["rule_type"] == "Exco to MD"
		}
		self.assertEqual(exco_to_md, {("X1", "MD1"), ("X2", "MD1")})
		self.assertNotIn("MD1", {pair["reviewer"] for pair in pairs})

	def test_exclusions_take_precedence_over_the_exco_circle(self):
		# EXCO member excluded from rating still receives reviews but gives none.
		patches = self._exco_patches(self._exco_rows(), excluded=(set(), {"X1"}))
		with patches[0], patches[1], patches[2], patches[3]:
			pairs = survey_cycle.build_required_pairs(
				self.roles,
				strategy=survey_cycle.BALANCED_STRATEGY,
				cycle_key="exco-excluded-reviewer-cycle",
			)
		self.assertNotIn("X1", {pair["reviewer"] for pair in pairs})
		self.assertIn("X1", {pair["reviewee"] for pair in pairs})

		# EXCO member excluded from being rated still gives reviews but receives none.
		patches = self._exco_patches(self._exco_rows(), excluded=({"X1"}, set()))
		with patches[0], patches[1], patches[2], patches[3]:
			pairs = survey_cycle.build_required_pairs(
				self.roles,
				strategy=survey_cycle.BALANCED_STRATEGY,
				cycle_key="exco-excluded-reviewee-cycle",
			)
		self.assertNotIn("X1", {pair["reviewee"] for pair in pairs})
		self.assertIn("X1", {pair["reviewer"] for pair in pairs})

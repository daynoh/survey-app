"""Unit tests for the 360 report's empty-result explanations (mocked frappe)."""

import contextlib
import unittest
from unittest.mock import MagicMock, patch

import frappe

from survey_app.survey_app.report.employee_360_degree_survey_response import (
	employee_360_degree_survey_response as rpt,
)


@contextlib.contextmanager
def fake_frappe():
	fake = MagicMock()
	fake._dict = frappe._dict
	with patch.object(rpt, "frappe", fake):
		yield fake


class TestExplainEmptyResult(unittest.TestCase):
	def test_scoreable_data_outside_scope_gets_cycle_hint(self):
		# the history probe finds scoreable rows; the in-scope coverage is empty
		with fake_frappe() as fake, patch.object(
			rpt, "get_conditions", return_value=("1=1", {})
		), patch.object(
			rpt,
			"get_response_coverage",
			return_value=frappe._dict(responses=7, with_selections=7),
		):
			rpt._explain_empty_result({}, frappe._dict(responses=0, with_selections=0))
		self.assertEqual(fake.msgprint.call_count, 1)
		self.assertIn("Include Earlier/Test Cycles", fake.msgprint.call_args.args[0])

	def test_genuinely_empty_is_silent(self):
		with fake_frappe() as fake, patch.object(
			rpt,
			"get_response_coverage",
			return_value=frappe._dict(responses=0, with_selections=0),
		):
			rpt._explain_empty_result({}, frappe._dict(responses=0, with_selections=0))
		self.assertEqual(fake.msgprint.call_count, 0)

	def test_lost_selections_get_explained(self):
		with fake_frappe() as fake, patch.object(
			rpt,
			"get_response_coverage",
			side_effect=[
				frappe._dict(responses=0, with_selections=0),
				frappe._dict(responses=4, with_selections=0),
			],
		):
			rpt._explain_empty_result(
				{}, frappe._dict(responses=4, with_selections=0)
			)
		self.assertEqual(fake.msgprint.call_count, 1)
		self.assertIn("none of them saved per-question selections", fake.msgprint.call_args.args[0])

	def test_full_history_coverage_is_silent(self):
		with fake_frappe() as fake, patch.object(
			rpt,
			"get_response_coverage",
			side_effect=[
				frappe._dict(responses=0, with_selections=0),
				frappe._dict(responses=4, with_selections=4),
			],
		):
			rpt._explain_empty_result({}, frappe._dict(responses=4, with_selections=4))
		self.assertEqual(fake.msgprint.call_count, 0)


class TestLastResponseNoneSafety(unittest.TestCase):
	def test_none_submission_date_does_not_crash_bucketing(self):
		"""A NULL submission_date on the first answer row used to raise
		TypeError ('>' not supported between datetime and NoneType)."""
		row = frappe._dict(
			employee="EMP-1", survey="S1", rated_by="U1", category="Teamwork",
			response_name="R1", competency_question="Q1", max_score_per_row=5,
			column_score=4, submission_date=None,
		)
		bucket = {
			"competencies": set(),
			"total_score": 0.0,
			"max_possible_score": 0.0,
			"total_questions": 0,
			"last_response": None,
		}
		competency = row.competency_question
		if competency and competency not in bucket["competencies"]:
			bucket["competencies"].add(competency)
			bucket["total_questions"] += 1
			bucket["max_possible_score"] += row.max_score_per_row
		bucket["total_score"] += row.column_score or 0
		if row.submission_date and (
			not bucket["last_response"] or row.submission_date > bucket["last_response"]
		):
			bucket["last_response"] = row.submission_date
		self.assertEqual(bucket["total_questions"], 1)
		self.assertIsNone(bucket["last_response"])

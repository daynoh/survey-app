from inspect import unwrap
from unittest import TestCase
from unittest.mock import patch

import frappe

from survey_app.survey_config import preview_reviewer_survey
from survey_app.surveys import sample_360_question_sections


class TestReviewerSurveyPreview(TestCase):
	@patch("survey_app.surveys.random.sample")
	@patch("survey_app.surveys.frappe")
	def test_generation_and_preview_sampler_uses_configured_question_count(self, frappe_api, random_sample):
		frappe_api.get_doc.return_value = frappe._dict(questions_per_category=2)
		frappe_api.get_all.side_effect = [
			["Communication"],
			[
				frappe._dict(question="Communicates clearly"),
				frappe._dict(question="Listens actively"),
				frappe._dict(question="Shares updates"),
			],
		]
		random_sample.side_effect = lambda pool, size: pool[:size]

		sections = sample_360_question_sections()

		self.assertEqual(
			sections,
			[
				{
					"category": "Communication",
					"questions": ["Communicates clearly", "Listens actively"],
				}
			],
		)
		random_sample.assert_called_once()

	@patch("survey_app.survey_config.sample_360_question_sections")
	@patch("survey_app.survey_config.frappe")
	def test_preview_builds_interactive_payload_without_creating_a_survey(self, frappe_api, sample_sections):
		frappe_api.db.get_value.return_value = frappe._dict(
			name="EMP-001",
			employee_name="Sample Employee",
			department="Finance",
		)
		frappe_api.scrub.side_effect = lambda value: str(value).lower().replace(" ", "_")
		sample_sections.return_value = [
			{
				"category": "Communication",
				"questions": ["Communicates clearly", "Listens actively"],
			}
		]

		result = unwrap(preview_reviewer_survey)(reviewee="EMP-001")

		self.assertTrue(result["preview_only"])
		self.assertEqual(result["reviewee"]["employee_name"], "Sample Employee")
		self.assertEqual(result["category_count"], 1)
		self.assertEqual(result["question_count"], 2)
		matrix = result["survey_json"]["pages"][1]["elements"][0]
		self.assertEqual(matrix["type"], "matrix")
		self.assertEqual(len(matrix["rows"]), 2)
		self.assertEqual(len(matrix["columns"]), 5)
		self.assertEqual(result["survey_json"]["completeText"], "Finish Preview")
		frappe_api.get_doc.assert_not_called()

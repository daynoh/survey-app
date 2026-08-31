import frappe


def execute():
	"""Preserve the meaning of plans created before cycle strategies existed."""
	if not frappe.db.table_exists("Survey Cycle"):
		return
	if not frappe.db.has_column("Survey Cycle", "generation_strategy"):
		return

	frappe.db.sql(
		"""
		UPDATE `tabSurvey Cycle`
		SET generation_strategy = %s
		""",
		("Full Baseline Matrix",),
	)

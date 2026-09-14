import frappe


def execute():
	"""Stamp Survey.cycle from the cycle pair that already links each survey."""
	if not frappe.db.table_exists("Survey"):
		return
	if not frappe.db.has_column("Survey", "cycle"):
		return

	frappe.db.sql(
		"""
		UPDATE `tabSurvey` s
		INNER JOIN `tabSurvey Cycle Pair` scp
			ON scp.survey = s.name
			AND scp.parenttype = 'Survey Cycle'
			AND scp.parentfield = 'pairs'
		SET s.cycle = scp.parent
		WHERE IFNULL(s.cycle, '') = ''
		"""
	)
	frappe.db.commit()
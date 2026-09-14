"""Shared current-cycle visibility rules for survey dashboards."""

import frappe
from frappe.utils import cint


ACTIVE_CYCLE_STATUSES = ("Open", "Generating", "Reporting")


def get_current_cycle():
	"""Return the active cycle, or the newest cycle when none is active."""
	if not frappe.db.exists("DocType", "Survey Cycle"):
		return None

	name = frappe.db.get_value(
		"Survey Cycle",
		{"status": ["in", list(ACTIVE_CYCLE_STATUSES)]},
		"name",
		order_by="period_start desc, creation desc",
	)
	if not name:
		name = frappe.db.get_value(
			"Survey Cycle",
			{},
			"name",
			order_by="period_start desc, creation desc",
		)
	if not name:
		return None

	cycle = frappe.db.get_value(
		"Survey Cycle",
		name,
		["name", "title", "status", "period_start", "period_end"],
		as_dict=True,
	)
	if not cycle:
		return None
	return {
		"name": cycle.name,
		"title": cycle.title or cycle.name,
		"status": cycle.status or "",
		"period_start": str(cycle.period_start or ""),
		"period_end": str(cycle.period_end or ""),
	}


def hide_previous_cycle_data():
	"""Default safely to current-cycle-only until the new setting is migrated."""
	if not frappe.db.exists("DocType", "Value Scoring Settings"):
		return True
	if not frappe.db.exists(
		"DocField",
		{
			"parent": "Value Scoring Settings",
			"parenttype": "DocType",
			"fieldname": "hide_previous_cycle_data",
		},
	):
		return True
	stored_values = frappe.db.sql(
		"""
		SELECT `value`
		FROM `tabSingles`
		WHERE `doctype` = %s AND `field` = %s
		LIMIT 1
		""",
		("Value Scoring Settings", "hide_previous_cycle_data"),
	)
	# Existing Single records receive an empty value when this field is first
	# migrated. Treat that upgrade state like the field's default (enabled),
	# while preserving an explicit 0 saved by an HR administrator.
	if not stored_values or stored_values[0][0] in (None, ""):
		return True
	return bool(cint(stored_values[0][0]))


def get_cycle_scope(include_history=0):
	"""Resolve the effective scope; only guarded HR APIs may override it."""
	include_history = bool(cint(include_history)) or not hide_previous_cycle_data()
	return {
		"include_history": include_history,
		"history_hidden": not include_history,
		"current_cycle": get_current_cycle(),
	}


def _scoped_cycle_sql(table):
	"""WHERE fragment limiting rows to the visible cycle scope.

	Legacy surveys (no cycle link) are always hidden. When previous-cycle data
	is hidden, only the current cycle is visible; otherwise past cycles show
	but legacy/test rows never do.
	"""
	current = get_current_cycle()
	if hide_previous_cycle_data():
		if not current:
			return "1 = 0"
		return f"`{table}`.`cycle` = {frappe.db.escape(current['name'])}"
	return f"IFNULL(`{table}`.`cycle`, '') != ''"


def survey_list_conditions(user=None, doctype=None):
	"""Desk list scoping for Survey: current cycle only by default."""
	return _scoped_cycle_sql("tabSurvey")


def survey_response_list_conditions(user=None, doctype=None):
	"""Desk list scoping for Survey Response via its survey's cycle."""
	return (
		"`tabSurvey Response`.`survey` IN "
		f"(SELECT `name` FROM `tabSurvey` WHERE {_scoped_cycle_sql('tabSurvey')})"
	)

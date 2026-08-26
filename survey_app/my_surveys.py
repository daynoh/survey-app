"""Employee-facing, session-scoped survey dashboard API."""

import frappe
from frappe import _
from frappe.utils import getdate, today

from survey_app.performance import build_employee_scorecard


LEGACY_PERIOD_KEY = "__legacy__"


@frappe.whitelist()
def get_my_dashboard(period_key=None, from_date=None, to_date=None):
	"""Return only the signed-in user's profile, aggregate results, and assignments."""
	if frappe.session.user == "Guest":
		frappe.throw(_("Please sign in to view My Surveys."), frappe.PermissionError)

	employee = frappe.db.get_value(
		"Employee",
		{"user_id": frappe.session.user},
		["name", "employee_name", "designation", "department", "image", "status"],
		as_dict=True,
	)
	if not employee:
		return _empty_dashboard("no_employee")

	profile = {
		"employee_name": employee.employee_name or employee.name,
		"designation": employee.designation or "",
		"department": employee.department or "",
		"image": employee.image or "",
		"status": employee.status or "",
	}
	if employee.status != "Active":
		return _empty_dashboard("inactive_employee", profile=profile)

	activity_filter = _normalise_activity_filter(from_date, to_date)
	assignments = _get_assignments(
		frappe.session.user,
		activity_filter["from_date"],
		activity_filter["to_date"],
	)
	active_cycle = _get_active_cycle(employee.name)
	periods = _get_result_periods(employee.name)
	period_keys = {period["key"] for period in periods}

	if period_key and period_key not in period_keys:
		frappe.throw(_("That survey result period is not available."), frappe.PermissionError)

	selected_key = period_key or (periods[0]["key"] if periods else None)
	selected_period = next((period for period in periods if period["key"] == selected_key), None)
	results = _get_results(employee.name, selected_period, active_cycle)
	trend = _get_result_trend(employee.name, periods)

	return {
		"state": "ready",
		"profile": profile,
		"active_cycle": active_cycle,
		"periods": periods,
		"selected_period": selected_period,
		"results": results,
		"trend": trend,
		"assignments": assignments,
		"activity_filter": activity_filter,
	}


def _get_result_periods(employee):
	periods = []
	if frappe.db.exists("DocType", "Survey Cycle") and frappe.db.exists(
		"DocType", "Survey Cycle Pair"
	):
		closed_cycles = frappe.db.sql(
			"""
			SELECT DISTINCT
				sc.name,
				sc.title,
				sc.period_start,
				sc.period_end
			FROM `tabSurvey Cycle` sc
			INNER JOIN `tabSurvey Cycle Pair` scp
				ON scp.parent = sc.name
				AND scp.parenttype = 'Survey Cycle'
				AND scp.parentfield = 'pairs'
			WHERE sc.status = 'Closed'
				AND scp.reviewee = %(employee)s
			ORDER BY sc.period_end DESC, sc.creation DESC
			""",
			{"employee": employee},
			as_dict=True,
		)
		periods.extend(
			{
				"key": cycle.name,
				"type": "cycle",
				"label": cycle.title or cycle.name,
				"period_start": str(cycle.period_start or ""),
				"period_end": str(cycle.period_end or ""),
				"released": True,
			}
			for cycle in closed_cycles
		)

	legacy_bounds = _get_legacy_bounds(employee)
	if legacy_bounds:
		periods.append(
			{
				"key": LEGACY_PERIOD_KEY,
				"type": "legacy",
				"label": _("Earlier Surveys"),
				"period_start": str(legacy_bounds.from_date or ""),
				"period_end": str(legacy_bounds.to_date or ""),
				"released": True,
			}
		)
	return periods


def _get_legacy_bounds(employee):
	cycle_join = ""
	cycle_condition = ""
	if frappe.db.exists("DocType", "Survey Cycle Pair"):
		cycle_join = """
		LEFT JOIN `tabSurvey Cycle Pair` scp
			ON scp.survey = s.name
			AND scp.parenttype = 'Survey Cycle'
			AND scp.parentfield = 'pairs'
		"""
		cycle_condition = "AND scp.name IS NULL"
	rows = frappe.db.sql(
		f"""
		SELECT
			MIN(DATE(sr.submission_date)) AS from_date,
			MAX(DATE(sr.submission_date)) AS to_date
		FROM `tabSurvey Response` sr
		INNER JOIN `tabSurvey` s ON s.name = sr.survey
		{cycle_join}
		WHERE sr.docstatus < 2
			AND s.employee_score = %(employee)s
			{cycle_condition}
		""",
		{"employee": employee},
		as_dict=True,
	)
	return rows[0] if rows and rows[0].from_date else None


def _get_results(employee, selected_period, active_cycle):
	if not selected_period:
		is_reviewee = bool(active_cycle and active_cycle.get("is_reviewee"))
		return {
			"state": "locked" if is_reviewee else "empty",
			"message": _("Results will be released after the active survey cycle is closed.")
			if is_reviewee
			else _("No released survey results are available yet."),
		}

	if selected_period["type"] == "cycle":
		cycle = frappe.get_cached_doc("Survey Cycle", selected_period["key"])
		scorecard = build_employee_scorecard(
			employee,
			cycle.period_start,
			cycle.period_end,
			cycle=cycle,
		)
	else:
		scorecard = build_employee_scorecard(
			employee,
			getdate(selected_period["period_start"]),
			getdate(selected_period["period_end"]),
			legacy_only=True,
		)

	if not scorecard["has_data"]:
		return {
			"state": "empty",
			"message": _("No scored feedback is available for this period."),
			"reviewer_count": scorecard["reviewer_count"],
			"expected_reviews": scorecard["expected_reviews"],
		}

	return {
		"state": "released",
		"overall_pct": scorecard["overall_pct"],
		"overall_percentile": scorecard["overall_percentile"],
		"org_overall_avg": scorecard["org_overall_avg"],
		"org_headcount": scorecard["org_headcount"],
		"delta": scorecard["delta"],
		"reviewer_count": scorecard["reviewer_count"],
		"expected_reviews": scorecard["expected_reviews"],
		"categories": scorecard["categories"],
	}


def _get_result_trend(employee, periods, limit=6):
	"""Return aggregate-only historical points from the employee's released periods."""
	ordered_periods = sorted(
		periods,
		key=lambda period: (
			period.get("period_end") or period.get("period_start") or "",
			period.get("key") or "",
		),
	)
	points = []
	for period in ordered_periods[-limit:]:
		result = _get_results(employee, period, active_cycle=None)
		if result.get("state") != "released":
			continue
		points.append(
			{
				"key": period["key"],
				"label": period.get("label") or period["key"],
				"period_start": period.get("period_start") or "",
				"period_end": period.get("period_end") or "",
				"overall_pct": result["overall_pct"],
				"org_avg": result.get("org_overall_avg"),
				"reviewer_count": result.get("reviewer_count") or 0,
			}
		)
	return points


def _get_active_cycle(employee):
	if not (
		frappe.db.exists("DocType", "Survey Cycle")
		and frappe.db.exists("DocType", "Survey Cycle Pair")
	):
		return None
	rows = frappe.db.sql(
		"""
		SELECT DISTINCT
			sc.name,
			sc.title,
			sc.status,
			sc.period_start,
			sc.period_end,
			MAX(CASE WHEN scp.reviewee = %(employee)s THEN 1 ELSE 0 END) AS is_reviewee
		FROM `tabSurvey Cycle` sc
		INNER JOIN `tabSurvey Cycle Pair` scp
			ON scp.parent = sc.name
			AND scp.parenttype = 'Survey Cycle'
			AND scp.parentfield = 'pairs'
		WHERE sc.status IN ('Open', 'Generating', 'Reporting')
			AND (scp.reviewer = %(employee)s OR scp.reviewee = %(employee)s)
		GROUP BY sc.name, sc.title, sc.status, sc.period_start, sc.period_end
		ORDER BY sc.period_start DESC, sc.creation DESC
		LIMIT 1
		""",
		{"employee": employee},
		as_dict=True,
	)
	if not rows:
		return None
	cycle = rows[0]
	counts = frappe.db.sql(
		"""
		SELECT
			SUM(CASE WHEN scp.survey IS NOT NULL AND sr.survey IS NULL THEN 1 ELSE 0 END) AS pending,
			SUM(CASE WHEN sr.survey IS NOT NULL THEN 1 ELSE 0 END) AS completed
		FROM `tabSurvey Cycle Pair` scp
		LEFT JOIN (
			SELECT survey FROM `tabSurvey Response` WHERE docstatus < 2 GROUP BY survey
		) sr ON sr.survey = scp.survey
		WHERE scp.parent = %(cycle)s
			AND scp.parenttype = 'Survey Cycle'
			AND scp.parentfield = 'pairs'
			AND scp.reviewer = %(employee)s
		""",
		{"cycle": cycle.name, "employee": employee},
		as_dict=True,
	)[0]
	return {
		"name": cycle.name,
		"title": cycle.title or cycle.name,
		"status": cycle.status,
		"period_start": str(cycle.period_start or ""),
		"period_end": str(cycle.period_end or ""),
		"is_reviewee": bool(cycle.is_reviewee),
		"my_pending": int(counts.pending or 0),
		"my_completed": int(counts.completed or 0),
	}


def _normalise_activity_filter(from_date=None, to_date=None):
	try:
		start = getdate(from_date) if from_date else None
		end = getdate(to_date) if to_date else None
	except (TypeError, ValueError):
		frappe.throw(_("Enter valid activity dates."), frappe.ValidationError)

	if start and end and start > end:
		frappe.throw(
			_("The activity start date cannot be after the end date."),
			frappe.ValidationError,
		)
	return {
		"from_date": str(start) if start else "",
		"to_date": str(end) if end else "",
		"active": bool(start or end),
	}


def _get_assignments(user, from_date=None, to_date=None):
	conditions = []
	values = {"user": user}
	if from_date:
		conditions.append(
			"DATE(COALESCE(response.submission_date, s.creation)) >= %(activity_from_date)s"
		)
		values["activity_from_date"] = getdate(from_date)
	if to_date:
		conditions.append(
			"DATE(COALESCE(response.submission_date, s.creation)) <= %(activity_to_date)s"
		)
		values["activity_to_date"] = getdate(to_date)
	date_condition = "\n\t\t\t\tAND " + "\n\t\t\t\tAND ".join(conditions) if conditions else ""
	rows = frappe.db.sql(
		f"""
			SELECT
			s.name AS survey,
			s.title,
			s.creation AS assigned_on,
			s.employee_score AS reviewee,
			COALESCE(reviewee.employee_name, s.employee_score) AS reviewee_name,
			COALESCE(reviewee.department, '') AS department,
			response.submission_date
		FROM `tabSurvey` s
		LEFT JOIN `tabEmployee` reviewee ON reviewee.name = s.employee_score
		LEFT JOIN (
			SELECT survey, MAX(submission_date) AS submission_date
			FROM `tabSurvey Response`
			WHERE docstatus < 2
			GROUP BY survey
		) response ON response.survey = s.name
			WHERE s.rated_by = %(user)s
				AND IFNULL(s.is_internal_scoring, 0) = 1
				{date_condition}
			ORDER BY COALESCE(response.submission_date, s.creation) DESC
			""",
		values,
		as_dict=True,
	)
	pending = []
	completed = []
	for row in rows:
		item = {
			"survey": row.survey,
			"title": row.title or _("360° Survey"),
			"reviewee_name": row.reviewee_name or _("Employee"),
			"department": row.department or "",
			"assigned_on": str(row.assigned_on or ""),
			"survey_url": f"/survey?id={row.survey}",
		}
		if row.submission_date:
			item["completed_on"] = str(row.submission_date)
			completed.append(item)
		else:
			item["days_pending"] = max(0, (getdate(today()) - getdate(row.assigned_on)).days)
			pending.append(item)

	pending.sort(key=lambda item: (item["days_pending"], item["assigned_on"]), reverse=True)
	return {
		"pending_count": len(pending),
		"completed_count": len(completed),
		"pending": pending,
		"recent_completed": completed[:20],
		"filter_active": bool(from_date or to_date),
	}


def _empty_dashboard(state, profile=None):
	return {
		"state": state,
		"profile": profile,
		"active_cycle": None,
		"periods": [],
		"selected_period": None,
		"results": {"state": "empty"},
		"trend": [],
		"activity_filter": {"from_date": "", "to_date": "", "active": False},
		"assignments": {
			"pending_count": 0,
			"completed_count": 0,
			"pending": [],
			"recent_completed": [],
			"filter_active": False,
		},
	}

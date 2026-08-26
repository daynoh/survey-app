"""Shared, cycle-aware 360-degree performance score aggregation."""

from collections import defaultdict

import frappe
from frappe.utils import add_to_date, flt, getdate


MAX_SCORE_PER_SELECTION = 5.0


def build_employee_scorecard(
	employee,
	period_start,
	period_end,
	cycle=None,
	legacy_only=False,
):
	"""Return aggregate-only employee results for one released result period."""
	cycle_name = _cycle_name(cycle)
	current = aggregate_rows(
		get_score_rows(
			employee,
			period_start,
			period_end,
			cycle=cycle_name,
			legacy_only=legacy_only,
		)
	)

	previous = _empty_aggregate()
	if not legacy_only:
		previous_cycle = _previous_closed_cycle(cycle_name)
		if previous_cycle:
			previous = aggregate_rows(
				get_score_rows(
					employee,
					previous_cycle.period_start,
					previous_cycle.period_end,
					cycle=previous_cycle.name,
				)
			)
		elif not cycle_name:
			prev_start, prev_end = previous_period(period_start, period_end)
			previous = aggregate_rows(get_score_rows(employee, prev_start, prev_end))

	delta = None
	if current["has_data"] and previous["has_data"]:
		delta = round(current["overall_pct"] - previous["overall_pct"], 1)

	org = get_org_benchmarks(
		period_start,
		period_end,
		cycle=cycle_name,
		legacy_only=legacy_only,
	)
	categories = []
	for category in current["categories"]:
		category_name = category["category"]
		peer_scores = (org.get("category_scores") or {}).get(category_name) or []
		categories.append(
			{
				**category,
				"percentile": percentile_rank(category["score_pct"], peer_scores),
				"org_avg": round(sum(peer_scores) / len(peer_scores), 1) if peer_scores else None,
				"org_n": len(peer_scores),
			}
		)

	expected = 0
	if cycle_name and _has_cycle_pairs():
		expected = frappe.db.count(
			"Survey Cycle Pair",
			{"parent": cycle_name, "parenttype": "Survey Cycle", "reviewee": employee},
		)

	return {
		"has_data": current["has_data"],
		"overall_pct": current["overall_pct"],
		"overall_percentile": percentile_rank(
			current["overall_pct"], org.get("overall_scores") or []
		)
		if current["has_data"]
		else None,
		"org_overall_avg": org.get("overall_avg"),
		"org_headcount": org.get("employee_count") or 0,
		"delta": delta,
		"categories": categories,
		"previous_categories": previous["categories"],
		"reviewer_count": current["response_count"],
		"expected_reviews": expected,
	}


def get_score_rows(employee, period_start, period_end, cycle=None, legacy_only=False):
	cycle_join, cycle_condition, values = _cycle_filter(cycle, legacy_only)
	values.update(
		{
			"employee": employee,
			"from_date": getdate(period_start),
			"to_date": getdate(period_end),
		}
	)
	return frappe.db.sql(
		f"""
		SELECT
			vq.category AS category,
			srs.score AS selection_score,
			col_opt.score AS column_score,
			sr.name AS response_name
		FROM `tabSurvey Response` sr
		INNER JOIN `tabSurvey` s ON s.name = sr.survey
		{cycle_join}
		INNER JOIN `tabSurvey Response Answer` sra ON sra.parent = sr.name
		INNER JOIN `tabSurvey Response Selection` srs ON srs.parent = sra.name
		LEFT JOIN `tabSurvey Question Options` row_opt ON row_opt.name = srs.row_option
		LEFT JOIN `tabValue Questions` vq ON vq.question = row_opt.option_label
		LEFT JOIN `tabSurvey Question Options` col_opt ON col_opt.name = srs.column_option
		WHERE s.employee_score = %(employee)s
			AND sr.docstatus < 2
			AND DATE(sr.submission_date) >= %(from_date)s
			AND DATE(sr.submission_date) <= %(to_date)s
			{cycle_condition}
		""",
		values,
		as_dict=True,
	)


def aggregate_rows(rows):
	if not rows:
		return _empty_aggregate()

	total_score = 0.0
	total_max = 0.0
	category_totals = defaultdict(lambda: {"scores": 0.0, "max_scores": 0.0})
	responses = set()
	for row in rows:
		score = flt(row.column_score or row.selection_score or 0)
		total_score += score
		total_max += MAX_SCORE_PER_SELECTION
		responses.add(row.response_name)
		category = row.category or "Uncategorised"
		category_totals[category]["scores"] += score
		category_totals[category]["max_scores"] += MAX_SCORE_PER_SELECTION

	categories = []
	for category in sorted(category_totals):
		totals = category_totals[category]
		percentage = (
			round(totals["scores"] / totals["max_scores"] * 100, 1)
			if totals["max_scores"]
			else 0
		)
		categories.append({"category": category, "score_pct": percentage})

	return {
		"has_data": True,
		"overall_pct": round(total_score / total_max * 100, 1) if total_max else 0,
		"categories": categories,
		"response_count": len(responses),
	}


def get_org_benchmarks(period_start, period_end, cycle=None, legacy_only=False):
	"""Return score distributions used internally for anonymous benchmarks."""
	cycle_join, cycle_condition, values = _cycle_filter(cycle, legacy_only)
	values.update({"from_date": getdate(period_start), "to_date": getdate(period_end)})
	rows = frappe.db.sql(
		f"""
		SELECT
			s.employee_score AS employee,
			vq.category AS category,
			srs.score AS selection_score,
			col_opt.score AS column_score
		FROM `tabSurvey Response` sr
		INNER JOIN `tabSurvey` s ON s.name = sr.survey
		{cycle_join}
		INNER JOIN `tabSurvey Response Answer` sra ON sra.parent = sr.name
		INNER JOIN `tabSurvey Response Selection` srs ON srs.parent = sra.name
		LEFT JOIN `tabSurvey Question Options` row_opt ON row_opt.name = srs.row_option
		LEFT JOIN `tabValue Questions` vq ON vq.question = row_opt.option_label
		LEFT JOIN `tabSurvey Question Options` col_opt ON col_opt.name = srs.column_option
		WHERE sr.docstatus < 2
			AND s.employee_score IS NOT NULL
			AND DATE(sr.submission_date) >= %(from_date)s
			AND DATE(sr.submission_date) <= %(to_date)s
			{cycle_condition}
		""",
		values,
		as_dict=True,
	)

	employee_totals = defaultdict(lambda: {"score": 0.0, "max": 0.0})
	employee_categories = defaultdict(
		lambda: defaultdict(lambda: {"score": 0.0, "max": 0.0})
	)
	for row in rows:
		if not row.employee:
			continue
		score = flt(row.column_score or row.selection_score or 0)
		employee_totals[row.employee]["score"] += score
		employee_totals[row.employee]["max"] += MAX_SCORE_PER_SELECTION
		category = row.category or "Uncategorised"
		employee_categories[row.employee][category]["score"] += score
		employee_categories[row.employee][category]["max"] += MAX_SCORE_PER_SELECTION

	overall_scores = [
		round(totals["score"] / totals["max"] * 100, 1)
		for totals in employee_totals.values()
		if totals["max"]
	]
	category_scores = defaultdict(list)
	for categories in employee_categories.values():
		for category, totals in categories.items():
			if totals["max"]:
				category_scores[category].append(
					round(totals["score"] / totals["max"] * 100, 1)
				)

	return {
		"overall_scores": overall_scores,
		"overall_avg": round(sum(overall_scores) / len(overall_scores), 1)
		if overall_scores
		else None,
		"employee_count": len(overall_scores),
		"category_scores": dict(category_scores),
	}


def percentile_rank(score, peer_scores):
	if not peer_scores:
		return None
	below = sum(1 for peer_score in peer_scores if peer_score < score)
	equal = sum(1 for peer_score in peer_scores if peer_score == score)
	return round((below + 0.5 * equal) / len(peer_scores) * 100, 0)


def previous_period(start, end):
	start = getdate(start)
	end = getdate(end)
	span = (end - start).days + 1
	previous_end = add_to_date(start, days=-1)
	previous_start = add_to_date(previous_end, days=-(span - 1))
	return getdate(previous_start), getdate(previous_end)


def _cycle_filter(cycle, legacy_only):
	if not _has_cycle_pairs():
		return "", "", {}

	if cycle:
		return (
			"""INNER JOIN `tabSurvey Cycle Pair` score_cycle_pair
				ON score_cycle_pair.survey = s.name
				AND score_cycle_pair.parenttype = 'Survey Cycle'
				AND score_cycle_pair.parentfield = 'pairs'""",
			"AND score_cycle_pair.parent = %(score_cycle)s",
			{"score_cycle": _cycle_name(cycle)},
		)
	if legacy_only:
		return (
			"""LEFT JOIN `tabSurvey Cycle Pair` score_cycle_pair
				ON score_cycle_pair.survey = s.name
				AND score_cycle_pair.parenttype = 'Survey Cycle'
				AND score_cycle_pair.parentfield = 'pairs'""",
			"AND score_cycle_pair.name IS NULL",
			{},
		)
	return "", "", {}


def _previous_closed_cycle(cycle):
	cycle_name = _cycle_name(cycle)
	if not cycle_name or not frappe.db.exists("DocType", "Survey Cycle"):
		return None
	period_start = frappe.db.get_value("Survey Cycle", cycle_name, "period_start")
	if not period_start:
		return None
	rows = frappe.get_all(
		"Survey Cycle",
		filters={"status": "Closed", "period_end": ["<", period_start]},
		fields=["name", "period_start", "period_end"],
		order_by="period_end desc",
		limit=1,
	)
	return rows[0] if rows else None


def _cycle_name(cycle):
	if not cycle:
		return None
	if isinstance(cycle, str):
		return cycle
	if isinstance(cycle, dict):
		return cycle.get("name")
	return getattr(cycle, "name", None)


def _has_cycle_pairs():
	return bool(frappe.db.exists("DocType", "Survey Cycle Pair"))


def _empty_aggregate():
	return {"has_data": False, "overall_pct": 0, "categories": [], "response_count": 0}

"""Survey Cycle: roles, required review matrix, load math, and batch assignment."""

from __future__ import annotations

import math
from collections import defaultdict
from datetime import date

import frappe
from frappe.utils import (
	add_days,
	add_months,
	add_to_date,
	cint,
	flt,
	get_datetime,
	getdate,
	now_datetime,
	today,
)

from survey_app.surveys import FREQUENCY_INTERVALS, create_survey_and_send_invitation, send_survey_notification_and_task


CYCLE_INTERVALS = {
	"Monthly": {"months": 1},
	"Quarterly": {"months": 3},
	"Bi-Annually": {"months": 6},
	"Yearly": {"months": 12},
}


def _settings():
	return frappe.get_doc("Value Scoring Settings")


def _active_employees(exclude_names=None):
	exclude_names = exclude_names or set()
	rows = frappe.get_all(
		"Employee",
		filters={"status": "Active"},
		fields=["name", "employee_name", "department", "user_id", "reports_to", "designation"],
	)
	return [e for e in rows if e.name not in exclude_names]


def _excluded_employees(settings):
	rated_emails = {d.user for d in (settings.exclude_rated or [])}
	rating_emails = {d.user for d in (settings.exclude_rating or [])}
	excluded_reviewees = set()
	excluded_reviewers = set()
	if rated_emails:
		excluded_reviewees = set(
			frappe.get_all("Employee", filters={"user_id": ["in", list(rated_emails)]}, pluck="name")
		)
	if rating_emails:
		excluded_reviewers = set(
			frappe.get_all("Employee", filters={"user_id": ["in", list(rating_emails)]}, pluck="name")
		)
	return excluded_reviewees, excluded_reviewers


# ---------------------------------------------------------------------------
# Role resolution
# ---------------------------------------------------------------------------

@frappe.whitelist()
def resolve_org_roles():
	"""Resolve MD + Team Leaders using Manual → Org → Role (Hybrid order)."""
	settings = _settings()
	mode = settings.role_resolution_mode or "Hybrid"
	employees = _active_employees()
	by_dept = defaultdict(list)
	for e in employees:
		if e.department:
			by_dept[e.department].append(e)

	md = None
	team_leaders = {}  # dept -> employee dict

	use_manual = mode in ("Manual", "Hybrid")
	use_org = mode in ("Org", "Hybrid")
	use_role = mode in ("Role", "Hybrid")

	# Manual MD / TLs
	if use_manual:
		if settings.md_employee and frappe.db.exists("Employee", settings.md_employee):
			md_row = frappe.get_value(
				"Employee",
				settings.md_employee,
				["name", "employee_name", "department", "user_id", "designation"],
				as_dict=True,
			)
			if md_row:
				md = {**md_row, "source": "Manual"}
		for row in settings.team_leaders or []:
			if not row.department or not row.employee:
				continue
			emp = frappe.get_value(
				"Employee",
				row.employee,
				["name", "employee_name", "department", "user_id", "designation"],
				as_dict=True,
			)
			if emp:
				team_leaders[row.department] = {**emp, "source": "Manual", "department": row.department}

	# Org fallback
	if use_org:
		if not md:
			md = _resolve_md_from_org(employees)
		designations = _parse_designations(settings.team_leader_designations)
		for dept, members in by_dept.items():
			if dept in team_leaders:
				continue
			tl = _resolve_tl_from_org(members, designations)
			if tl:
				team_leaders[dept] = {**tl, "source": "Org", "department": dept}

	# Role fallback
	if use_role:
		if not md:
			md = _resolve_from_role("Managing Director", employees, source="Role")
		role_tls = _employees_with_role("Team Leader", employees)
		for emp in role_tls:
			dept = emp.department
			if dept and dept not in team_leaders:
				team_leaders[dept] = {
					"name": emp.name,
					"employee_name": emp.employee_name,
					"department": dept,
					"user_id": emp.user_id,
					"designation": emp.designation,
					"source": "Role",
				}

	departments = sorted(by_dept.keys())
	roster = []
	for dept in departments:
		tl = team_leaders.get(dept)
		roster.append({
			"department": dept,
			"team_size": len(by_dept[dept]),
			"team_leader": tl["name"] if tl else None,
			"team_leader_name": tl["employee_name"] if tl else None,
			"source": tl["source"] if tl else None,
		})

	return {
		"mode": mode,
		"md": md,
		"team_leaders": [
			{
				"department": d,
				"employee": tl["name"],
				"employee_name": tl["employee_name"],
				"source": tl.get("source"),
			}
			for d, tl in sorted(team_leaders.items())
		],
		"roster": roster,
		"warnings": _role_warnings(md, team_leaders, departments),
	}


def _parse_designations(raw):
	if not raw:
		return {"team lead", "team leader", "teamleader"}
	parts = [p.strip().lower() for p in str(raw).replace("\n", ",").split(",") if p.strip()]
	return set(parts) or {"team lead", "team leader"}


def _resolve_md_from_org(employees):
	# Prefer designation containing managing director / md
	for e in employees:
		des = (e.designation or "").lower()
		if "managing director" in des or des.strip() == "md":
			return {
				"name": e.name,
				"employee_name": e.employee_name,
				"department": e.department,
				"user_id": e.user_id,
				"designation": e.designation,
				"source": "Org",
			}
	# Top of reports_to chain: someone who is never a reports_to target of anyone? 
	# Prefer employee who has reports but reports_to is empty
	reported_to = {e.reports_to for e in employees if e.reports_to}
	roots = [e for e in employees if not e.reports_to and e.name in reported_to]
	if roots:
		e = roots[0]
		return {
			"name": e.name,
			"employee_name": e.employee_name,
			"department": e.department,
			"user_id": e.user_id,
			"designation": e.designation,
			"source": "Org",
		}
	return None


def _resolve_tl_from_org(members, designations):
	# designation match
	for e in members:
		des = (e.designation or "").lower()
		if any(d in des for d in designations):
			return e
	# person in dept that others report to, and not reporting within dept
	member_names = {m.name for m in members}
	managers = []
	for e in members:
		if any(m.reports_to == e.name for m in members):
			managers.append(e)
	if managers:
		# Prefer those whose reports_to is outside dept or empty
		for e in managers:
			if not e.reports_to or e.reports_to not in member_names:
				return e
		return managers[0]
	return None


def _employees_with_role(role, employees):
	if not frappe.db.exists("Role", role):
		return []
	users = frappe.get_all(
		"Has Role",
		filters={"role": role, "parenttype": "User"},
		pluck="parent",
	)
	user_set = set(users or [])
	return [e for e in employees if e.user_id and e.user_id in user_set]


def _resolve_from_role(role, employees, source="Role"):
	matched = _employees_with_role(role, employees)
	if not matched:
		return None
	e = matched[0]
	return {
		"name": e.name,
		"employee_name": e.employee_name,
		"department": e.department,
		"user_id": e.user_id,
		"designation": e.designation,
		"source": source,
	}


def _role_warnings(md, team_leaders, departments):
	warnings = []
	if not md:
		warnings.append("Managing Director is not resolved. Assign one in Survey Setup.")
	missing = [d for d in departments if d not in team_leaders]
	if missing:
		warnings.append(
			f"No Team Leader resolved for {len(missing)} department(s): "
			+ ", ".join(missing[:8])
			+ ("…" if len(missing) > 8 else "")
		)
	return warnings


# ---------------------------------------------------------------------------
# Required matrix + load preview
# ---------------------------------------------------------------------------

def build_required_pairs(roles=None):
	"""Return list of {reviewer, reviewee, rule_type} for the cycle matrix."""
	settings = _settings()
	roles = roles or resolve_org_roles()
	excluded_reviewees, excluded_reviewers = _excluded_employees(settings)
	employees = _active_employees(exclude_names=excluded_reviewees)

	by_dept = defaultdict(list)
	for e in employees:
		if e.department:
			by_dept[e.department].append(e)

	md = roles.get("md")
	md_name = md["name"] if md else None
	tl_by_dept = {t["department"]: t["employee"] for t in roles.get("team_leaders") or []}

	pairs = []
	seen = set()

	def add_pair(reviewer, reviewee, rule_type):
		if not reviewer or not reviewee or reviewer == reviewee:
			return
		if reviewer in excluded_reviewers or reviewee in excluded_reviewees:
			return
		key = (reviewer, reviewee)
		if key in seen:
			return
		seen.add(key)
		pairs.append({
			"reviewer": reviewer,
			"reviewee": reviewee,
			"rule_type": rule_type,
		})

	# Team Leader → each team member (before peers so rule_type is preserved)
	for dept, tl in tl_by_dept.items():
		for m in by_dept.get(dept, []):
			add_pair(tl, m.name, "TeamLeader")

	# Team Leader → MD
	if md_name:
		for dept, tl in tl_by_dept.items():
			add_pair(tl, md_name, "TL_to_MD")

	# Peers: every teammate surveys every other teammate
	for dept, members in by_dept.items():
		names = [m.name for m in members]
		for a in names:
			for b in names:
				if a != b:
					add_pair(a, b, "Peer")

	# Nearness externals (required when factor > 0)
	nearness = frappe.get_all(
		"Departmental Nearness Factor",
		fields=["department", "department2", "factor"],
	)
	nearness_map = {(n.department, n.department2): flt(n.factor) for n in nearness}

	max_per_employee = cint(settings.max_surveys_per_employee) or 10
	for dept, members in by_dept.items():
		other_depts = [d for d in by_dept.keys() if d != dept]
		total_weight = sum(nearness_map.get((dept, od), 0) for od in other_depts)
		if total_weight <= 0:
			continue
		# Aim ~40% external of target reviews per reviewee, at least 1 when nearness exists
		external_needed = max(1, math.ceil(max_per_employee * 0.4))
		for od in other_depts:
			weight = nearness_map.get((dept, od), 0)
			if weight <= 0:
				continue
			quota = max(1, math.ceil((weight / total_weight) * external_needed))
			candidates = [m.name for m in by_dept.get(od, []) if m.name not in excluded_reviewers]
			for reviewee in members:
				for reviewer in candidates[:quota]:
					add_pair(reviewer, reviewee.name, "Nearness")

	return pairs


def _reviewer_batch_quota(remaining, batches_left, min_per, cap):
	"""Evenly split remaining pairs across remaining sends, with min floor and max cap.

	Last remainder is always assigned even when below min (quota cannot exceed remaining).
	"""
	remaining = cint(remaining)
	batches_left = max(1, cint(batches_left))
	min_per = max(1, cint(min_per) or 3)
	cap = max(1, cint(cap) or 10)
	if remaining <= 0:
		return 0
	even = math.ceil(remaining / batches_left)
	quota = max(min_per, even)
	return min(quota, cap, remaining)


@frappe.whitelist()
def preview_cycle_load():
	"""Estimated load per reviewer for the planned matrix + batch size."""
	settings = _settings()
	roles = resolve_org_roles()
	pairs = build_required_pairs(roles)
	survey_freq = settings.generation_frequency or "Weekly"
	cycle = settings.completeness_cycle or "Quarterly"

	batches = _batches_in_cycle(survey_freq, cycle)
	by_reviewer = defaultdict(int)
	by_rule = defaultdict(int)
	for p in pairs:
		by_reviewer[p["reviewer"]] += 1
		by_rule[p["rule_type"]] += 1

	emp_names = {e.name: e.employee_name for e in _active_employees()}
	load_rows = []
	warnings = list(roles.get("warnings") or [])
	cap = cint(settings.max_surveys_per_reviewer) or 10
	min_per = cint(getattr(settings, "min_surveys_per_batch", None)) or 3

	for reviewer, count in sorted(by_reviewer.items(), key=lambda x: -x[1]):
		even = math.ceil(count / batches) if batches else count
		per_batch = _reviewer_batch_quota(count, batches, min_per, cap)
		row = {
			"reviewer": reviewer,
			"reviewer_name": emp_names.get(reviewer, reviewer),
			"required_surveys": count,
			"batches_in_cycle": batches,
			"even_split": even,
			"per_batch": per_batch,
			"over_cap": even > cap,
			"under_min": even < min_per and count >= min_per,
		}
		load_rows.append(row)
		if even > cap:
			warnings.append(
				f"{row['reviewer_name']} needs ~{even}/batch "
				f"(cap {cap}). Raise cap or reduce matrix."
			)
		elif even < min_per and count >= min_per:
			warnings.append(
				f"{row['reviewer_name']} even-split is ~{even}/batch "
				f"(min {min_per}); early sends will front-load to the minimum."
			)

	return {
		"roles": roles,
		"total_pairs": len(pairs),
		"by_rule": dict(by_rule),
		"survey_frequency": survey_freq,
		"completeness_cycle": cycle,
		"batches_in_cycle": batches,
		"min_surveys_per_batch": min_per,
		"max_surveys_per_reviewer": cap,
		"load": load_rows[:100],
		"warnings": warnings,
		"generation_mode": getattr(settings, "generation_mode", None) or "Cycle Matrix",
	}


def _batches_in_cycle(survey_freq, completeness_cycle):
	survey_days = _interval_days(FREQUENCY_INTERVALS.get(survey_freq))
	cycle_days = _interval_days(CYCLE_INTERVALS.get(completeness_cycle) or CYCLE_INTERVALS["Quarterly"])
	if not survey_days:
		return 1
	return max(1, math.ceil(cycle_days / survey_days))


def _interval_days(interval):
	if not interval:
		return None
	if "minutes" in interval:
		return max(interval["minutes"] / (60 * 24), 1 / 288)  # tiny for testing
	if "hours" in interval:
		return max(interval["hours"] / 24, 1 / 24)
	if "days" in interval:
		return interval["days"]
	if "months" in interval:
		return interval["months"] * 30
	return None


def _cycle_period(completeness_cycle, as_of=None):
	as_of = getdate(as_of or today())
	cycle = completeness_cycle or "Quarterly"
	if cycle == "Monthly":
		start = as_of.replace(day=1)
		end = add_days(add_months(start, 1), -1)
	elif cycle == "Yearly":
		start = as_of.replace(month=1, day=1)
		end = as_of.replace(month=12, day=31)
	elif cycle == "Bi-Annually":
		if as_of.month <= 6:
			start = as_of.replace(month=1, day=1)
			end = as_of.replace(month=6, day=30)
		else:
			start = as_of.replace(month=7, day=1)
			end = as_of.replace(month=12, day=31)
	else:  # Quarterly
		q = (as_of.month - 1) // 3
		start_month = q * 3 + 1
		start = as_of.replace(month=start_month, day=1)
		end = add_days(add_months(start, 3), -1)
	return start, end


# ---------------------------------------------------------------------------
# Cycle document lifecycle
# ---------------------------------------------------------------------------

def get_or_create_open_cycle(force_rebuild=False):
	settings = _settings()
	start, end = _cycle_period(settings.completeness_cycle or "Quarterly")
	existing = frappe.db.get_value(
		"Survey Cycle",
		{"period_start": start, "period_end": end, "status": ["in", ["Open", "Generating", "Reporting"]]},
		"name",
	)
	if existing and not force_rebuild:
		return frappe.get_doc("Survey Cycle", existing)

	if existing and force_rebuild:
		frappe.delete_doc("Survey Cycle", existing, ignore_permissions=True, force=1)

	roles = resolve_org_roles()
	pairs = build_required_pairs(roles)
	title = f"Cycle {start} → {end}"

	doc = frappe.get_doc({
		"doctype": "Survey Cycle",
		"title": title,
		"status": "Open",
		"period_start": start,
		"period_end": end,
		"survey_frequency": settings.generation_frequency or "Weekly",
		"report_frequency": getattr(settings, "report_frequency", None) or "Monthly",
		"completeness_cycle": settings.completeness_cycle or "Quarterly",
		"total_pairs": len(pairs),
		"assigned_pairs": 0,
		"completed_pairs": 0,
		"completion_pct": 0,
		"current_batch": 0,
		"pairs": [
			{
				"reviewer": p["reviewer"],
				"reviewee": p["reviewee"],
				"rule_type": p["rule_type"],
				"batch_no": 0,
				"status": "Planned",
			}
			for p in pairs
		],
	})
	doc.insert(ignore_permissions=True)
	frappe.db.commit()
	return doc


@frappe.whitelist()
def ensure_cycle(force_rebuild=0):
	doc = get_or_create_open_cycle(force_rebuild=cint(force_rebuild))
	refresh_cycle_stats(doc)
	return cycle_summary(doc)


def cycle_summary(doc=None):
	if isinstance(doc, str):
		doc = frappe.get_doc("Survey Cycle", doc)
	if not doc:
		doc = get_or_create_open_cycle()
	refresh_cycle_stats(doc)
	doc.reload()
	by_status = defaultdict(int)
	for p in doc.pairs or []:
		by_status[p.status] += 1
	return {
		"name": doc.name,
		"title": doc.title,
		"status": doc.status,
		"period_start": str(doc.period_start),
		"period_end": str(doc.period_end),
		"survey_frequency": doc.survey_frequency,
		"report_frequency": doc.report_frequency,
		"completeness_cycle": doc.completeness_cycle,
		"total_pairs": doc.total_pairs,
		"assigned_pairs": doc.assigned_pairs,
		"completed_pairs": doc.completed_pairs,
		"completion_pct": doc.completion_pct,
		"current_batch": doc.current_batch,
		"by_status": dict(by_status),
	}


def refresh_cycle_stats(doc):
	"""Mark pairs Completed when Survey Response exists; recompute totals."""
	if isinstance(doc, str):
		doc = frappe.get_doc("Survey Cycle", doc)

	changed = False
	assigned = 0
	completed = 0
	for p in doc.pairs or []:
		if p.survey and frappe.db.exists("Survey Response", {"survey": p.survey}):
			if p.status != "Completed":
				p.status = "Completed"
				changed = True
		if p.status in ("Assigned", "Completed", "Overdue"):
			assigned += 1
		if p.status == "Completed":
			completed += 1
		# Overdue: assigned, past period end, not completed
		if (
			p.status == "Assigned"
			and doc.period_end
			and getdate(today()) > getdate(doc.period_end)
		):
			p.status = "Overdue"
			changed = True

	total = len(doc.pairs or [])
	doc.total_pairs = total
	doc.assigned_pairs = assigned
	doc.completed_pairs = completed
	doc.completion_pct = round((completed / total * 100), 1) if total else 0
	if changed or True:
		doc.save(ignore_permissions=True)
		frappe.db.commit()
	return doc


# ---------------------------------------------------------------------------
# Batch assignment
# ---------------------------------------------------------------------------

@frappe.whitelist()
def run_cycle_batch(force=0, trigger_source="Manual"):
	"""Assign next batch of Planned pairs and create surveys."""
	settings = _settings()
	doc = get_or_create_open_cycle()
	refresh_cycle_stats(doc)
	doc.reload()

	if doc.status == "Closed":
		return {"status": "closed", "cycle": doc.name}

	planned = [p for p in doc.pairs if p.status == "Planned"]
	if not planned:
		return {
			"status": "nothing_to_assign",
			"cycle": doc.name,
			"completion_pct": doc.completion_pct,
			"created": 0,
		}

	# Group remaining planned by reviewer for fair quotas
	by_reviewer = defaultdict(list)
	for p in planned:
		by_reviewer[p.reviewer].append(p)

	batches_total = _batches_in_cycle(doc.survey_frequency or "Weekly", doc.completeness_cycle or "Quarterly")
	batches_left = max(1, batches_total - cint(doc.current_batch))
	cap = cint(settings.max_surveys_per_reviewer) or 10
	min_per = cint(getattr(settings, "min_surveys_per_batch", None)) or 3

	to_assign = []
	for reviewer, plist in by_reviewer.items():
		quota = _reviewer_batch_quota(len(plist), batches_left, min_per, cap)
		to_assign.extend(plist[:quota])

	batch_no = cint(doc.current_batch) + 1
	doc.status = "Generating"
	created = 0
	emails = 0
	details = []
	errors = []

	for p in to_assign:
		try:
			survey_name = create_survey_and_send_invitation(
				sender_employee=p.reviewer,
				receiver_employee=p.reviewee,
			)
			p.survey = survey_name
			p.status = "Assigned"
			p.batch_no = batch_no
			notify = send_survey_notification_and_task(
				survey_name,
				sender_employee=p.reviewer,
				receiver_employee=p.reviewee,
				cycle=doc.name,
			) or {}
			created += 1
			if notify.get("email_sent"):
				emails += 1
			details.append({
				"survey": survey_name,
				"reviewer": p.reviewer,
				"reviewer_name": p.reviewer_name or frappe.db.get_value("Employee", p.reviewer, "employee_name"),
				"reviewer_email": notify.get("reviewer_email"),
				"reviewee": p.reviewee,
				"reviewee_name": p.reviewee_name or frappe.db.get_value("Employee", p.reviewee, "employee_name"),
				"task": notify.get("task"),
				"email_sent": 1 if notify.get("email_sent") else 0,
			})
		except Exception as e:
			errors.append(f"{p.reviewer}->{p.reviewee}: {e}")
			frappe.log_error(title="Cycle Batch Pair Failed", message=frappe.get_traceback())

	doc.current_batch = batch_no
	doc.status = "Open"
	doc.save(ignore_permissions=True)
	refresh_cycle_stats(doc)

	from survey_app.surveys import _create_generation_log
	log_name = _create_generation_log(
		trigger_source=trigger_source or "Manual",
		frequency=doc.survey_frequency,
		status="Partial" if errors else ("Success" if created else "Skipped"),
		details=details,
		summary=f"Cycle {doc.name} batch {batch_no}: created {created}",
		error_message="\n".join(errors[:20]),
	)

	return {
		"status": "generated",
		"cycle": doc.name,
		"batch_no": batch_no,
		"created": created,
		"emails_sent": emails,
		"errors": len(errors),
		"log": log_name,
		"completion_pct": frappe.db.get_value("Survey Cycle", doc.name, "completion_pct"),
	}


@frappe.whitelist()
def get_cycle_status():
	if not frappe.db.exists("DocType", "Survey Cycle"):
		return {"status": "unavailable"}
	open_cycle = frappe.db.get_value(
		"Survey Cycle",
		{"status": ["in", ["Open", "Generating", "Reporting"]]},
		"name",
		order_by="period_start desc",
	)
	if not open_cycle:
		return {"status": "no_open_cycle", "preview": preview_cycle_load()}
	return {
		"status": "ok",
		"cycle": cycle_summary(open_cycle),
		"preview": preview_cycle_load(),
	}

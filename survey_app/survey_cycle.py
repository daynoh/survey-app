"""Survey Cycle: roles, required review matrix, load math, and batch assignment."""

from __future__ import annotations

import hashlib
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

from survey_app.permissions import survey_admin_required
from survey_app.surveys import FREQUENCY_INTERVALS, create_survey_and_send_invitation, send_survey_notification_and_task


CYCLE_INTERVALS = {
	"Monthly": {"months": 1},
	"Quarterly": {"months": 3},
	"Bi-Annually": {"months": 6},
	"Yearly": {"months": 12},
}

BALANCED_STRATEGY = "Balanced Coverage"
FULL_BASELINE_STRATEGY = "Full Baseline Matrix"
CYCLE_STRATEGIES = {BALANCED_STRATEGY, FULL_BASELINE_STRATEGY}


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


def _exco_oversight(settings):
	"""Map EXCO member -> list of departments they oversee, from settings rows."""
	exco_map = defaultdict(list)
	for row in getattr(settings, "exco_oversight", None) or []:
		employee = getattr(row, "employee", None)
		department = getattr(row, "department", None)
		if employee and department and department not in exco_map[employee]:
			exco_map[employee].append(department)
	return dict(exco_map)


def _exco_violation(exco_map, exco_employees, md_name, dept_by_employee, reviewer, reviewee):
	"""True when a pair breaks the EXCO circle.

	Circle: an EXCO member only reviews, and is only reviewed by, members of the
	department(s) they oversee, other EXCO members, and the MD. Exclusions are
	enforced separately and always take precedence over the circle.
	"""
	if reviewer not in exco_employees and reviewee not in exco_employees:
		return False
	if reviewer in exco_employees and reviewee in exco_employees:
		return False

	def _outside_circle(exco_member, other):
		if other == md_name:
			return False
		departments = exco_map.get(exco_member) or []
		return dept_by_employee.get(other) not in departments

	if reviewer in exco_employees:
		return _outside_circle(reviewer, reviewee)
	return _outside_circle(reviewee, reviewer)


# ---------------------------------------------------------------------------
# Role resolution
# ---------------------------------------------------------------------------

@frappe.whitelist()
@survey_admin_required
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

def _normalise_cycle_strategy(strategy=None):
	strategy = strategy or BALANCED_STRATEGY
	if strategy not in CYCLE_STRATEGIES:
		frappe.throw(f"Unsupported cycle strategy: {strategy}")
	return strategy


def _stable_token(seed, *parts):
	value = "|".join(str(part or "") for part in (seed, *parts))
	return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _pair_context(roles):
	settings = _settings()
	excluded_reviewees, excluded_reviewers = _excluded_employees(settings)
	employees = _active_employees(exclude_names=excluded_reviewees)

	by_dept = defaultdict(list)
	for e in employees:
		if e.department:
			by_dept[e.department].append(e)
	for members in by_dept.values():
		members.sort(key=lambda employee: employee.name)

	md = roles.get("md")
	md_name = md["name"] if md else None
	tl_by_dept = {t["department"]: t["employee"] for t in roles.get("team_leaders") or []}
	nearness = frappe.get_all(
		"Departmental Nearness Factor",
		fields=["department", "department2", "factor"],
	)
	nearness_map = {(row.department, row.department2): flt(row.factor) for row in nearness}

	exco_map = _exco_oversight(settings)
	exco_employees = {name for name in exco_map if name in employees_by_name}
	dept_by_employee = {e.name: e.department for e in employees}

	def exco_pair_allowed(reviewer, reviewee):
		return not _exco_violation(
			exco_map, exco_employees, md_name, dept_by_employee, reviewer, reviewee
		)

	return {
		"settings": settings,
		"employees": employees,
		"employees_by_name": {employee.name: employee for employee in employees},
		"by_dept": by_dept,
		"excluded_reviewees": excluded_reviewees,
		"excluded_reviewers": excluded_reviewers,
		"md_name": md_name,
		"tl_by_dept": tl_by_dept,
		"nearness_map": nearness_map,
		"exco_map": exco_map,
		"exco_employees": exco_employees,
		"exco_pair_allowed": exco_pair_allowed,
	}


def _weighted_department_slots(weights, count, seed):
	"""Allocate exactly count slots using largest remainders; no forced one-per-link."""
	count = max(0, cint(count))
	positive = {department: flt(weight) for department, weight in weights.items() if flt(weight) > 0}
	total_weight = sum(positive.values())
	if not count or total_weight <= 0:
		return []

	quotas = {}
	remainders = []
	for department, weight in positive.items():
		raw = (weight / total_weight) * count
		whole = math.floor(raw)
		quotas[department] = whole
		remainders.append(
			(raw - whole, weight, _stable_token(seed, department), department)
		)
	remaining = count - sum(quotas.values())
	for _, _, _, department in sorted(remainders, key=lambda row: (-row[0], -row[1], row[2]))[:remaining]:
		quotas[department] += 1

	slots = [
		(department, index)
		for department, quota in quotas.items()
		for index in range(quota)
	]
	slots.sort(key=lambda slot: _stable_token(seed, "slot", slot[0], slot[1]))
	return [department for department, _ in slots]


def _build_full_baseline_pairs(roles, cycle_key=None):
	"""Build exhaustive organisation coverage while rotating departmental reviewers fairly."""
	context = _pair_context(roles)
	settings = context["settings"]
	by_dept = context["by_dept"]
	excluded_reviewers = context["excluded_reviewers"]
	seed = cycle_key or FULL_BASELINE_STRATEGY

	pairs = []
	seen = set()
	reviewer_load = defaultdict(int)

	def add_pair(reviewer, reviewee, rule_type):
		if not reviewer or not reviewee or reviewer == reviewee:
			return False
		if reviewer in excluded_reviewers or reviewee in context["excluded_reviewees"]:
			return False
		if not context["exco_pair_allowed"](reviewer, reviewee):
			return False
		key = (reviewer, reviewee)
		if key in seen:
			return False
		seen.add(key)
		pairs.append({
			"reviewer": reviewer,
			"reviewee": reviewee,
			"rule_type": rule_type,
		})
		reviewer_load[reviewer] += 1
		return True

	# Team Leader → each team member (before peers so rule_type is preserved)
	for dept, tl in context["tl_by_dept"].items():
		for m in by_dept.get(dept, []):
			add_pair(tl, m.name, "TeamLeader")

	# Team Leader → MD
	if context["md_name"]:
		for _, tl in context["tl_by_dept"].items():
			add_pair(tl, context["md_name"], "TL_to_MD")

	# EXCO oversight circle: supervised team both ways, EXCO peers, and the MD.
	for exco_member, departments in context["exco_map"].items():
		if exco_member not in context["employees_by_name"]:
			continue
		for department in departments:
			for m in by_dept.get(department, []):
				add_pair(exco_member, m.name, "Exco Oversight")
				add_pair(m.name, exco_member, "Exco Oversight")
		for other_exco in context["exco_employees"]:
			if other_exco != exco_member:
				add_pair(exco_member, other_exco, "Exco Peer")
		if context["md_name"]:
			add_pair(exco_member, context["md_name"], "Exco to MD")

	# Peers: every teammate surveys every other teammate (EXCO handled above)
	exco_employees = context["exco_employees"]
	for _, members in by_dept.items():
		names = [m.name for m in members if m.name not in exco_employees]
		for a in names:
			for b in names:
				if a != b:
					add_pair(a, b, "Peer")

	# Every positive matrix link is represented in the baseline. Candidate choice is load-balanced.
	max_per_employee = cint(settings.max_surveys_per_employee) or 10
	for dept, members in by_dept.items():
		other_depts = [d for d in by_dept.keys() if d != dept]
		total_weight = sum(context["nearness_map"].get((dept, od), 0) for od in other_depts)
		if total_weight <= 0:
			continue
		external_needed = max(1, math.ceil(max_per_employee * 0.4))
		for od in other_depts:
			weight = context["nearness_map"].get((dept, od), 0)
			if weight <= 0:
				continue
			quota = max(1, math.ceil((weight / total_weight) * external_needed))
			candidates = [
				m.name
				for m in by_dept.get(od, [])
				if m.name not in excluded_reviewers and m.name not in exco_employees
			]
			for reviewee in members:
				if reviewee.name in exco_employees:
					continue
				ordered = sorted(
					candidates,
					key=lambda reviewer: (
						reviewer_load[reviewer],
						_stable_token(seed, dept, od, reviewee.name, reviewer),
					),
				)
				added = 0
				for reviewer in ordered:
					if add_pair(reviewer, reviewee.name, "Nearness"):
						added += 1
					if added >= quota:
						break

	return pairs


def _build_balanced_pairs(roles, cycle_key=None):
	"""Build a recurring cycle with target coverage, weighted nearness, and fair reviewer load."""
	context = _pair_context(roles)
	settings = context["settings"]
	employees = context["employees"]
	employees_by_name = context["employees_by_name"]
	by_dept = context["by_dept"]
	seed = cycle_key or BALANCED_STRATEGY
	target = max(1, cint(getattr(settings, "balanced_reviews_per_employee", None)) or 6)
	reviewer_cap = max(target, cint(getattr(settings, "balanced_max_surveys_per_reviewer", None)) or 10)
	external_target = min(target, max(1, math.ceil(target * 0.4))) if target > 1 else 0
	internal_target = target - external_target

	pairs = []
	seen = set()
	reviewer_load = defaultdict(int)
	reviewee_coverage = defaultdict(int)
	internal_coverage = defaultdict(int)
	external_coverage = defaultdict(int)

	def add_pair(reviewer, reviewee, rule_type, mandatory=False):
		if not reviewer or not reviewee or reviewer == reviewee:
			return False
		if reviewer in context["excluded_reviewers"] or reviewee in context["excluded_reviewees"]:
			return False
		if not context["exco_pair_allowed"](reviewer, reviewee):
			return False
		if not mandatory and reviewer_load[reviewer] >= reviewer_cap:
			return False
		key = (reviewer, reviewee)
		if key in seen:
			return False
		seen.add(key)
		pairs.append({"reviewer": reviewer, "reviewee": reviewee, "rule_type": rule_type})
		reviewer_load[reviewer] += 1
		reviewee_coverage[reviewee] += 1
		reviewer_department = (employees_by_name.get(reviewer) or frappe._dict()).get("department")
		reviewee_department = (employees_by_name.get(reviewee) or frappe._dict()).get("department")
		if reviewer_department and reviewer_department == reviewee_department:
			internal_coverage[reviewee] += 1
		else:
			external_coverage[reviewee] += 1
		return True

	# Mandatory organisation constraints are always planned first.
	for dept, team_leader in context["tl_by_dept"].items():
		for member in by_dept.get(dept, []):
			add_pair(team_leader, member.name, "TeamLeader", mandatory=True)
	if context["md_name"]:
		for _, team_leader in context["tl_by_dept"].items():
			add_pair(team_leader, context["md_name"], "TL_to_MD", mandatory=True)

	# EXCO oversight circle: supervised team both ways, EXCO peers, and the MD.
	# Mandatory so circle coverage never falls victim to reviewer caps.
	for exco_member, departments in context["exco_map"].items():
		if exco_member not in context["employees_by_name"]:
			continue
		for department in departments:
			for m in by_dept.get(department, []):
				add_pair(exco_member, m.name, "Exco Oversight", mandatory=True)
				add_pair(m.name, exco_member, "Exco Oversight", mandatory=True)
		for other_exco in context["exco_employees"]:
			if other_exco != exco_member:
				add_pair(exco_member, other_exco, "Exco Peer", mandatory=True)
		if context["md_name"]:
			add_pair(exco_member, context["md_name"], "Exco to MD", mandatory=True)

	def choose_candidate(candidates, reviewee, salt):
		eligible = [
			candidate
			for candidate in candidates
			if candidate != reviewee
			and candidate not in context["excluded_reviewers"]
			and candidate not in context["exco_employees"]
			and (candidate, reviewee) not in seen
			and reviewer_load[candidate] < reviewer_cap
		]
		if not eligible:
			return None
		return min(
			eligible,
			key=lambda candidate: (
				reviewer_load[candidate],
				_stable_token(seed, salt, reviewee, candidate),
			),
		)

	reviewees = [
		employee
		for employee in employees
		if employee.department and employee.name not in context["exco_employees"]
	]
	reviewees.sort(key=lambda employee: _stable_token(seed, "reviewee", employee.name))
	for reviewee in reviewees:
		if reviewee_coverage[reviewee.name] >= target:
			continue

		internal_candidates = [
			member.name
			for member in by_dept.get(reviewee.department, [])
			if member.name not in context["exco_employees"]
		]
		internal_needed = max(0, internal_target - internal_coverage[reviewee.name])
		while internal_needed > 0 and reviewee_coverage[reviewee.name] < target:
			candidate = choose_candidate(internal_candidates, reviewee.name, "internal")
			if not candidate:
				break
			if add_pair(candidate, reviewee.name, "Peer"):
				internal_needed -= 1

		external_needed = max(0, external_target - external_coverage[reviewee.name])
		weights = {
			department: context["nearness_map"].get((reviewee.department, department), 0)
			for department in by_dept.keys()
			if department != reviewee.department
		}
		for department in _weighted_department_slots(
			weights,
			external_needed,
			f"{seed}|{reviewee.name}|external",
		):
			candidates = [member.name for member in by_dept.get(department, [])]
			candidate = choose_candidate(candidates, reviewee.name, f"external|{department}")
			if candidate:
				add_pair(candidate, reviewee.name, "Nearness")

		# Fill any capacity left using only valid peer or positive-nearness relationships.
		valid_external = [
			member.name
			for department, members in by_dept.items()
			if department != reviewee.department and flt(weights.get(department)) > 0
			for member in members
		]
		fallback_candidates = internal_candidates + valid_external
		while reviewee_coverage[reviewee.name] < target:
			candidate = choose_candidate(fallback_candidates, reviewee.name, "fallback")
			if not candidate:
				break
			candidate_department = employees_by_name[candidate].department
			rule_type = "Peer" if candidate_department == reviewee.department else "Nearness"
			add_pair(candidate, reviewee.name, rule_type)

	return pairs


def build_required_pairs(roles=None, strategy=None, cycle_key=None):
	"""Return the planned pairs for the requested cycle strategy."""
	roles = roles or resolve_org_roles()
	strategy = _normalise_cycle_strategy(strategy)
	if strategy == FULL_BASELINE_STRATEGY:
		return _build_full_baseline_pairs(roles, cycle_key=cycle_key)
	return _build_balanced_pairs(roles, cycle_key=cycle_key)


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
@survey_admin_required
def preview_cycle_load(strategy=None):
	"""Estimated load per reviewer for the planned matrix + batch size."""
	settings = _settings()
	roles = resolve_org_roles()
	if strategy:
		selected_strategy = _normalise_cycle_strategy(strategy)
	else:
		selected_strategy = frappe.db.get_value(
			"Survey Cycle",
			{"status": ["in", ["Open", "Generating", "Reporting"]]},
			"generation_strategy",
			order_by="period_start desc",
		) or BALANCED_STRATEGY
		selected_strategy = _normalise_cycle_strategy(selected_strategy)
	survey_freq = settings.generation_frequency or "Weekly"
	cycle = settings.completeness_cycle or "Quarterly"
	period_start, period_end = _cycle_period(cycle)
	pairs = build_required_pairs(
		roles,
		strategy=selected_strategy,
		cycle_key=f"{period_start}|{period_end}|{selected_strategy}",
	)

	batches = _batches_in_cycle(survey_freq, cycle)
	by_reviewer = defaultdict(int)
	by_reviewee = defaultdict(int)
	by_rule = defaultdict(int)
	for p in pairs:
		by_reviewer[p["reviewer"]] += 1
		by_reviewee[p["reviewee"]] += 1
		by_rule[p["rule_type"]] += 1

	emp_names = {e.name: e.employee_name for e in _active_employees()}
	load_rows = []
	warnings = list(roles.get("warnings") or [])
	cap = cint(settings.max_surveys_per_reviewer) or 10
	min_per = cint(getattr(settings, "min_surveys_per_batch", None)) or 3
	balanced_target = max(1, cint(getattr(settings, "balanced_reviews_per_employee", None)) or 6)
	balanced_cycle_cap = max(
		balanced_target,
		cint(getattr(settings, "balanced_max_surveys_per_reviewer", None)) or 10,
	)

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
			"review_only": False,
			"reviews_received": by_reviewee.get(reviewer, 0),
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

	# People who receive reviews but give none (e.g. the MD) still belong in the roster.
	for reviewee, received in sorted(by_reviewee.items(), key=lambda x: (-x[1], x[0])):
		if reviewee in by_reviewer:
			continue
		load_rows.append(
			{
				"reviewer": reviewee,
				"reviewer_name": emp_names.get(reviewee, reviewee),
				"required_surveys": 0,
				"batches_in_cycle": batches,
				"even_split": 0,
				"per_batch": 0,
				"over_cap": False,
				"under_min": False,
				"review_only": True,
				"reviews_received": received,
			}
		)

	if selected_strategy == BALANCED_STRATEGY:
		excluded_reviewees, _ = _excluded_employees(settings)
		exco_employees = set(_exco_oversight(settings))
		under_target = [
			employee
			for employee in _active_employees(exclude_names=excluded_reviewees)
			if employee.department
			and employee.name not in exco_employees
			and by_reviewee[employee.name] < balanced_target
		]
		if under_target:
			warnings.append(
				f"{len(under_target)} employee(s) could not reach the Balanced Coverage target of "
				f"{balanced_target}. Add valid nearness links, eligible peers, or raise the reviewer cycle cap."
			)
		mandatory_over_cap = [
			reviewer for reviewer, count in by_reviewer.items() if count > balanced_cycle_cap
		]
		if mandatory_over_cap:
			warnings.append(
				f"{len(mandatory_over_cap)} reviewer(s) exceed the per-cycle safety cap because mandatory "
				"leadership assignments are preserved."
			)

	loads = list(by_reviewer.values())
	coverages = list(by_reviewee.values())

	return {
		"roles": roles,
		"total_pairs": len(pairs),
		"by_rule": dict(by_rule),
		"survey_frequency": survey_freq,
		"completeness_cycle": cycle,
		"batches_in_cycle": batches,
		"min_surveys_per_batch": min_per,
		"max_surveys_per_reviewer": cap,
		"balanced_reviews_per_employee": balanced_target,
		"balanced_max_surveys_per_reviewer": balanced_cycle_cap,
		"average_reviewer_load": round(len(pairs) / len(loads), 1) if loads else 0,
		"minimum_reviewer_load": min(loads) if loads else 0,
		"maximum_reviewer_load": max(loads) if loads else 0,
		"minimum_reviews_received": min(coverages) if coverages else 0,
		"maximum_reviews_received": max(coverages) if coverages else 0,
		"load": load_rows[:100],
		"warnings": warnings,
		"generation_mode": getattr(settings, "generation_mode", None) or "Cycle Matrix",
		"generation_strategy": selected_strategy,
	}


@frappe.whitelist()
@survey_admin_required
def preview_cycle_assignments(cycle=None):
	"""Return the exact HR-only reviewer/reviewee plan without survey responses."""
	roles = resolve_org_roles()
	settings = _settings()
	excluded_reviewees, excluded_reviewers = _excluded_employees(settings)
	warnings = list(roles.get("warnings") or [])
	doc = None

	if cycle:
		if not frappe.db.exists("Survey Cycle", cycle):
			frappe.throw("Survey Cycle not found")
		doc = frappe.get_doc("Survey Cycle", cycle)
	else:
		open_cycle = frappe.db.get_value(
			"Survey Cycle",
			{"status": ["in", ["Open", "Generating", "Reporting"]]},
			"name",
			order_by="period_start desc",
		)
		if open_cycle:
			doc = frappe.get_doc("Survey Cycle", open_cycle)

	if doc:
		selected_strategy = _normalise_cycle_strategy(doc.generation_strategy or BALANCED_STRATEGY)
		pairs = [
			{
				"reviewer": p.reviewer,
				"reviewee": p.reviewee,
				"rule_type": p.rule_type,
				"status": p.status or "Planned",
				"batch_no": cint(p.batch_no),
			}
			for p in (doc.pairs or [])
		]
		source = "cycle"
	else:
		selected_strategy = BALANCED_STRATEGY
		pairs = [
			{
				**p,
				"status": "Planned",
				"batch_no": 0,
			}
			for p in build_required_pairs(roles, strategy=selected_strategy)
		]
		source = "calculated"

	exclusion_conflicts = None
	if source == "cycle" and (excluded_reviewees or excluded_reviewers):
		conflict_pairs = [
			p
			for p in pairs
			if p.get("reviewer") in excluded_reviewers or p.get("reviewee") in excluded_reviewees
		]
		if conflict_pairs:
			planned_conflicts = sum(
				1 for p in conflict_pairs if (p.get("status") or "Planned") == "Planned"
			)
			involved = set()
			for p in conflict_pairs:
				if p.get("reviewer") in excluded_reviewers:
					involved.add(p["reviewer"])
				if p.get("reviewee") in excluded_reviewees:
					involved.add(p["reviewee"])
			exclusion_conflicts = {
				"total": len(conflict_pairs),
				"planned": planned_conflicts,
				"assigned": len(conflict_pairs) - planned_conflicts,
				"employees": sorted(involved),
			}
			warnings.append(
				f"{len(conflict_pairs)} stored pair(s) involve employees now excluded from rating "
				"or being rated. Remove them from the plan or rebuild the cycle to apply exclusions."
			)

	md_row = roles.get("md")
	md_name = md_row["name"] if md_row else None
	exco_map = _exco_oversight(settings)
	exco_conflicts = None
	if source == "cycle" and exco_map:
		dept_by_employee = {e.name: e.department for e in employee_rows}
		exco_employees = {name for name in exco_map if name in dept_by_employee}
		exco_conflict_pairs = [
			p
			for p in pairs
			if _exco_violation(
				exco_map,
				exco_employees,
				md_name,
				dept_by_employee,
				p.get("reviewer"),
				p.get("reviewee"),
			)
		]
		if exco_conflict_pairs:
			exco_planned = sum(
				1 for p in exco_conflict_pairs if (p.get("status") or "Planned") == "Planned"
			)
			exco_involved = set()
			for p in exco_conflict_pairs:
				if p.get("reviewer") in exco_employees:
					exco_involved.add(p["reviewer"])
				if p.get("reviewee") in exco_employees:
					exco_involved.add(p["reviewee"])
			exco_conflicts = {
				"total": len(exco_conflict_pairs),
				"planned": exco_planned,
				"assigned": len(exco_conflict_pairs) - exco_planned,
				"employees": sorted(exco_involved),
			}
			warnings.append(
				f"{len(exco_conflict_pairs)} stored pair(s) fall outside the EXCO review circle "
				"(supervised team, EXCO peers, and the MD only). Purge them or rebuild the cycle."
			)

	employee_names = sorted(
		{p.get("reviewer") for p in pairs if p.get("reviewer")}
		| {p.get("reviewee") for p in pairs if p.get("reviewee")}
	)
	employee_rows = []
	if employee_names:
		employee_rows = frappe.get_all(
			"Employee",
			filters={"name": ["in", employee_names]},
			fields=["name", "employee_name", "department"],
		)
	employees = {e.name: e for e in employee_rows}

	excluded_people = []
	if excluded_reviewees or excluded_reviewers:
		for row in frappe.get_all(
			"Employee",
			filters={"name": ["in", sorted(excluded_reviewees | excluded_reviewers)]},
			fields=["name", "employee_name"],
			order_by="employee_name",
		):
			excluded_people.append(
				{
					"employee": row.name,
					"employee_name": row.employee_name,
					"cannot_rate": row.name in excluded_reviewers,
					"cannot_be_rated": row.name in excluded_reviewees,
				}
			)

	reviewer_load = defaultdict(int)
	reviewee_coverage = defaultdict(int)
	by_rule = defaultdict(int)
	rows = []
	for pair in pairs:
		reviewer = pair.get("reviewer")
		reviewee = pair.get("reviewee")
		reviewer_row = employees.get(reviewer) or frappe._dict()
		reviewee_row = employees.get(reviewee) or frappe._dict()
		reviewer_load[reviewer] += 1
		reviewee_coverage[reviewee] += 1
		by_rule[pair.get("rule_type") or "Other"] += 1
		rows.append(
			{
				"reviewer": reviewer,
				"reviewer_name": reviewer_row.get("employee_name") or reviewer,
				"reviewer_department": reviewer_row.get("department") or "",
				"reviewee": reviewee,
				"reviewee_name": reviewee_row.get("employee_name") or reviewee,
				"reviewee_department": reviewee_row.get("department") or "",
				"rule_type": pair.get("rule_type") or "Other",
				"status": pair.get("status") or "Planned",
				"batch_no": cint(pair.get("batch_no")),
			}
		)

	for row in rows:
		row["reviewer_cycle_load"] = reviewer_load[row["reviewer"]]
		row["reviewee_coverage"] = reviewee_coverage[row["reviewee"]]
	rows.sort(
		key=lambda row: (
			(row.get("reviewer_name") or "").lower(),
			(row.get("reviewee_name") or "").lower(),
			row.get("rule_type") or "",
		)
	)

	load_rows = [
		{
			"reviewer": reviewer,
			"reviewer_name": (employees.get(reviewer) or frappe._dict()).get("employee_name") or reviewer,
			"department": (employees.get(reviewer) or frappe._dict()).get("department") or "",
			"required_surveys": count,
			"reviews_received": reviewee_coverage.get(reviewer, 0),
			"review_only": False,
		}
		for reviewer, count in reviewer_load.items()
	]
	# Review-only people (reviewed but reviewing nobody) stay visible with a zero load.
	for reviewee, received in reviewee_coverage.items():
		if reviewee in reviewer_load:
			continue
		load_rows.append(
			{
				"reviewer": reviewee,
				"reviewer_name": (employees.get(reviewee) or frappe._dict()).get("employee_name") or reviewee,
				"department": (employees.get(reviewee) or frappe._dict()).get("department") or "",
				"required_surveys": 0,
				"reviews_received": received,
				"review_only": True,
			}
		)
	load_rows.sort(key=lambda row: (-row["required_surveys"], (row["reviewer_name"] or "").lower()))
	loads = list(reviewer_load.values())
	departments = sorted(
		{
			row[department_key]
			for row in rows
			for department_key in ("reviewer_department", "reviewee_department")
			if row[department_key]
		}
	)

	return {
		"source": source,
		"is_cycle_plan": source == "cycle",
		"generation_strategy": selected_strategy,
		"cycle": {
			"name": doc.name,
			"title": doc.title,
			"status": doc.status,
			"current_batch": cint(doc.current_batch),
			"generation_strategy": selected_strategy,
		} if doc else None,
		"summary": {
			"total_pairs": len(rows),
			"reviewers": len(reviewer_load),
			"reviewees": len(reviewee_coverage),
			"average_load": round(len(rows) / len(reviewer_load), 1) if reviewer_load else 0,
			"minimum_load": min(loads) if loads else 0,
			"maximum_load": max(loads) if loads else 0,
		},
		"by_rule": dict(by_rule),
		"departments": departments,
		"rules": sorted(by_rule.keys()),
		"statuses": sorted({row["status"] for row in rows}),
		"exclusion_conflicts": exclusion_conflicts,
		"exco_conflicts": exco_conflicts,
		"excluded_people": excluded_people,
		"load": load_rows,
		"rows": rows,
		"warnings": warnings,
	}


@frappe.whitelist()
@survey_admin_required
def purge_excluded_pairs(cycle=None):
	"""Drop Planned pairs that violate exclusions or the EXCO review circle.

	Assigned/Completed pairs are never touched — they already have surveys in flight.
	Exclusions always take precedence over the EXCO circle.
	"""
	settings = _settings()
	excluded_reviewees, excluded_reviewers = _excluded_employees(settings)
	exco_map = _exco_oversight(settings)
	if not excluded_reviewees and not excluded_reviewers and not exco_map:
		frappe.throw("No exclusions or EXCO oversight rules are configured.")

	doc = None
	if cycle:
		if not frappe.db.exists("Survey Cycle", cycle):
			frappe.throw("Survey Cycle not found")
		doc = frappe.get_doc("Survey Cycle", cycle)
	else:
		open_cycle = frappe.db.get_value(
			"Survey Cycle",
			{"status": ["in", ["Open", "Generating", "Reporting"]]},
			"name",
			order_by="period_start desc",
		)
		if open_cycle:
			doc = frappe.get_doc("Survey Cycle", open_cycle)
	if not doc:
		frappe.throw("No open Survey Cycle to clean.")

	roles = resolve_org_roles()
	md_row = roles.get("md")
	md_name = md_row["name"] if md_row else None

	participants = set()
	for pair in doc.pairs or []:
		participants.add(pair.reviewer)
		participants.add(pair.reviewee)
	dept_by_employee = {
		row.name: row.department
		for row in frappe.get_all(
			"Employee",
			filters={"name": ["in", sorted(participants)]},
			fields=["name", "department"],
		)
	}
	exco_employees = {name for name in exco_map if name in dept_by_employee}

	kept = []
	removed = 0
	exco_removed = 0
	skipped = 0
	for pair in doc.pairs or []:
		breaks_exclusion = pair.reviewer in excluded_reviewers or pair.reviewee in excluded_reviewees
		breaks_exco = _exco_violation(
			exco_map, exco_employees, md_name, dept_by_employee, pair.reviewer, pair.reviewee
		)
		if (breaks_exclusion or breaks_exco) and (pair.status or "Planned") == "Planned":
			removed += 1
			if breaks_exco and not breaks_exclusion:
				exco_removed += 1
			continue
		if breaks_exclusion or breaks_exco:
			skipped += 1
		kept.append(pair)

	if removed:
		doc.pairs = kept
		doc.total_pairs = len(kept)
		doc.flags.ignore_permissions = True
		doc.save()
		frappe.db.commit()

	return {
		"cycle": doc.name,
		"removed": removed,
		"exco_removed": exco_removed,
		"kept_assigned_or_completed": skipped,
		"remaining_pairs": len(kept),
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

def _cycle_strategy_locked(doc):
	return bool(
		cint(doc.current_batch)
		or cint(doc.assigned_pairs)
		or any(
			pair.status != "Planned" or pair.survey
			for pair in (doc.pairs or [])
		)
	)


def get_or_create_open_cycle(force_rebuild=False, strategy=None):
	settings = _settings()
	start, end = _cycle_period(settings.completeness_cycle or "Quarterly")
	existing = frappe.db.get_value(
		"Survey Cycle",
		{"period_start": start, "period_end": end, "status": ["in", ["Open", "Generating", "Reporting"]]},
		"name",
	)
	existing_doc = frappe.get_doc("Survey Cycle", existing) if existing else None
	if existing_doc and not force_rebuild:
		return existing_doc

	if existing_doc and force_rebuild:
		if _cycle_strategy_locked(existing_doc):
			frappe.throw("The cycle plan cannot be rebuilt after survey generation has started.")
		strategy = strategy or existing_doc.generation_strategy or BALANCED_STRATEGY
		frappe.delete_doc("Survey Cycle", existing_doc.name, ignore_permissions=True, force=1)

	strategy = _normalise_cycle_strategy(strategy)
	roles = resolve_org_roles()
	pairs = build_required_pairs(
		roles,
		strategy=strategy,
		cycle_key=f"{start}|{end}|{strategy}",
	)
	title = f"Cycle {start} → {end}"

	doc = frappe.get_doc({
		"doctype": "Survey Cycle",
		"title": title,
		"status": "Open",
		"generation_strategy": strategy,
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
@survey_admin_required
def ensure_cycle(force_rebuild=0, strategy=None):
	doc = get_or_create_open_cycle(
		force_rebuild=cint(force_rebuild),
		strategy=strategy or None,
	)
	refresh_cycle_stats(doc)
	return cycle_summary(doc)


@frappe.whitelist()
@survey_admin_required
def set_cycle_strategy(strategy):
	"""Select and rebuild an unstarted cycle plan; new cycles still default to Balanced."""
	strategy = _normalise_cycle_strategy(strategy)
	doc = get_or_create_open_cycle(strategy=strategy)
	if _cycle_strategy_locked(doc):
		frappe.throw("The cycle strategy is locked because survey generation has already started.")
	if (doc.generation_strategy or BALANCED_STRATEGY) == strategy and doc.pairs:
		return cycle_summary(doc)

	roles = resolve_org_roles()
	pairs = build_required_pairs(
		roles,
		strategy=strategy,
		cycle_key=f"{doc.period_start}|{doc.period_end}|{strategy}",
	)
	doc.generation_strategy = strategy
	doc.set("pairs", [])
	for pair in pairs:
		doc.append(
			"pairs",
			{
				"reviewer": pair["reviewer"],
				"reviewee": pair["reviewee"],
				"rule_type": pair["rule_type"],
				"batch_no": 0,
				"status": "Planned",
			},
		)
	doc.total_pairs = len(pairs)
	doc.assigned_pairs = 0
	doc.completed_pairs = 0
	doc.completion_pct = 0
	doc.current_batch = 0
	doc.save(ignore_permissions=True)
	frappe.db.commit()
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
		"generation_strategy": _normalise_cycle_strategy(doc.generation_strategy or BALANCED_STRATEGY),
		"strategy_locked": _cycle_strategy_locked(doc),
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
@survey_admin_required
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
@survey_admin_required
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

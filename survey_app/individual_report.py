"""Automated individual performance reports for survey cycles."""

from __future__ import annotations

import base64
import os
from collections import defaultdict

import frappe
from frappe.utils import (
	add_to_date,
	cint,
	flt,
	formatdate,
	get_datetime,
	getdate,
	now_datetime,
	today,
)

from survey_app.performance import (
	aggregate_rows as _aggregate,
	build_employee_scorecard,
	get_org_benchmarks as _org_benchmarks,
	get_score_rows as _score_rows,
	percentile_rank as _percentile_rank,
)
from survey_app.permissions import survey_admin_required
from survey_app.surveys import FREQUENCY_INTERVALS
from survey_app.survey_cycle import (
	CYCLE_INTERVALS,
	get_or_create_open_cycle,
	refresh_cycle_stats,
	resolve_org_roles,
	_cycle_period,
)


@frappe.whitelist()
@survey_admin_required
def auto_send_reports_if_due(force=0):
	settings = frappe.get_doc("Value Scoring Settings")
	if not cint(force) and not cint(getattr(settings, "enable_scheduled_reports", 0)):
		return {"status": "disabled"}

	freq = getattr(settings, "report_frequency", None) or ""
	if not freq:
		return {"status": "no_frequency"}
	if freq not in FREQUENCY_INTERVALS:
		return {"status": "unknown_frequency", "frequency": freq}

	now = now_datetime()
	last = getattr(settings, "last_report_date", None)
	should_run = bool(cint(force)) or not last
	next_due = None
	if last and not should_run:
		interval = FREQUENCY_INTERVALS[freq]
		next_due = add_to_date(get_datetime(last), **interval)
		should_run = now >= get_datetime(next_due)

	if not should_run:
		return {
			"status": "not_due",
			"frequency": freq,
			"last_report": str(last) if last else None,
			"next_run": str(next_due) if next_due else None,
		}

	result = send_individual_reports(force=force)
	mgr = send_manager_reports(force=force)
	hr = send_hr_reports(force=force)
	settings.reload()
	settings.last_report_date = now
	settings.save(ignore_permissions=True)
	frappe.db.commit()
	result["last_report"] = str(now)
	result["manager_reports"] = mgr
	result["hr_reports"] = hr
	return result


@frappe.whitelist()
@survey_admin_required
def send_individual_reports(force=0, employee=None):
	"""Build and email individual reports for the current report period."""
	settings = frappe.get_doc("Value Scoring Settings")
	cycle = None
	if frappe.db.exists("DocType", "Survey Cycle"):
		try:
			cycle = get_or_create_open_cycle()
			refresh_cycle_stats(cycle)
			cycle.reload()
		except Exception:
			cycle = None

	# Report window = report_frequency period ending today
	report_freq = getattr(settings, "report_frequency", None) or "Monthly"
	period_start, period_end = _report_period(report_freq)

	completion_pct = flt(cycle.completion_pct) if cycle else 0
	threshold = cint(getattr(settings, "min_completion_pct_for_final_report", 90)) or 90
	report_type = "Final" if completion_pct >= threshold else "Progress"

	employees = []
	if employee:
		employees = [employee]
	else:
		employees = frappe.get_all(
			"Employee",
			filters={"status": "Active"},
			pluck="name",
		)

	sent = []
	failed = []
	skipped = []

	for emp in employees:
		log = None
		try:
			payload = build_employee_report(emp, period_start, period_end, cycle=cycle)
			if not payload.get("has_data") and not cint(force):
				skipped.append({"employee": emp, "reason": "no_data"})
				continue

			email = payload.get("email")
			if not email:
				skipped.append({"employee": emp, "reason": "no_email"})
				continue

			cc = []
			# Team Leaders / HR receive dedicated multi-person digests
			# (send_manager_reports / send_hr_reports), not a CC of each email.

			subject = (
				f"{'[PROGRESS] ' if report_type == 'Progress' else ''}"
				f"Your 360° Performance Report ({formatdate(period_start)} – {formatdate(period_end)})"
			)

			log = frappe.get_doc({
				"doctype": "Survey Report Log",
				"employee": emp,
				"period_start": period_start,
				"period_end": period_end,
				"report_type": report_type,
				"status": "Pending",
				"sent_at": now_datetime(),
				"email": email,
				"cycle": cycle.name if cycle else None,
				"overall_score": payload.get("overall_pct"),
				"email_content": payload["html"],
			})
			log.insert(ignore_permissions=True)

			from survey_app.email_log import send_survey_email

			mail_result = send_survey_email(
				email_type="Individual Report",
				recipients=[email],
				cc=list(set(cc)),
				subject=subject,
				message=payload["html"],
				cycle=cycle.name if cycle else None,
				employee=emp,
				report_log=log.name,
				recipient_name=payload.get("employee_name"),
				reference_doctype="Survey Report Log",
				reference_name=log.name,
			)
			if mail_result.get("status") in ("queued", "sent"):
				log.db_set("status", "Sent", update_modified=False)
				sent.append({"employee": emp, "email": email, "report_type": report_type})
			else:
				log.db_set(
					{
						"status": "Failed",
						"error_message": (mail_result.get("error") or "Email send failed")[:500],
					},
					update_modified=False,
				)
				failed.append({"employee": emp, "error": mail_result.get("error") or "send failed"})
		except Exception as e:
			frappe.log_error(title="Individual Report Failed", message=frappe.get_traceback())
			try:
				if log:
					log.db_set(
						{"status": "Failed", "error_message": str(e)[:500]},
						update_modified=False,
					)
				else:
					frappe.get_doc({
						"doctype": "Survey Report Log",
						"employee": emp,
						"period_start": period_start,
						"period_end": period_end,
						"report_type": report_type,
						"status": "Failed",
						"cycle": cycle.name if cycle else None,
						"error_message": str(e)[:500],
					}).insert(ignore_permissions=True)
			except Exception:
				pass
			failed.append({"employee": emp, "error": str(e)})

	frappe.db.commit()

	# Incomplete cycle: nudge remaining reviewers
	reminded = 0
	if cycle and report_type == "Progress":
		reminded = _remind_incomplete_cycle_pairs(cycle)

	return {
		"status": "ok",
		"report_type": report_type,
		"completion_pct": completion_pct,
		"period_start": str(period_start),
		"period_end": str(period_end),
		"sent": len(sent),
		"skipped": len(skipped),
		"failed": len(failed),
		"reminders_sent": reminded,
		"details": {"sent": sent, "skipped": skipped, "failed": failed},
	}


def _report_period(report_freq):
	# Align with cycle helper where possible
	if report_freq in CYCLE_INTERVALS:
		return _cycle_period(report_freq)
	# Weekly → last 7 days
	end = getdate(today())
	if report_freq == "Weekly":
		return add_to_date(end, days=-6), end
	return _cycle_period("Monthly")


@frappe.whitelist()
@survey_admin_required
def preview_employee_report(employee=None):
	settings = frappe.get_doc("Value Scoring Settings")
	freq = getattr(settings, "report_frequency", None) or "Monthly"
	start, end = _report_period(freq)
	cycle = _open_cycle_safe()
	if not employee:
		employee = frappe.db.get_value("Employee", {"status": "Active"}, "name")
	if not employee:
		frappe.throw("No employee found for preview")
	payload = build_employee_report(employee, start, end, cycle=cycle)
	payload["report_kind"] = "individual"
	payload["period_label"] = f"{formatdate(start)} – {formatdate(end)}"
	return _preview_payload(payload)


@frappe.whitelist()
@survey_admin_required
def preview_manager_report(manager=None):
	"""Team Leader digest: team members ranked + individual breakdowns."""
	settings = frappe.get_doc("Value Scoring Settings")
	freq = getattr(settings, "report_frequency", None) or "Monthly"
	start, end = _report_period(freq)
	cycle = _open_cycle_safe()
	roles = resolve_org_roles()
	md = _role_employee_id(roles.get("md"))
	if not manager:
		best = None
		best_n = -1
		seen = set()
		for t in roles.get("team_leaders") or []:
			emp = t.get("employee")
			if not emp or emp == md or emp in seen:
				continue
			seen.add(emp)
			n = len(get_manager_team(emp))
			if n > best_n:
				best_n = n
				best = emp
		manager = best
	if not manager:
		frappe.throw("No Team Leader found for preview. Set Team Leaders in Roles & Org first.")
	if md and _role_employee_id(manager) == md:
		frappe.throw("Use Preview MD Digest for the Managing Director leadership report.")
	payload = build_manager_report(manager, start, end, cycle=cycle)
	payload["report_kind"] = "manager"
	payload["period_label"] = f"{formatdate(start)} – {formatdate(end)}"
	payload["people_count"] = len(payload.get("team") or [])
	return _preview_payload(payload)


@frappe.whitelist()
@survey_admin_required
def preview_md_report():
	"""MD digest: managers ranked by individual and team performance."""
	settings = frappe.get_doc("Value Scoring Settings")
	freq = getattr(settings, "report_frequency", None) or "Monthly"
	start, end = _report_period(freq)
	cycle = _open_cycle_safe()
	payload = build_md_report(start, end, cycle=cycle)
	payload["report_kind"] = "md"
	payload["period_label"] = f"{formatdate(start)} – {formatdate(end)}"
	payload["people_count"] = len(payload.get("managers") or [])
	return _preview_payload(payload)


@frappe.whitelist()
@survey_admin_required
def preview_hr_report():
	"""HR digest: all teams ranked + individual breakdowns."""
	settings = frappe.get_doc("Value Scoring Settings")
	freq = getattr(settings, "report_frequency", None) or "Monthly"
	start, end = _report_period(freq)
	cycle = _open_cycle_safe()
	payload = build_hr_report(start, end, cycle=cycle)
	payload["report_kind"] = "hr"
	payload["period_label"] = f"{formatdate(start)} – {formatdate(end)}"
	payload["people_count"] = len(payload.get("team") or [])
	return _preview_payload(payload)


def _preview_payload(payload):
	"""Attach transport-safe HTML fields for desk preview (some clients strip `html`)."""
	import base64

	raw = payload.get("html") or ""
	payload["report_html"] = raw
	payload["html_b64"] = base64.b64encode(raw.encode("utf-8")).decode("ascii") if raw else ""
	# Keep html for email send paths; preview UI prefers report_html / html_b64
	return payload


def _role_employee_id(value):
	"""resolve_org_roles() returns MD as a dict and TL rows with `employee`."""
	if not value:
		return None
	if isinstance(value, dict):
		return value.get("employee") or value.get("name")
	return value


def _open_cycle_safe():
	if not frappe.db.exists("DocType", "Survey Cycle"):
		return None
	try:
		cycle = get_or_create_open_cycle()
		refresh_cycle_stats(cycle)
		cycle.reload()
		return cycle
	except Exception:
		return None


@frappe.whitelist()
@survey_admin_required
def send_manager_reports(force=0, manager=None):
	"""Email team digests to Team Leaders and a leadership digest to the MD."""
	settings = frappe.get_doc("Value Scoring Settings")
	# Managers get a dedicated digest when this flag is on (or a single manager is forced for preview/test).
	if not cint(getattr(settings, "cc_team_leader_on_report", 0)) and not manager:
		return {"status": "skipped", "reason": "Team Leader digest is disabled", "sent": 0}

	cycle = _open_cycle_safe()
	report_freq = getattr(settings, "report_frequency", None) or "Monthly"
	period_start, period_end = _report_period(report_freq)

	roles = resolve_org_roles()
	md = _role_employee_id(roles.get("md"))
	managers = []
	send_md = False
	if manager:
		mgr_id = _role_employee_id(manager)
		if md and mgr_id == md:
			send_md = True
		else:
			managers = [mgr_id]
	else:
		seen = set()
		for t in roles.get("team_leaders") or []:
			emp = t.get("employee")
			if emp and emp not in seen and emp != md:
				seen.add(emp)
				managers.append(emp)
		send_md = bool(md)

	sent, failed, skipped = [], [], []
	for mgr in managers:
		if not mgr:
			continue
		try:
			payload = build_manager_report(mgr, period_start, period_end, cycle=cycle)
			if not payload.get("team") and not cint(force):
				skipped.append({"manager": mgr, "reason": "no_team"})
				continue
			email = payload.get("email")
			if not email:
				skipped.append({"manager": mgr, "reason": "no_email"})
				continue

			subject = (
				f"{payload.get('digest_title') or 'Team Performance Digest'} — {payload.get('manager_name')} "
				f"({formatdate(period_start)} – {formatdate(period_end)})"
			)
			from survey_app.email_log import send_survey_email

			mail_result = send_survey_email(
				email_type="Manager Report",
				recipients=[email],
				subject=subject,
				message=payload["html"],
				cycle=cycle.name if cycle else None,
				employee=mgr,
				recipient_name=payload.get("manager_name"),
				reference_doctype="Employee",
				reference_name=mgr,
			)
			if mail_result.get("status") in ("queued", "sent"):
				sent.append({"manager": mgr, "email": email, "team_size": len(payload.get("team") or []), "kind": "team"})
			else:
				failed.append({"manager": mgr, "error": mail_result.get("error") or "send failed"})
		except Exception as e:
			frappe.log_error(title="Manager Report Failed", message=frappe.get_traceback())
			failed.append({"manager": mgr, "error": str(e)})

	if send_md and md:
		try:
			payload = build_md_report(period_start, period_end, cycle=cycle, md_employee=md)
			email = payload.get("email")
			if not email and not cint(force):
				skipped.append({"manager": md, "reason": "no_email"})
			elif email:
				subject = (
					f"{payload.get('digest_title') or 'Leadership Performance Digest'} — {payload.get('manager_name')} "
					f"({formatdate(period_start)} – {formatdate(period_end)})"
				)
				from survey_app.email_log import send_survey_email

				mail_result = send_survey_email(
					email_type="MD Report",
					recipients=[email],
					subject=subject,
					message=payload["html"],
					cycle=cycle.name if cycle else None,
					employee=md,
					recipient_name=payload.get("manager_name"),
					reference_doctype="Employee",
					reference_name=md,
				)
				if mail_result.get("status") in ("queued", "sent"):
					sent.append({
						"manager": md,
						"email": email,
						"managers": len(payload.get("managers") or []),
						"kind": "md",
					})
				else:
					failed.append({"manager": md, "error": mail_result.get("error") or "send failed"})
		except Exception as e:
			frappe.log_error(title="MD Report Failed", message=frappe.get_traceback())
			failed.append({"manager": md, "error": str(e)})

	frappe.db.commit()
	return {
		"status": "ok",
		"period_start": str(period_start),
		"period_end": str(period_end),
		"sent": len(sent),
		"skipped": len(skipped),
		"failed": len(failed),
		"details": {"sent": sent, "skipped": skipped, "failed": failed},
	}


@frappe.whitelist()
@survey_admin_required
def send_hr_reports(force=0):
	"""Email organisation-wide digest to HR Managers."""
	settings = frappe.get_doc("Value Scoring Settings")
	if not cint(getattr(settings, "cc_hr_on_report", 0)) and not cint(force):
		return {"status": "skipped", "reason": "HR digest is disabled", "sent": 0}

	cycle = _open_cycle_safe()
	report_freq = getattr(settings, "report_frequency", None) or "Monthly"
	period_start, period_end = _report_period(report_freq)
	payload = build_hr_report(period_start, period_end, cycle=cycle)

	hr_users = frappe.get_all(
		"Has Role",
		filters={"role": "HR Manager", "parenttype": "User"},
		pluck="parent",
	)
	recipients = []
	for u in hr_users:
		em = frappe.db.get_value("User", u, "email")
		if em:
			recipients.append(em)
	recipients = sorted(set(recipients))
	if not recipients:
		return {"status": "skipped", "reason": "no_hr_emails", "sent": 0}

	subject = (
		f"Organisation Performance Digest "
		f"({formatdate(period_start)} – {formatdate(period_end)})"
	)
	from survey_app.email_log import send_survey_email

	mail_result = send_survey_email(
		email_type="HR Report",
		recipients=recipients,
		subject=subject,
		message=payload["html"],
		cycle=cycle.name if cycle else None,
		recipient_name="HR Managers",
	)
	frappe.db.commit()
	return {
		"status": mail_result.get("status"),
		"sent": 1 if mail_result.get("status") in ("queued", "sent") else 0,
		"recipients": recipients,
		"people": len(payload.get("team") or []),
		"teams": len(payload.get("teams") or []),
	}


def get_manager_team(manager_employee):
	"""
	Employees covered by a Team Leader's digest:
	union of their TL departments + direct reports (manager excluded).
	"""
	manager_employee = _role_employee_id(manager_employee)
	if not manager_employee:
		return []

	roles = resolve_org_roles()
	seen = {}

	def _add(rows):
		for e in rows:
			if e.name != manager_employee:
				seen[e.name] = e

	depts = [
		t["department"]
		for t in (roles.get("team_leaders") or [])
		if t.get("employee") == manager_employee and t.get("department")
	]
	if depts:
		_add(
			frappe.get_all(
				"Employee",
				filters={"status": "Active", "department": ["in", depts]},
				fields=["name", "employee_name", "department", "user_id"],
				order_by="employee_name asc",
			)
		)

	_add(
		frappe.get_all(
			"Employee",
			filters={"status": "Active", "reports_to": manager_employee},
			fields=["name", "employee_name", "department", "user_id"],
			order_by="employee_name asc",
		)
	)

	# Fallback: if still empty, use manager's own department peers
	if not seen:
		dept = frappe.db.get_value("Employee", manager_employee, "department")
		if dept:
			_add(
				frappe.get_all(
					"Employee",
					filters={"status": "Active", "department": dept},
					fields=["name", "employee_name", "department", "user_id"],
					order_by="employee_name asc",
				)
			)

	return sorted(seen.values(), key=lambda e: (e.employee_name or e.name))


def _build_people_rows(employees, period_start, period_end, cycle=None):
	org = _org_benchmarks(period_start, period_end)
	team_rows = []
	scores_for_avg = []
	for te in employees:
		payload = build_employee_report(te.name, period_start, period_end, cycle=cycle)
		cats = payload.get("categories") or []
		strongest = max(cats, key=lambda c: flt(c.get("score_pct"))) if cats else None
		weakest = min(cats, key=lambda c: flt(c.get("score_pct"))) if cats else None
		row = {
			"employee": te.name,
			"employee_name": te.employee_name,
			"department": te.department,
			"overall_pct": payload.get("overall_pct") or 0,
			"overall_percentile": payload.get("overall_percentile"),
			"reviewer_count": payload.get("reviewer_count") or 0,
			"has_data": payload.get("has_data"),
			"strongest": strongest["category"] if strongest else None,
			"strongest_pct": strongest["score_pct"] if strongest else None,
			"development": weakest["category"] if weakest else None,
			"development_pct": weakest["score_pct"] if weakest else None,
		}
		team_rows.append(row)
		if payload.get("has_data"):
			scores_for_avg.append(flt(payload.get("overall_pct")))

	team_rows.sort(key=lambda r: flt(r.get("overall_pct")), reverse=True)
	team_avg = round(sum(scores_for_avg) / len(scores_for_avg), 1) if scores_for_avg else None
	return team_rows, team_avg, org


def _build_department_team_summaries(period_start, period_end, cycle=None):
	"""One summary per Team Leader × department assignment (for HR team ranking)."""
	roles = resolve_org_roles()
	org = _org_benchmarks(period_start, period_end)
	teams = []
	for t in roles.get("team_leaders") or []:
		dept = t.get("department")
		mgr = t.get("employee")
		if not dept or not mgr:
			continue
		members = frappe.get_all(
			"Employee",
			filters={"status": "Active", "department": dept},
			fields=["name", "employee_name", "department", "user_id"],
			order_by="employee_name asc",
		)
		# Team performance excludes the manager themselves
		member_emps = [m for m in members if m.name != mgr]
		member_rows, team_avg, _ = _build_people_rows(member_emps, period_start, period_end, cycle=cycle)
		teams.append({
			"department": dept,
			"manager": mgr,
			"manager_name": t.get("employee_name") or mgr,
			"team_size": len(member_emps),
			"team_avg": team_avg,
			"scored_count": len([r for r in member_rows if r.get("has_data")]),
			"members": member_rows,
		})
	teams.sort(key=lambda r: flt(r.get("team_avg") if r.get("team_avg") is not None else -1), reverse=True)
	return teams, org


def _build_leadership_summaries(period_start, period_end, cycle=None):
	"""Unique Team Leaders with individual score + aggregated team performance (for MD)."""
	roles = resolve_org_roles()
	md = _role_employee_id(roles.get("md"))
	org = _org_benchmarks(period_start, period_end)
	by_mgr = {}
	for t in roles.get("team_leaders") or []:
		emp = t.get("employee")
		if not emp or emp == md:
			continue
		meta = by_mgr.setdefault(
			emp,
			{
				"manager": emp,
				"manager_name": t.get("employee_name"),
				"departments": [],
			},
		)
		if t.get("department") and t["department"] not in meta["departments"]:
			meta["departments"].append(t["department"])
		if t.get("employee_name"):
			meta["manager_name"] = t["employee_name"]

	rows = []
	for emp, meta in by_mgr.items():
		members = get_manager_team(emp)
		_member_rows, team_avg, _ = _build_people_rows(members, period_start, period_end, cycle=cycle)
		indiv = build_employee_report(emp, period_start, period_end, cycle=cycle)
		rows.append({
			"manager": emp,
			"manager_name": meta.get("manager_name") or indiv.get("employee_name") or emp,
			"departments": ", ".join(meta["departments"]) if meta["departments"] else (indiv.get("department") or "—"),
			"department": meta["departments"][0] if meta["departments"] else indiv.get("department"),
			"individual_pct": indiv.get("overall_pct") or 0,
			"individual_percentile": indiv.get("overall_percentile"),
			"has_individual_data": indiv.get("has_data"),
			"team_avg": team_avg,
			"team_size": len(members),
			"team_scored": len([r for r in _member_rows if r.get("has_data")]),
			"reviewer_count": indiv.get("reviewer_count") or 0,
		})
	return rows, org


def build_manager_report(manager, period_start, period_end, cycle=None):
	"""Team Leader digest — team members ranked + individual breakdowns."""
	manager = _role_employee_id(manager)
	mgr = frappe.get_value(
		"Employee",
		manager,
		["name", "employee_name", "department", "user_id", "designation"],
		as_dict=True,
	)
	if not mgr:
		frappe.throw(f"Manager {manager} not found")

	email = frappe.db.get_value("User", mgr.user_id, "email") if mgr.user_id else None
	team_emps = get_manager_team(manager)
	team_rows, team_avg, org = _build_people_rows(team_emps, period_start, period_end, cycle=cycle)

	digest_title = "Team Performance Digest"
	html = _render_manager_html(
		mgr=mgr,
		period_start=period_start,
		period_end=period_end,
		team_rows=team_rows,
		team_avg=team_avg,
		org_overall_avg=org.get("overall_avg"),
		org_headcount=org.get("employee_count") or 0,
		cycle=cycle,
		digest_title=digest_title,
		audience_label="Manager Copy · Confidential",
		scope_label="team",
	)

	return {
		"manager": mgr.name,
		"manager_name": mgr.employee_name,
		"department": mgr.department,
		"email": email,
		"team": team_rows,
		"team_avg": team_avg,
		"digest_title": digest_title,
		"html": html,
		"period_start": str(period_start),
		"period_end": str(period_end),
		"has_data": bool(team_avg is not None),
		"people_count": len(team_rows),
	}


def build_md_report(period_start, period_end, cycle=None, md_employee=None):
	"""MD digest — managers ranked by individual score and by team performance."""
	roles = resolve_org_roles()
	md_id = _role_employee_id(md_employee) or _role_employee_id(roles.get("md"))
	if not md_id:
		frappe.throw("No Managing Director configured. Set MD in Roles & Org first.")

	mgr = frappe.get_value(
		"Employee",
		md_id,
		["name", "employee_name", "department", "user_id", "designation"],
		as_dict=True,
	)
	if not mgr:
		frappe.throw(f"Managing Director {md_id} not found")

	email = frappe.db.get_value("User", mgr.user_id, "email") if mgr.user_id else None
	managers, org = _build_leadership_summaries(period_start, period_end, cycle=cycle)
	digest_title = "Leadership Performance Digest"
	html = _render_md_html(
		mgr=mgr,
		period_start=period_start,
		period_end=period_end,
		managers=managers,
		org_overall_avg=org.get("overall_avg"),
		org_headcount=org.get("employee_count") or 0,
		cycle=cycle,
		digest_title=digest_title,
	)
	return {
		"manager": mgr.name,
		"manager_name": mgr.employee_name,
		"department": mgr.department,
		"email": email,
		"managers": managers,
		"team": managers,  # preview meta reuse
		"digest_title": digest_title,
		"html": html,
		"period_start": str(period_start),
		"period_end": str(period_end),
		"has_data": any(r.get("has_individual_data") or r.get("team_avg") is not None for r in managers),
		"people_count": len(managers),
		"managers_count": len(managers),
	}


def build_hr_report(period_start, period_end, cycle=None):
	"""HR digest — all teams ranked + full individual breakdowns."""
	teams, org = _build_department_team_summaries(period_start, period_end, cycle=cycle)
	people = frappe.get_all(
		"Employee",
		filters={"status": "Active"},
		fields=["name", "employee_name", "department", "user_id"],
		order_by="department asc, employee_name asc",
	)
	team_rows, people_avg, _ = _build_people_rows(people, period_start, period_end, cycle=cycle)

	viewer = frappe._dict(
		name="HR",
		employee_name="Human Resources",
		department="Organisation",
	)
	digest_title = "Organisation Performance Digest"
	html = _render_hr_html(
		viewer=viewer,
		period_start=period_start,
		period_end=period_end,
		teams=teams,
		people_rows=team_rows,
		people_avg=people_avg,
		org_overall_avg=org.get("overall_avg"),
		org_headcount=org.get("employee_count") or 0,
		cycle=cycle,
		digest_title=digest_title,
	)
	return {
		"manager": None,
		"manager_name": "Human Resources",
		"department": "Organisation",
		"email": None,
		"teams": teams,
		"team": team_rows,
		"team_avg": people_avg,
		"digest_title": digest_title,
		"html": html,
		"period_start": str(period_start),
		"period_end": str(period_end),
		"has_data": bool(people_avg is not None or any(t.get("team_avg") is not None for t in teams)),
		"people_count": len(team_rows),
		"teams_count": len(teams),
	}


def build_employee_report(employee, period_start, period_end, cycle=None):
	emp = frappe.get_value(
		"Employee",
		employee,
		["name", "employee_name", "department", "user_id"],
		as_dict=True,
	)
	if not emp:
		frappe.throw(f"Employee {employee} not found")

	email = frappe.db.get_value("User", emp.user_id, "email") if emp.user_id else None
	scorecard = build_employee_scorecard(
		employee,
		period_start,
		period_end,
		cycle=cycle,
	)
	overall = scorecard["overall_pct"]
	delta = scorecard["delta"]
	reviewer_count = scorecard["reviewer_count"]
	expected = scorecard["expected_reviews"]
	overall_percentile = scorecard["overall_percentile"]
	categories = scorecard["categories"]

	html = _render_html(
		emp=emp,
		period_start=period_start,
		period_end=period_end,
		overall=overall,
		overall_percentile=overall_percentile,
		org_overall_avg=scorecard["org_overall_avg"],
		org_headcount=scorecard["org_headcount"],
		delta=delta,
		categories=categories,
		prev_categories=scorecard["previous_categories"],
		expected=expected,
		reviewer_count=reviewer_count,
		cycle=cycle,
	)

	return {
		"employee": emp.name,
		"employee_name": emp.employee_name,
		"department": emp.department,
		"email": email,
		"overall_pct": overall,
		"overall_percentile": overall_percentile,
		"delta": delta,
		"categories": categories,
		"reviewer_count": reviewer_count,
		"has_data": scorecard["has_data"],
		"html": html,
		"period_start": str(period_start),
		"period_end": str(period_end),
	}


def _previous_period(start, end):
	start = getdate(start)
	end = getdate(end)
	span = (end - start).days + 1
	prev_end = add_to_date(start, days=-1)
	prev_start = add_to_date(prev_end, days=-(span - 1))
	return getdate(prev_start), getdate(prev_end)


def _percentile_label(pct):
	if pct is None:
		return "Insufficient data"
	pct_i = int(pct)
	if 10 <= pct_i % 100 <= 20:
		suffix = "th"
	else:
		suffix = {1: "st", 2: "nd", 3: "rd"}.get(pct_i % 10, "th")
	return f"{pct_i}{suffix}"


def _esc(text):
	return (
		frappe.utils.cstr(text or "")
		.replace("&", "&amp;")
		.replace("<", "&lt;")
		.replace(">", "&gt;")
		.replace('"', "&quot;")
)


REPORT_MOTTO = "Impacting lives positively"
REPORT_SIGNOFF = "Human Resources"
_LOGO_DATA_URI = None


def _logo_data_uri():
	global _LOGO_DATA_URI
	if _LOGO_DATA_URI is not None:
		return _LOGO_DATA_URI
	path = os.path.join(
		frappe.get_app_path("survey_app"),
		"public",
		"images",
		"actserv-logo.png",
	)
	if os.path.exists(path):
		with open(path, "rb") as f:
			b64 = base64.b64encode(f.read()).decode("ascii")
		_LOGO_DATA_URI = f"data:image/png;base64,{b64}"
	else:
		_LOGO_DATA_URI = ""
	return _LOGO_DATA_URI


def _report_accent_bar():
	return (
		'<tr><td style="background:linear-gradient(90deg,#F58220 0%,#F58220 45%,#86BC25 45%,#86BC25 100%);'
		'height:4px;font-size:0;line-height:0;">&nbsp;</td></tr>'
	)


def _report_masthead_branding(report_title, right_label="Confidential"):
	logo = _logo_data_uri()
	logo_html = ""
	if logo:
		logo_html = (
			f'<img src="{logo}" alt="actserv" width="140" height="auto" '
			f'style="display:block;max-width:140px;height:auto;border:0;" />'
		)
	return f"""
			<table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%">
				<tr>
					<td valign="top">{logo_html}</td>
					<td align="right" valign="top" style="font-family:Arial,Helvetica,sans-serif;font-size:10px;letter-spacing:1px;text-transform:uppercase;color:#B7B7B7;">
						{_esc(right_label)}
					</td>
				</tr>
			</table>
			<div style="font-family:Arial,Helvetica,sans-serif;font-size:11px;color:#86BC25;margin-top:8px;letter-spacing:0.3px;">
				{_esc(REPORT_MOTTO)}
			</div>
			<div style="font-family:Arial,Helvetica,sans-serif;font-size:10px;letter-spacing:2px;text-transform:uppercase;color:#F58220;font-weight:700;margin-top:14px;">
				{_esc(report_title)}
			</div>
	"""


def _report_signoff_html(extra_paragraph=None):
	para = ""
	if extra_paragraph:
		para = (
			f'<p style="font-family:Arial,Helvetica,sans-serif;font-size:13px;line-height:1.6;'
			f'color:#333333;margin:0 0 16px 0;">{extra_paragraph}</p>'
		)
	return f"""
		<tr>
			<td style="padding:28px 36px 32px 36px;">
				{para}
				<p style="font-family:Arial,Helvetica,sans-serif;font-size:13px;color:#333333;margin:0;">
					Kind regards,<br>
					<strong>{_esc(REPORT_SIGNOFF)}</strong>
				</p>
			</td>
		</tr>
	"""


def _html_bar_row(label, value, max_value=100, fill="#86BC25", track="#E8E8E8", display=None):
	"""Single email-safe horizontal bar using nested tables (Outlook/Gmail compatible)."""
	val = max(0.0, min(flt(value), flt(max_value) or 100))
	pct_w = int(round((val / (max_value or 100)) * 100)) if max_value else 0
	pct_w = max(pct_w, 2) if val > 0 else 0
	empty_w = 100 - pct_w
	safe = _esc(label)
	shown = display if display is not None else (f"{flt(value):.0f}%" if value is not None else "—")
	return f"""
	<tr>
		<td style="padding:10px 12px 10px 0;width:160px;vertical-align:middle;font-family:Arial,Helvetica,sans-serif;font-size:13px;color:#1A1A1A;line-height:1.3;">
			{safe}
		</td>
		<td style="padding:10px 0;vertical-align:middle;">
			<table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%" style="border-collapse:collapse;">
				<tr>
					<td width="{pct_w}%" style="background-color:{fill};height:14px;font-size:0;line-height:0;">&nbsp;</td>
					<td width="{empty_w}%" style="background-color:{track};height:14px;font-size:0;line-height:0;">&nbsp;</td>
				</tr>
			</table>
		</td>
		<td style="padding:10px 0 10px 12px;width:72px;text-align:right;vertical-align:middle;font-family:Arial,Helvetica,sans-serif;font-size:13px;font-weight:700;color:#1A1A1A;white-space:nowrap;">
			{shown}
		</td>
	</tr>
	"""


def _html_compare_bar_row(label, yours, org_avg):
	"""You vs organisation average — dual bars (consulting scorecard style)."""
	safe = _esc(label)
	y = flt(yours)
	o = flt(org_avg) if org_avg is not None else None
	y_w = max(int(round(y)), 2) if y else 0
	o_w = max(int(round(o)), 2) if o else 0
	org_row = ""
	if o is not None:
		org_row = f"""
		<tr>
			<td style="padding:0 0 2px 0;font-family:Arial,Helvetica,sans-serif;font-size:10px;color:#767676;letter-spacing:0.3px;">ORGANISATION AVG</td>
			<td style="padding:0 0 2px 8px;">
				<table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%" style="border-collapse:collapse;">
					<tr>
						<td width="{o_w}%" style="background-color:#B7B7B7;height:8px;font-size:0;line-height:0;">&nbsp;</td>
						<td width="{100 - o_w}%" style="background-color:#F0F0F0;height:8px;font-size:0;line-height:0;">&nbsp;</td>
					</tr>
				</table>
			</td>
			<td style="padding:0 0 2px 10px;width:48px;text-align:right;font-family:Arial,Helvetica,sans-serif;font-size:11px;color:#767676;">{o:.0f}%</td>
		</tr>
		"""
	return f"""
	<tr>
		<td colspan="3" style="padding:14px 0 4px 0;border-top:1px solid #EEEEEE;">
			<table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%" style="border-collapse:collapse;">
				<tr>
					<td style="font-family:Arial,Helvetica,sans-serif;font-size:13px;font-weight:700;color:#1A1A1A;padding-bottom:8px;">{safe}</td>
				</tr>
				<tr>
					<td>
						<table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%" style="border-collapse:collapse;">
							<tr>
								<td style="padding:0 0 4px 0;width:120px;font-family:Arial,Helvetica,sans-serif;font-size:10px;color:#86BC25;letter-spacing:0.3px;font-weight:700;">YOUR SCORE</td>
								<td style="padding:0 0 4px 8px;">
									<table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%" style="border-collapse:collapse;">
										<tr>
											<td width="{y_w}%" style="background-color:#86BC25;height:12px;font-size:0;line-height:0;">&nbsp;</td>
											<td width="{100 - y_w}%" style="background-color:#F0F0F0;height:12px;font-size:0;line-height:0;">&nbsp;</td>
										</tr>
									</table>
								</td>
								<td style="padding:0 0 4px 10px;width:48px;text-align:right;font-family:Arial,Helvetica,sans-serif;font-size:13px;font-weight:700;color:#1A1A1A;">{y:.0f}%</td>
							</tr>
							{org_row}
						</table>
					</td>
				</tr>
			</table>
		</td>
	</tr>
	"""


def _trait_score_chart(categories):
	if not categories:
		return (
			'<p style="font-family:Arial,Helvetica,sans-serif;font-size:13px;color:#767676;margin:0;">'
			"No competency scores available for this period.</p>"
		)
	rows = "".join(
		_html_compare_bar_row(c["category"], c["score_pct"], c.get("org_avg")) for c in categories
	)
	return f"""
	<table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%" style="border-collapse:collapse;">
		{rows}
	</table>
	"""


def _percentile_chart(categories):
	items = [c for c in categories if c.get("percentile") is not None]
	if not items:
		return (
			'<p style="font-family:Arial,Helvetica,sans-serif;font-size:13px;color:#767676;margin:0;">'
			"Organisation percentiles will appear once a broader set of colleagues has been scored.</p>"
		)
	rows = "".join(
		_html_bar_row(
			c["category"],
			c["percentile"],
			max_value=100,
			fill="#000000",
			track="#E8E8E8",
			display=_percentile_label(c["percentile"]),
		)
		for c in items
	)
	return f"""
	<table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%" style="border-collapse:collapse;">
		{rows}
	</table>
	"""


def _kpi_cell(label, value, sub=None, border_right=True):
	border = "border-right:1px solid #E0E0E0;" if border_right else ""
	sub_html = (
		f'<div style="font-family:Arial,Helvetica,sans-serif;font-size:11px;color:#767676;margin-top:4px;">{_esc(sub)}</div>'
		if sub
		else ""
	)
	return f"""
	<td width="33%" style="padding:18px 16px;{border}vertical-align:top;">
		<div style="font-family:Arial,Helvetica,sans-serif;font-size:10px;letter-spacing:1.2px;text-transform:uppercase;color:#767676;font-weight:700;margin-bottom:8px;">{_esc(label)}</div>
		<div style="font-family:Georgia,'Times New Roman',serif;font-size:28px;line-height:1;color:#000000;font-weight:400;">{value}</div>
		{sub_html}
	</td>
	"""


def _render_html(
	emp,
	period_start,
	period_end,
	overall,
	overall_percentile,
	org_overall_avg,
	org_headcount,
	delta,
	categories,
	prev_categories,
	expected,
	reviewer_count,
	cycle,
):
	prev_map = {c["category"]: c["score_pct"] for c in (prev_categories or [])}
	detail_rows = ""
	for i, c in enumerate(categories):
		prev = prev_map.get(c["category"])
		if prev is not None:
			d = round(c["score_pct"] - prev, 1)
			if d > 0:
				trend = f'<span style="color:#0D7A3F;">+{d:.1f} pts</span>'
			elif d < 0:
				trend = f'<span style="color:#A61B1B;">{d:.1f} pts</span>'
			else:
				trend = '<span style="color:#767676;">Unchanged</span>'
		else:
			trend = '<span style="color:#B7B7B7;">—</span>'
		pct_txt = _percentile_label(c.get("percentile")) if c.get("percentile") is not None else "—"
		org_avg = f'{c["org_avg"]:.0f}%' if c.get("org_avg") is not None else "—"
		bg = "#FAFAFA" if i % 2 else "#FFFFFF"
		detail_rows += f"""
		<tr style="background:{bg};">
			<td style="padding:12px 14px;font-family:Arial,Helvetica,sans-serif;font-size:13px;color:#1A1A1A;border-bottom:1px solid #EEEEEE;">{_esc(c['category'])}</td>
			<td style="padding:12px 14px;font-family:Arial,Helvetica,sans-serif;font-size:13px;color:#1A1A1A;text-align:right;border-bottom:1px solid #EEEEEE;font-weight:700;">{c['score_pct']:.0f}%</td>
			<td style="padding:12px 14px;font-family:Arial,Helvetica,sans-serif;font-size:13px;color:#1A1A1A;text-align:right;border-bottom:1px solid #EEEEEE;">{pct_txt}</td>
			<td style="padding:12px 14px;font-family:Arial,Helvetica,sans-serif;font-size:13px;color:#767676;text-align:right;border-bottom:1px solid #EEEEEE;">{org_avg}</td>
			<td style="padding:12px 14px;font-family:Arial,Helvetica,sans-serif;font-size:12px;text-align:right;border-bottom:1px solid #EEEEEE;">{trend}</td>
		</tr>
		"""

	if not detail_rows:
		detail_rows = """
		<tr>
			<td colspan="5" style="padding:20px 14px;font-family:Arial,Helvetica,sans-serif;font-size:13px;color:#767676;">
				No scored feedback is available for this reporting period.
			</td>
		</tr>
		"""

	colleagues = reviewer_count or 0
	if colleagues == 1:
		review_intro = (
			"You have been reviewed by <strong>1 colleague</strong> during this reporting period. "
			"The results below summarise how your performance was assessed across core competencies."
		)
	elif colleagues > 1:
		review_intro = (
			f"You have been reviewed by <strong>{colleagues} colleagues</strong> during this reporting period. "
			"The results below summarise how your performance was assessed across core competencies."
		)
	else:
		review_intro = (
			"No colleague reviews have been submitted for you in this reporting period. "
			"Scores will appear once feedback has been received."
		)
	if expected and colleagues and colleagues < expected:
		review_intro += f" To date, {colleagues} of {expected} expected reviews have been completed."

	delta_sub = None
	if delta is not None:
		sign = "+" if delta > 0 else ""
		delta_sub = f"{sign}{delta:.1f} pts vs prior period"

	pct_value = _percentile_label(overall_percentile) if overall_percentile is not None else "—"
	pct_sub = (
		f"of {org_headcount} employees scored"
		if overall_percentile is not None and org_headcount
		else "Awaiting peer data"
	)
	org_avg_note = (
		f"Organisation average: {org_overall_avg:.0f}%"
		if org_overall_avg is not None
		else None
	)

	score_chart = _trait_score_chart(categories)
	pct_chart = _percentile_chart(categories)

	dept = _esc(emp.department) if emp.department else "—"
	cycle_line = ""
	if cycle:
		cycle_line = (
			f'<div style="font-family:Arial,Helvetica,sans-serif;font-size:11px;color:#767676;margin-top:6px;">'
			f"Assessment cycle {_esc(cycle.name)} · Organisation completion {flt(cycle.completion_pct):.0f}%"
			f"</div>"
		)

	strongest = None
	development = None
	if categories:
		ordered = sorted(categories, key=lambda x: flt(x.get("score_pct")), reverse=True)
		strongest = ordered[0]
		development = ordered[-1] if len(ordered) > 1 else None

	insight_bits = []
	if strongest:
		insight_bits.append(
			f"Your strongest competency in this period is <strong>{_esc(strongest['category'])}</strong> "
			f"({strongest['score_pct']:.0f}%)."
		)
	if development and strongest and development["category"] != strongest["category"]:
		insight_bits.append(
			f"The primary development focus is <strong>{_esc(development['category'])}</strong> "
			f"({development['score_pct']:.0f}%)."
		)
	if overall_percentile is not None and org_headcount:
		insight_bits.append(
			f"Overall, you rank in the <strong>{_percentile_label(overall_percentile)} percentile</strong> "
			f"relative to {org_headcount} employees assessed in the same period"
			+ (f" (organisation average {org_overall_avg:.0f}%)." if org_overall_avg is not None else ".")
		)
	insights = " ".join(insight_bits) if insight_bits else ""

	return f"""
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Individual Performance Report</title>
</head>
<body style="margin:0;padding:0;background-color:#F5F5F5;">
<table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%" style="background-color:#F5F5F5;padding:24px 12px;">
<tr><td align="center">
<table role="presentation" cellpadding="0" cellspacing="0" border="0" width="640" style="max-width:640px;width:100%;background-color:#FFFFFF;border-collapse:collapse;">

	<!-- Accent bar -->
	{_report_accent_bar()}

	<!-- Masthead -->
	<tr>
		<td style="background-color:#000000;padding:28px 36px 24px 36px;">
			{_report_masthead_branding("Individual Performance Report")}
			<div style="font-family:Georgia,'Times New Roman',serif;font-size:26px;line-height:1.25;color:#FFFFFF;margin-top:16px;font-weight:400;">
				{_esc(emp.employee_name)}
			</div>
			<div style="font-family:Arial,Helvetica,sans-serif;font-size:13px;color:#B7B7B7;margin-top:10px;line-height:1.5;">
				{formatdate(period_start)} – {formatdate(period_end)}&nbsp;&nbsp;|&nbsp;&nbsp;{dept}
			</div>
			{cycle_line}
		</td>
	</tr>

	<!-- Executive summary -->
	<tr>
		<td style="padding:28px 36px 8px 36px;">
			<div style="font-family:Arial,Helvetica,sans-serif;font-size:10px;letter-spacing:1.5px;text-transform:uppercase;color:#767676;font-weight:700;margin-bottom:12px;">
				Executive Summary
			</div>
			<p style="font-family:Arial,Helvetica,sans-serif;font-size:14px;line-height:1.65;color:#333333;margin:0 0 12px 0;">
				{review_intro}
			</p>
			{"<p style='font-family:Arial,Helvetica,sans-serif;font-size:14px;line-height:1.65;color:#333333;margin:0;'>" + insights + "</p>" if insights else ""}
		</td>
	</tr>

	<!-- KPI strip -->
	<tr>
		<td style="padding:20px 36px 8px 36px;">
			<table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%" style="border:1px solid #E0E0E0;border-collapse:collapse;background-color:#FFFFFF;">
				<tr>
					{_kpi_cell("Overall Score", f"{overall:.0f}%", delta_sub or org_avg_note, True)}
					{_kpi_cell("Organisation Percentile", pct_value, pct_sub, True)}
					{_kpi_cell("Colleague Reviews", str(colleagues), f"of {expected} expected" if expected else "Completed reviews", False)}
				</tr>
			</table>
		</td>
	</tr>

	<!-- Competency performance -->
	<tr>
		<td style="padding:28px 36px 8px 36px;">
			<div style="font-family:Arial,Helvetica,sans-serif;font-size:10px;letter-spacing:1.5px;text-transform:uppercase;color:#767676;font-weight:700;margin-bottom:4px;">
				Section 01
			</div>
			<div style="font-family:Georgia,'Times New Roman',serif;font-size:20px;color:#000000;margin-bottom:6px;">
				Performance by Competency
			</div>
			<p style="font-family:Arial,Helvetica,sans-serif;font-size:12px;line-height:1.5;color:#767676;margin:0 0 8px 0;">
				Your score compared with the organisation average for each competency.
			</p>
			{score_chart}
		</td>
	</tr>

	<!-- Relative standing -->
	<tr>
		<td style="padding:28px 36px 8px 36px;">
			<div style="border-top:1px solid #EEEEEE;padding-top:28px;">
				<div style="font-family:Arial,Helvetica,sans-serif;font-size:10px;letter-spacing:1.5px;text-transform:uppercase;color:#767676;font-weight:700;margin-bottom:4px;">
					Section 02
				</div>
				<div style="font-family:Georgia,'Times New Roman',serif;font-size:20px;color:#000000;margin-bottom:6px;">
					Relative Standing
				</div>
				<p style="font-family:Arial,Helvetica,sans-serif;font-size:12px;line-height:1.5;color:#767676;margin:0 0 12px 0;">
					Percentile rank within the organisation for each competency. A higher percentile indicates a stronger relative position.
				</p>
				{pct_chart}
			</div>
		</td>
	</tr>

	<!-- Detail table -->
	<tr>
		<td style="padding:28px 36px 8px 36px;">
			<div style="border-top:1px solid #EEEEEE;padding-top:28px;">
				<div style="font-family:Arial,Helvetica,sans-serif;font-size:10px;letter-spacing:1.5px;text-transform:uppercase;color:#767676;font-weight:700;margin-bottom:4px;">
					Section 03
				</div>
				<div style="font-family:Georgia,'Times New Roman',serif;font-size:20px;color:#000000;margin-bottom:14px;">
					Detailed Results
				</div>
				<table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%" style="border-collapse:collapse;border:1px solid #E0E0E0;">
					<thead>
						<tr style="background-color:#000000;">
							<th align="left" style="padding:11px 14px;font-family:Arial,Helvetica,sans-serif;font-size:10px;letter-spacing:1px;text-transform:uppercase;color:#FFFFFF;font-weight:700;">Competency</th>
							<th align="right" style="padding:11px 14px;font-family:Arial,Helvetica,sans-serif;font-size:10px;letter-spacing:1px;text-transform:uppercase;color:#FFFFFF;font-weight:700;">Score</th>
							<th align="right" style="padding:11px 14px;font-family:Arial,Helvetica,sans-serif;font-size:10px;letter-spacing:1px;text-transform:uppercase;color:#FFFFFF;font-weight:700;">Percentile</th>
							<th align="right" style="padding:11px 14px;font-family:Arial,Helvetica,sans-serif;font-size:10px;letter-spacing:1px;text-transform:uppercase;color:#FFFFFF;font-weight:700;">Org Avg</th>
							<th align="right" style="padding:11px 14px;font-family:Arial,Helvetica,sans-serif;font-size:10px;letter-spacing:1px;text-transform:uppercase;color:#FFFFFF;font-weight:700;">Trend</th>
						</tr>
					</thead>
					<tbody>
						{detail_rows}
					</tbody>
				</table>
			</div>
		</td>
	</tr>

	<!-- Closing -->
	{_report_signoff_html(
		"Please discuss these results with your Team Leader or HR to agree development priorities for the next period."
	)}

	<!-- Footer -->
	<tr>
		<td style="background-color:#F5F5F5;border-top:1px solid #E0E0E0;padding:16px 36px;">
			<p style="font-family:Arial,Helvetica,sans-serif;font-size:10px;line-height:1.5;color:#9A9A9A;margin:0;">
				This document is confidential and intended solely for the named recipient. Scores are derived from colleague feedback submitted during the stated reporting period and should be interpreted alongside manager judgement and other performance evidence.
			</p>
		</td>
	</tr>

</table>
</td></tr>
</table>
</body>
</html>
	"""


def _rank_bar_row(label, pct, right_label="—", sub_label=None):
	"""Email-safe horizontal bar row for digests."""
	has = pct is not None
	pct_val = flt(pct) if has else 0
	pct_w = max(int(round(pct_val)), 2) if has and pct_val > 0 else 0
	empty_w = 100 - pct_w
	score_txt = f"{pct_val:.0f}%" if has else "—"
	sub = (
		f'<div style="font-family:Arial,Helvetica,sans-serif;font-size:11px;color:#9A9A9A;margin-top:2px;">{_esc(sub_label)}</div>'
		if sub_label
		else ""
	)
	return f"""
	<tr>
		<td style="padding:10px 12px 10px 0;width:180px;vertical-align:middle;font-family:Arial,Helvetica,sans-serif;font-size:13px;color:#1A1A1A;">
			{_esc(label)}{sub}
		</td>
		<td style="padding:10px 0;vertical-align:middle;">
			<table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%" style="border-collapse:collapse;">
				<tr>
					<td width="{pct_w}%" style="background-color:#86BC25;height:12px;font-size:0;line-height:0;">&nbsp;</td>
					<td width="{empty_w}%" style="background-color:#F0F0F0;height:12px;font-size:0;line-height:0;">&nbsp;</td>
				</tr>
			</table>
		</td>
		<td style="padding:10px 0 10px 12px;width:48px;text-align:right;font-family:Arial,Helvetica,sans-serif;font-size:13px;font-weight:700;color:#1A1A1A;">
			{score_txt}
		</td>
		<td style="padding:10px 0 10px 8px;width:72px;text-align:right;font-family:Arial,Helvetica,sans-serif;font-size:11px;color:#767676;">
			{_esc(right_label)}
		</td>
	</tr>
	"""


def _digest_shell(title, audience, recipient_name, subtitle, cycle_line, body_sections, footer_note):
	return f"""
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{_esc(title)}</title>
</head>
<body style="margin:0;padding:0;background-color:#F5F5F5;">
<table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%" style="background-color:#F5F5F5;padding:24px 12px;">
<tr><td align="center">
<table role="presentation" cellpadding="0" cellspacing="0" border="0" width="680" style="max-width:680px;width:100%;background-color:#FFFFFF;border-collapse:collapse;">

	{_report_accent_bar()}

	<tr>
		<td style="background-color:#000000;padding:28px 36px 24px 36px;">
			{_report_masthead_branding(title, right_label=audience)}
			<div style="font-family:Georgia,'Times New Roman',serif;font-size:26px;line-height:1.25;color:#FFFFFF;margin-top:16px;">
				{_esc(recipient_name)}
			</div>
			<div style="font-family:Arial,Helvetica,sans-serif;font-size:13px;color:#B7B7B7;margin-top:10px;line-height:1.5;">
				{subtitle}
			</div>
			{cycle_line}
		</td>
	</tr>

	{body_sections}

	{_report_signoff_html()}

	<tr>
		<td style="background-color:#F5F5F5;border-top:1px solid #E0E0E0;padding:16px 36px;">
			<p style="font-family:Arial,Helvetica,sans-serif;font-size:10px;line-height:1.5;color:#9A9A9A;margin:0;">
				{_esc(footer_note)}
			</p>
		</td>
	</tr>

</table>
</td></tr>
</table>
</body>
</html>
	"""


def _cycle_line_html(cycle):
	if not cycle:
		return ""
	return (
		f'<div style="font-family:Arial,Helvetica,sans-serif;font-size:11px;color:#767676;margin-top:6px;">'
		f"Assessment cycle {_esc(cycle.name)} · Organisation completion {flt(cycle.completion_pct):.0f}%"
		f"</div>"
	)


def _section_block(section_no, title, intro, inner_html):
	return f"""
	<tr>
		<td style="padding:28px 36px 8px 36px;">
			<div style="font-family:Arial,Helvetica,sans-serif;font-size:10px;letter-spacing:1.5px;text-transform:uppercase;color:#767676;font-weight:700;margin-bottom:4px;">
				Section {section_no}
			</div>
			<div style="font-family:Georgia,'Times New Roman',serif;font-size:20px;color:#000000;margin-bottom:6px;">
				{_esc(title)}
			</div>
			<p style="font-family:Arial,Helvetica,sans-serif;font-size:12px;line-height:1.5;color:#767676;margin:0 0 12px 0;">
				{intro}
			</p>
			{inner_html}
		</td>
	</tr>
	"""


def _render_md_html(
	mgr,
	period_start,
	period_end,
	managers,
	org_overall_avg,
	org_headcount,
	cycle,
	digest_title="Leadership Performance Digest",
):
	by_individual = sorted(
		[m for m in managers if m.get("has_individual_data")],
		key=lambda r: flt(r.get("individual_pct")),
		reverse=True,
	)
	by_team = sorted(
		[m for m in managers if m.get("team_avg") is not None],
		key=lambda r: flt(r.get("team_avg")),
		reverse=True,
	)

	indiv_rows = "".join(
		_rank_bar_row(
			m["manager_name"],
			m.get("individual_pct"),
			_percentile_label(m["individual_percentile"]) if m.get("individual_percentile") is not None else "—",
			sub_label=m.get("departments"),
		)
		for m in by_individual
	) or """<tr><td colspan="4" style="padding:14px 0;font-family:Arial,Helvetica,sans-serif;font-size:13px;color:#767676;">
		No manager individual scores in this period yet.</td></tr>"""

	team_rows = "".join(
		_rank_bar_row(
			m["manager_name"],
			m.get("team_avg"),
			f"{cint(m.get('team_scored') or 0)}/{cint(m.get('team_size') or 0)} scored",
			sub_label=m.get("departments"),
		)
		for m in by_team
	) or """<tr><td colspan="4" style="padding:14px 0;font-family:Arial,Helvetica,sans-serif;font-size:13px;color:#767676;">
		No team averages available yet.</td></tr>"""

	detail = ""
	for i, m in enumerate(sorted(managers, key=lambda r: flt(r.get("team_avg") if r.get("team_avg") is not None else -1), reverse=True)):
		bg = "#FAFAFA" if i % 2 else "#FFFFFF"
		indiv = f'{flt(m["individual_pct"]):.0f}%' if m.get("has_individual_data") else "—"
		tavg = f'{flt(m["team_avg"]):.0f}%' if m.get("team_avg") is not None else "—"
		detail += f"""
		<tr style="background:{bg};">
			<td style="padding:12px 14px;font-family:Arial,Helvetica,sans-serif;font-size:13px;color:#1A1A1A;border-bottom:1px solid #EEEEEE;">{_esc(m['manager_name'])}</td>
			<td style="padding:12px 14px;font-family:Arial,Helvetica,sans-serif;font-size:12px;color:#767676;border-bottom:1px solid #EEEEEE;">{_esc(m.get('departments') or '—')}</td>
			<td style="padding:12px 14px;font-family:Arial,Helvetica,sans-serif;font-size:13px;font-weight:700;text-align:right;border-bottom:1px solid #EEEEEE;">{indiv}</td>
			<td style="padding:12px 14px;font-family:Arial,Helvetica,sans-serif;font-size:13px;font-weight:700;text-align:right;border-bottom:1px solid #EEEEEE;">{tavg}</td>
			<td style="padding:12px 14px;font-family:Arial,Helvetica,sans-serif;font-size:12px;text-align:right;border-bottom:1px solid #EEEEEE;">{cint(m.get('team_size') or 0)}</td>
			<td style="padding:12px 14px;font-family:Arial,Helvetica,sans-serif;font-size:12px;text-align:right;border-bottom:1px solid #EEEEEE;">{cint(m.get('reviewer_count') or 0)}</td>
		</tr>
		"""
	if not detail:
		detail = """<tr><td colspan="6" style="padding:20px 14px;font-family:Arial,Helvetica,sans-serif;font-size:13px;color:#767676;">
			No Team Leaders configured. Set them in Roles &amp; Org.</td></tr>"""

	org_avg_disp = f"{org_overall_avg:.0f}%" if org_overall_avg is not None else "—"
	top_indiv = by_individual[0] if by_individual else None
	top_team = by_team[0] if by_team else None
	insights = [
		f"This leadership digest covers <strong>{len(managers)}</strong> Team Leader(s).",
	]
	if top_indiv:
		insights.append(
			f"Highest individual score: <strong>{_esc(top_indiv['manager_name'])}</strong> "
			f"({flt(top_indiv['individual_pct']):.0f}%)."
		)
	if top_team:
		insights.append(
			f"Strongest team average: <strong>{_esc(top_team['manager_name'])}</strong> "
			f"({flt(top_team['team_avg']):.0f}%)."
		)

	body = f"""
	<tr>
		<td style="padding:28px 36px 8px 36px;">
			<div style="font-family:Arial,Helvetica,sans-serif;font-size:10px;letter-spacing:1.5px;text-transform:uppercase;color:#767676;font-weight:700;margin-bottom:12px;">
				Executive Summary
			</div>
			<p style="font-family:Arial,Helvetica,sans-serif;font-size:14px;line-height:1.65;color:#333333;margin:0;">
				{" ".join(insights)}
			</p>
		</td>
	</tr>
	<tr>
		<td style="padding:20px 36px 8px 36px;">
			<table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%" style="border:1px solid #E0E0E0;border-collapse:collapse;">
				<tr>
					{_kpi_cell("Managers", str(len(managers)), f"{len(by_individual)} with individual scores", True)}
					{_kpi_cell("Teams Scored", str(len(by_team)), f"of {len(managers)} managers", True)}
					{_kpi_cell("Org Average", org_avg_disp, f"{org_headcount} employees" if org_headcount else None, False)}
				</tr>
			</table>
		</td>
	</tr>
	{_section_block("01", "Managers by Individual Score", "Each Team Leader's personal overall score from colleague feedback.", f'<table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%" style="border-collapse:collapse;">{indiv_rows}</table>')}
	{_section_block("02", "Managers by Team Performance", "Average overall score of people on each Team Leader's team.", f'<table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%" style="border-collapse:collapse;">{team_rows}</table>')}
	<tr>
		<td style="padding:28px 36px 8px 36px;">
			<div style="border-top:1px solid #EEEEEE;padding-top:28px;">
				<div style="font-family:Arial,Helvetica,sans-serif;font-size:10px;letter-spacing:1.5px;text-transform:uppercase;color:#767676;font-weight:700;margin-bottom:4px;">Section 03</div>
				<div style="font-family:Georgia,'Times New Roman',serif;font-size:20px;color:#000000;margin-bottom:14px;">Manager Scorecard</div>
				<table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%" style="border-collapse:collapse;border:1px solid #E0E0E0;">
					<thead>
						<tr style="background-color:#000000;">
							<th align="left" style="padding:11px 10px;font-family:Arial,Helvetica,sans-serif;font-size:9px;letter-spacing:0.8px;text-transform:uppercase;color:#FFFFFF;">Manager</th>
							<th align="left" style="padding:11px 10px;font-family:Arial,Helvetica,sans-serif;font-size:9px;letter-spacing:0.8px;text-transform:uppercase;color:#FFFFFF;">Teams</th>
							<th align="right" style="padding:11px 10px;font-family:Arial,Helvetica,sans-serif;font-size:9px;letter-spacing:0.8px;text-transform:uppercase;color:#FFFFFF;">Individual</th>
							<th align="right" style="padding:11px 10px;font-family:Arial,Helvetica,sans-serif;font-size:9px;letter-spacing:0.8px;text-transform:uppercase;color:#FFFFFF;">Team Avg</th>
							<th align="right" style="padding:11px 10px;font-family:Arial,Helvetica,sans-serif;font-size:9px;letter-spacing:0.8px;text-transform:uppercase;color:#FFFFFF;">Team Size</th>
							<th align="right" style="padding:11px 10px;font-family:Arial,Helvetica,sans-serif;font-size:9px;letter-spacing:0.8px;text-transform:uppercase;color:#FFFFFF;">Reviews</th>
						</tr>
					</thead>
					<tbody>{detail}</tbody>
				</table>
			</div>
		</td>
	</tr>
	"""

	return _digest_shell(
		title=digest_title,
		audience="Managing Director Copy · Confidential",
		recipient_name=mgr.employee_name,
		subtitle=f"{formatdate(period_start)} – {formatdate(period_end)}&nbsp;&nbsp;|&nbsp;&nbsp;{_esc(mgr.department) if mgr.department else '—'}&nbsp;&nbsp;|&nbsp;&nbsp;{len(managers)} managers",
		cycle_line=_cycle_line_html(cycle),
		body_sections=body,
		footer_note="This leadership digest is confidential. Manager and team scores should be discussed with HR before wider circulation.",
	)


def _render_hr_html(
	viewer,
	period_start,
	period_end,
	teams,
	people_rows,
	people_avg,
	org_overall_avg,
	org_headcount,
	cycle,
	digest_title="Organisation Performance Digest",
):
	teams_with = [t for t in teams if t.get("team_avg") is not None]
	team_rank = "".join(
		_rank_bar_row(
			t["department"],
			t.get("team_avg"),
			f"{cint(t.get('scored_count') or 0)}/{cint(t.get('team_size') or 0)}",
			sub_label=f"TL: {t.get('manager_name') or '—'}",
		)
		for t in teams_with
	) or """<tr><td colspan="4" style="padding:14px 0;font-family:Arial,Helvetica,sans-serif;font-size:13px;color:#767676;">
		No team averages available yet. Confirm Team Leaders in Roles &amp; Org.</td></tr>"""

	with_data = [r for r in people_rows if r.get("has_data")]
	indiv_rank = "".join(
		_rank_bar_row(
			r["employee_name"],
			r.get("overall_pct"),
			_percentile_label(r["overall_percentile"]) if r.get("overall_percentile") is not None else "—",
			sub_label=r.get("department"),
		)
		for r in with_data
	) or """<tr><td colspan="4" style="padding:14px 0;font-family:Arial,Helvetica,sans-serif;font-size:13px;color:#767676;">
		No scored individuals in this reporting period yet.</td></tr>"""

	detail_rows = ""
	for i, r in enumerate(people_rows):
		bg = "#FAFAFA" if i % 2 else "#FFFFFF"
		score = f'{flt(r["overall_pct"]):.0f}%' if r.get("has_data") else "—"
		pct = _percentile_label(r["overall_percentile"]) if r.get("overall_percentile") is not None else "—"
		strong = _esc(r["strongest"]) if r.get("strongest") else "—"
		develop = _esc(r["development"]) if r.get("development") else "—"
		detail_rows += f"""
		<tr style="background:{bg};">
			<td style="padding:12px 14px;font-family:Arial,Helvetica,sans-serif;font-size:13px;color:#1A1A1A;border-bottom:1px solid #EEEEEE;">{_esc(r['employee_name'])}</td>
			<td style="padding:12px 14px;font-family:Arial,Helvetica,sans-serif;font-size:12px;color:#767676;border-bottom:1px solid #EEEEEE;">{_esc(r.get('department') or '—')}</td>
			<td style="padding:12px 14px;font-family:Arial,Helvetica,sans-serif;font-size:13px;font-weight:700;text-align:right;border-bottom:1px solid #EEEEEE;">{score}</td>
			<td style="padding:12px 14px;font-family:Arial,Helvetica,sans-serif;font-size:12px;text-align:right;border-bottom:1px solid #EEEEEE;">{pct}</td>
			<td style="padding:12px 14px;font-family:Arial,Helvetica,sans-serif;font-size:12px;text-align:right;border-bottom:1px solid #EEEEEE;">{cint(r.get('reviewer_count') or 0)}</td>
			<td style="padding:12px 14px;font-family:Arial,Helvetica,sans-serif;font-size:12px;border-bottom:1px solid #EEEEEE;">{strong}</td>
			<td style="padding:12px 14px;font-family:Arial,Helvetica,sans-serif;font-size:12px;border-bottom:1px solid #EEEEEE;">{develop}</td>
		</tr>
		"""
	if not detail_rows:
		detail_rows = """<tr><td colspan="7" style="padding:20px 14px;font-family:Arial,Helvetica,sans-serif;font-size:13px;color:#767676;">
			No employees were found for this digest.</td></tr>"""

	people_avg_disp = f"{people_avg:.0f}%" if people_avg is not None else "—"
	org_avg_disp = f"{org_overall_avg:.0f}%" if org_overall_avg is not None else "—"
	top_team = teams_with[0] if teams_with else None
	top_person = with_data[0] if with_data else None
	insights = [
		f"This digest ranks <strong>{len(teams)}</strong> team(s) and covers <strong>{len(people_rows)}</strong> people.",
	]
	if top_team:
		insights.append(
			f"Highest team average: <strong>{_esc(top_team['department'])}</strong> "
			f"({flt(top_team['team_avg']):.0f}%, TL {_esc(top_team.get('manager_name') or '—')})."
		)
	if top_person:
		insights.append(
			f"Highest individual score: <strong>{_esc(top_person['employee_name'])}</strong> "
			f"({flt(top_person['overall_pct']):.0f}%)."
		)

	body = f"""
	<tr>
		<td style="padding:28px 36px 8px 36px;">
			<div style="font-family:Arial,Helvetica,sans-serif;font-size:10px;letter-spacing:1.5px;text-transform:uppercase;color:#767676;font-weight:700;margin-bottom:12px;">
				Executive Summary
			</div>
			<p style="font-family:Arial,Helvetica,sans-serif;font-size:14px;line-height:1.65;color:#333333;margin:0;">
				{" ".join(insights)}
			</p>
		</td>
	</tr>
	<tr>
		<td style="padding:20px 36px 8px 36px;">
			<table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%" style="border:1px solid #E0E0E0;border-collapse:collapse;">
				<tr>
					{_kpi_cell("Teams", str(len(teams)), f"{len(teams_with)} with scores", True)}
					{_kpi_cell("People", str(len(people_rows)), f"{len(with_data)} with reviews", True)}
					{_kpi_cell("Org Average", people_avg_disp, f"Benchmark {org_avg_disp}", False)}
				</tr>
			</table>
		</td>
	</tr>
	{_section_block("01", "Team Ranking", "Departments ranked by average team member score (Team Leader shown under each team).", f'<table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%" style="border-collapse:collapse;">{team_rank}</table>')}
	{_section_block("02", "Individual Ranking", "All active employees by overall score (green bar) with organisation percentile.", f'<table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%" style="border-collapse:collapse;">{indiv_rank}</table>')}
	<tr>
		<td style="padding:28px 36px 8px 36px;">
			<div style="border-top:1px solid #EEEEEE;padding-top:28px;">
				<div style="font-family:Arial,Helvetica,sans-serif;font-size:10px;letter-spacing:1.5px;text-transform:uppercase;color:#767676;font-weight:700;margin-bottom:4px;">Section 03</div>
				<div style="font-family:Georgia,'Times New Roman',serif;font-size:20px;color:#000000;margin-bottom:14px;">Individual Breakdown</div>
				<table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%" style="border-collapse:collapse;border:1px solid #E0E0E0;">
					<thead>
						<tr style="background-color:#000000;">
							<th align="left" style="padding:11px 10px;font-family:Arial,Helvetica,sans-serif;font-size:9px;letter-spacing:0.8px;text-transform:uppercase;color:#FFFFFF;">Employee</th>
							<th align="left" style="padding:11px 10px;font-family:Arial,Helvetica,sans-serif;font-size:9px;letter-spacing:0.8px;text-transform:uppercase;color:#FFFFFF;">Dept</th>
							<th align="right" style="padding:11px 10px;font-family:Arial,Helvetica,sans-serif;font-size:9px;letter-spacing:0.8px;text-transform:uppercase;color:#FFFFFF;">Score</th>
							<th align="right" style="padding:11px 10px;font-family:Arial,Helvetica,sans-serif;font-size:9px;letter-spacing:0.8px;text-transform:uppercase;color:#FFFFFF;">%ile</th>
							<th align="right" style="padding:11px 10px;font-family:Arial,Helvetica,sans-serif;font-size:9px;letter-spacing:0.8px;text-transform:uppercase;color:#FFFFFF;">Reviews</th>
							<th align="left" style="padding:11px 10px;font-family:Arial,Helvetica,sans-serif;font-size:9px;letter-spacing:0.8px;text-transform:uppercase;color:#FFFFFF;">Strength</th>
							<th align="left" style="padding:11px 10px;font-family:Arial,Helvetica,sans-serif;font-size:9px;letter-spacing:0.8px;text-transform:uppercase;color:#FFFFFF;">Focus</th>
						</tr>
					</thead>
					<tbody>{detail_rows}</tbody>
				</table>
			</div>
		</td>
	</tr>
	"""

	return _digest_shell(
		title=digest_title,
		audience="HR Copy · Confidential",
		recipient_name=viewer.employee_name,
		subtitle=f"{formatdate(period_start)} – {formatdate(period_end)}&nbsp;&nbsp;|&nbsp;&nbsp;Organisation&nbsp;&nbsp;|&nbsp;&nbsp;{len(teams)} teams · {len(people_rows)} people",
		cycle_line=_cycle_line_html(cycle),
		body_sections=body,
		footer_note="This organisation digest is confidential and intended for HR. Do not forward individual scores outside authorised channels.",
	)


def _render_manager_html(
	mgr,
	period_start,
	period_end,
	team_rows,
	team_avg,
	org_overall_avg,
	org_headcount,
	cycle,
	digest_title="Team Performance Digest",
	audience_label="Manager Copy · Confidential",
	scope_label="team",
):
	dept = _esc(mgr.department) if mgr.department else "—"
	with_data = [r for r in team_rows if r.get("has_data")]
	reviewed = sum(1 for r in team_rows if cint(r.get("reviewer_count")))
	cycle_line = ""
	if cycle:
		cycle_line = (
			f'<div style="font-family:Arial,Helvetica,sans-serif;font-size:11px;color:#767676;margin-top:6px;">'
			f"Assessment cycle {_esc(cycle.name)} · Organisation completion {flt(cycle.completion_pct):.0f}%"
			f"</div>"
		)

	# Ranking bars for team members with data
	rank_rows = ""
	for r in with_data:
		pct_w = max(int(round(flt(r["overall_pct"]))), 2) if r.get("overall_pct") else 0
		empty_w = 100 - pct_w
		pct_label = (
			_percentile_label(r["overall_percentile"])
			if r.get("overall_percentile") is not None
			else "—"
		)
		rank_rows += f"""
		<tr>
			<td style="padding:10px 12px 10px 0;width:160px;vertical-align:middle;font-family:Arial,Helvetica,sans-serif;font-size:13px;color:#1A1A1A;">
				{_esc(r['employee_name'])}
			</td>
			<td style="padding:10px 0;vertical-align:middle;">
				<table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%" style="border-collapse:collapse;">
					<tr>
						<td width="{pct_w}%" style="background-color:#86BC25;height:12px;font-size:0;line-height:0;">&nbsp;</td>
						<td width="{empty_w}%" style="background-color:#F0F0F0;height:12px;font-size:0;line-height:0;">&nbsp;</td>
					</tr>
				</table>
			</td>
			<td style="padding:10px 0 10px 12px;width:48px;text-align:right;font-family:Arial,Helvetica,sans-serif;font-size:13px;font-weight:700;color:#1A1A1A;">
				{flt(r['overall_pct']):.0f}%
			</td>
			<td style="padding:10px 0 10px 8px;width:56px;text-align:right;font-family:Arial,Helvetica,sans-serif;font-size:11px;color:#767676;">
				{pct_label}
			</td>
		</tr>
		"""

	if not rank_rows:
		rank_rows = """
		<tr><td colspan="4" style="padding:14px 0;font-family:Arial,Helvetica,sans-serif;font-size:13px;color:#767676;">
			No scored team members in this reporting period yet.
		</td></tr>
		"""

	detail_rows = ""
	for i, r in enumerate(team_rows):
		bg = "#FAFAFA" if i % 2 else "#FFFFFF"
		score = f'{flt(r["overall_pct"]):.0f}%' if r.get("has_data") else "—"
		pct = _percentile_label(r["overall_percentile"]) if r.get("overall_percentile") is not None else "—"
		strong = _esc(r["strongest"]) if r.get("strongest") else "—"
		develop = _esc(r["development"]) if r.get("development") else "—"
		detail_rows += f"""
		<tr style="background:{bg};">
			<td style="padding:12px 14px;font-family:Arial,Helvetica,sans-serif;font-size:13px;color:#1A1A1A;border-bottom:1px solid #EEEEEE;">{_esc(r['employee_name'])}</td>
			<td style="padding:12px 14px;font-family:Arial,Helvetica,sans-serif;font-size:12px;color:#767676;border-bottom:1px solid #EEEEEE;">{_esc(r.get('department') or '—')}</td>
			<td style="padding:12px 14px;font-family:Arial,Helvetica,sans-serif;font-size:13px;font-weight:700;text-align:right;border-bottom:1px solid #EEEEEE;">{score}</td>
			<td style="padding:12px 14px;font-family:Arial,Helvetica,sans-serif;font-size:12px;text-align:right;border-bottom:1px solid #EEEEEE;">{pct}</td>
			<td style="padding:12px 14px;font-family:Arial,Helvetica,sans-serif;font-size:12px;text-align:right;border-bottom:1px solid #EEEEEE;">{cint(r.get('reviewer_count') or 0)}</td>
			<td style="padding:12px 14px;font-family:Arial,Helvetica,sans-serif;font-size:12px;border-bottom:1px solid #EEEEEE;">{strong}</td>
			<td style="padding:12px 14px;font-family:Arial,Helvetica,sans-serif;font-size:12px;border-bottom:1px solid #EEEEEE;">{develop}</td>
		</tr>
		"""

	team_avg_disp = f"{team_avg:.0f}%" if team_avg is not None else "—"
	org_avg_disp = f"{org_overall_avg:.0f}%" if org_overall_avg is not None else "—"
	top = with_data[0] if with_data else None
	bottom = with_data[-1] if len(with_data) > 1 else None
	insights = []
	scope_word = "organisation" if scope_label == "organisation" else "team"
	insights.append(
		f"This digest covers <strong>{len(team_rows)}</strong> {scope_word} member(s); "
		f"<strong>{len(with_data)}</strong> have scored feedback in the period."
	)
	if top:
		insights.append(
			f"Highest overall score: <strong>{_esc(top['employee_name'])}</strong> ({flt(top['overall_pct']):.0f}%)."
		)
	if bottom and top and bottom["employee"] != top["employee"]:
		insights.append(
			f"Lowest overall score: <strong>{_esc(bottom['employee_name'])}</strong> ({flt(bottom['overall_pct']):.0f}%)."
		)

	section_rank = "Organisation Ranking" if scope_label == "organisation" else "Team Ranking"
	section_detail = "People Detail" if scope_label == "organisation" else "Team Member Detail"
	kpi_size_label = "People Covered" if scope_label == "organisation" else "Team Size"
	empty_detail = (
		"No employees were found for this digest."
		if scope_label == "organisation"
		else "No team members were found for this manager. Confirm Team Leader assignments in Roles &amp; Org."
	)
	if not detail_rows:
		detail_rows = f"""
		<tr><td colspan="7" style="padding:20px 14px;font-family:Arial,Helvetica,sans-serif;font-size:13px;color:#767676;">
			{empty_detail}
		</td></tr>
		"""

	return f"""
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{_esc(digest_title)}</title>
</head>
<body style="margin:0;padding:0;background-color:#F5F5F5;">
<table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%" style="background-color:#F5F5F5;padding:24px 12px;">
<tr><td align="center">
<table role="presentation" cellpadding="0" cellspacing="0" border="0" width="680" style="max-width:680px;width:100%;background-color:#FFFFFF;border-collapse:collapse;">

	{_report_accent_bar()}

	<tr>
		<td style="background-color:#000000;padding:28px 36px 24px 36px;">
			{_report_masthead_branding(digest_title, right_label=audience_label)}
			<div style="font-family:Georgia,'Times New Roman',serif;font-size:26px;line-height:1.25;color:#FFFFFF;margin-top:16px;">
				{_esc(mgr.employee_name)}
			</div>
			<div style="font-family:Arial,Helvetica,sans-serif;font-size:13px;color:#B7B7B7;margin-top:10px;line-height:1.5;">
				{formatdate(period_start)} – {formatdate(period_end)}&nbsp;&nbsp;|&nbsp;&nbsp;{dept}
				&nbsp;&nbsp;|&nbsp;&nbsp;{len(team_rows)} people
			</div>
			{cycle_line}
		</td>
	</tr>

	<tr>
		<td style="padding:28px 36px 8px 36px;">
			<div style="font-family:Arial,Helvetica,sans-serif;font-size:10px;letter-spacing:1.5px;text-transform:uppercase;color:#767676;font-weight:700;margin-bottom:12px;">
				Executive Summary
			</div>
			<p style="font-family:Arial,Helvetica,sans-serif;font-size:14px;line-height:1.65;color:#333333;margin:0;">
				{" ".join(insights)}
			</p>
		</td>
	</tr>

	<tr>
		<td style="padding:20px 36px 8px 36px;">
			<table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%" style="border:1px solid #E0E0E0;border-collapse:collapse;">
				<tr>
					{_kpi_cell(kpi_size_label, str(len(team_rows)), f"{reviewed} with reviews", True)}
					{_kpi_cell("Average Score", team_avg_disp, f"Org average {org_avg_disp}", True)}
					{_kpi_cell("Scored Members", str(len(with_data)), f"of {org_headcount} in organisation" if org_headcount else None, False)}
				</tr>
			</table>
		</td>
	</tr>

	<tr>
		<td style="padding:28px 36px 8px 36px;">
			<div style="font-family:Arial,Helvetica,sans-serif;font-size:10px;letter-spacing:1.5px;text-transform:uppercase;color:#767676;font-weight:700;margin-bottom:4px;">
				Section 01
			</div>
			<div style="font-family:Georgia,'Times New Roman',serif;font-size:20px;color:#000000;margin-bottom:6px;">
				{section_rank}
			</div>
			<p style="font-family:Arial,Helvetica,sans-serif;font-size:12px;line-height:1.5;color:#767676;margin:0 0 12px 0;">
				Overall score by person (green bar) with organisation percentile — {len(with_data)} of {len(team_rows)} people shown.
			</p>
			<table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%" style="border-collapse:collapse;">
				{rank_rows}
			</table>
		</td>
	</tr>

	<tr>
		<td style="padding:28px 36px 8px 36px;">
			<div style="border-top:1px solid #EEEEEE;padding-top:28px;">
				<div style="font-family:Arial,Helvetica,sans-serif;font-size:10px;letter-spacing:1.5px;text-transform:uppercase;color:#767676;font-weight:700;margin-bottom:4px;">
					Section 02
				</div>
				<div style="font-family:Georgia,'Times New Roman',serif;font-size:20px;color:#000000;margin-bottom:14px;">
					{section_detail}
				</div>
				<table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%" style="border-collapse:collapse;border:1px solid #E0E0E0;">
					<thead>
						<tr style="background-color:#000000;">
							<th align="left" style="padding:11px 10px;font-family:Arial,Helvetica,sans-serif;font-size:9px;letter-spacing:0.8px;text-transform:uppercase;color:#FFFFFF;">Employee</th>
							<th align="left" style="padding:11px 10px;font-family:Arial,Helvetica,sans-serif;font-size:9px;letter-spacing:0.8px;text-transform:uppercase;color:#FFFFFF;">Dept</th>
							<th align="right" style="padding:11px 10px;font-family:Arial,Helvetica,sans-serif;font-size:9px;letter-spacing:0.8px;text-transform:uppercase;color:#FFFFFF;">Score</th>
							<th align="right" style="padding:11px 10px;font-family:Arial,Helvetica,sans-serif;font-size:9px;letter-spacing:0.8px;text-transform:uppercase;color:#FFFFFF;">%ile</th>
							<th align="right" style="padding:11px 10px;font-family:Arial,Helvetica,sans-serif;font-size:9px;letter-spacing:0.8px;text-transform:uppercase;color:#FFFFFF;">Reviews</th>
							<th align="left" style="padding:11px 10px;font-family:Arial,Helvetica,sans-serif;font-size:9px;letter-spacing:0.8px;text-transform:uppercase;color:#FFFFFF;">Strength</th>
							<th align="left" style="padding:11px 10px;font-family:Arial,Helvetica,sans-serif;font-size:9px;letter-spacing:0.8px;text-transform:uppercase;color:#FFFFFF;">Focus</th>
						</tr>
					</thead>
					<tbody>{detail_rows}</tbody>
				</table>
			</div>
		</td>
	</tr>

	{_report_signoff_html(
		"Use this digest in 1:1s to recognise strong performance and agree development priorities. Individual reports have been issued separately to each employee."
	)}

	<tr>
		<td style="background-color:#F5F5F5;border-top:1px solid #E0E0E0;padding:16px 36px;">
			<p style="font-family:Arial,Helvetica,sans-serif;font-size:10px;line-height:1.5;color:#9A9A9A;margin:0;">
				This manager digest is confidential. Do not forward individual scores outside the leadership chain without HR guidance.
			</p>
		</td>
	</tr>

</table>
</td></tr>
</table>
</body>
</html>
	"""


def _remind_incomplete_cycle_pairs(cycle):
	from survey_app.outstanding import _send_one_reminder

	count = 0
	for p in cycle.pairs or []:
		if p.status in ("Assigned", "Overdue") and p.survey:
			try:
				res = _send_one_reminder(p.survey)
				if res.get("status") == "sent":
					count += 1
			except Exception:
				pass
	return count

import frappe
from frappe.utils import get_url, now_datetime, getdate, date_diff, cint, formatdate, add_days, today


@frappe.whitelist()
def get_outstanding_surveys(filters=None, sort_by="days_pending", sort_order="desc"):
	"""Return surveys that were sent but not yet completed, grouped by Survey Cycle."""
	if isinstance(filters, str):
		import json
		filters = json.loads(filters)
	filters = filters or {}

	conditions = [
		"IFNULL(s.is_internal_scoring, 0) = 1",
		"IFNULL(s.rated_by, '') != ''",
		"sr.name IS NULL",
	]
	values = {}

	if filters.get("department"):
		conditions.append("reviewee.department = %(department)s")
		values["department"] = filters["department"]
	if filters.get("reviewer"):
		conditions.append("s.rated_by = %(reviewer)s")
		values["reviewer"] = filters["reviewer"]
	if filters.get("reviewee"):
		conditions.append("s.employee_score = %(reviewee)s")
		values["reviewee"] = filters["reviewee"]
	if filters.get("from_date"):
		conditions.append("DATE(s.creation) >= %(from_date)s")
		values["from_date"] = filters["from_date"]
	if filters.get("to_date"):
		conditions.append("DATE(s.creation) <= %(to_date)s")
		values["to_date"] = filters["to_date"]
	if filters.get("min_days"):
		conditions.append("DATEDIFF(%(today)s, DATE(s.creation)) >= %(min_days)s")
		values["today"] = today()
		values["min_days"] = cint(filters["min_days"])

	has_cycle_pair = frappe.db.exists("DocType", "Survey Cycle Pair")
	cycle_select = ""
	cycle_join = ""
	if has_cycle_pair:
		cycle_select = """
			, scp.parent AS cycle
			, COALESCE(sc.title, scp.parent) AS cycle_title
			, sc.status AS cycle_status
			, sc.period_start AS cycle_period_start
			, sc.period_end AS cycle_period_end
			, sc.completeness_cycle AS completeness_cycle
		"""
		cycle_join = """
		LEFT JOIN `tabSurvey Cycle Pair` scp ON scp.survey = s.name
		LEFT JOIN `tabSurvey Cycle` sc ON sc.name = scp.parent
		"""
		if filters.get("cycle"):
			if filters["cycle"] == "__none__":
				conditions.append("scp.parent IS NULL")
			else:
				conditions.append("scp.parent = %(cycle)s")
				values["cycle"] = filters["cycle"]

	where_sql = " AND ".join(conditions)

	rows = frappe.db.sql(
		f"""
		SELECT
			s.name AS survey,
			s.title,
			s.creation AS sent_on,
			s.rated_by AS reviewer_user,
			s.employee_score AS reviewee,
			COALESCE(reviewer.employee_name, s.rated_by) AS reviewer_name,
			COALESCE(u.email, s.rated_by) AS reviewer_email,
			COALESCE(reviewee.employee_name, s.employee_score) AS reviewee_name,
			COALESCE(reviewee.department, 'No Department') AS department,
			DATEDIFF(%(as_of)s, DATE(s.creation)) AS days_pending
			{cycle_select}
		FROM `tabSurvey` s
		LEFT JOIN `tabSurvey Response` sr
			ON sr.survey = s.name AND IFNULL(sr.docstatus, 0) < 2
		LEFT JOIN `tabUser` u ON u.name = s.rated_by
		LEFT JOIN `tabEmployee` reviewer ON reviewer.user_id = s.rated_by
		LEFT JOIN `tabEmployee` reviewee ON reviewee.name = s.employee_score
		{cycle_join}
		WHERE {where_sql}
		""",
		{**values, "as_of": today()},
		as_dict=True,
	)

	base_url = get_url()
	for row in rows:
		row["survey_url"] = f"{base_url}/survey?id={row.survey}"
		row["sent_on"] = str(row.sent_on) if row.sent_on else ""
		row["days_pending"] = cint(row.days_pending)
		row["cycle"] = row.get("cycle") or None
		row["cycle_title"] = row.get("cycle_title") or None
		row["cycle_status"] = row.get("cycle_status") or None
		row["cycle_period_start"] = str(row.get("cycle_period_start") or "")
		row["cycle_period_end"] = str(row.get("cycle_period_end") or "")
		row["completeness_cycle"] = row.get("completeness_cycle") or ""

	sort_key = sort_by or "days_pending"
	reverse = (sort_order or "desc").lower() != "asc"
	valid_keys = {
		"days_pending",
		"sent_on",
		"reviewer_name",
		"reviewee_name",
		"department",
		"survey",
		"title",
		"cycle_title",
	}
	if sort_key not in valid_keys:
		sort_key = "days_pending"

	rows.sort(key=lambda r: (r.get(sort_key) is None, r.get(sort_key)), reverse=reverse)

	# Summary by reviewer for HR overview
	by_reviewer = {}
	for row in rows:
		key = row.reviewer_user or "Unknown"
		if key not in by_reviewer:
			by_reviewer[key] = {
				"reviewer_user": key,
				"reviewer_name": row.reviewer_name,
				"reviewer_email": row.reviewer_email,
				"pending_count": 0,
				"max_days": 0,
			}
		by_reviewer[key]["pending_count"] += 1
		by_reviewer[key]["max_days"] = max(by_reviewer[key]["max_days"], row.days_pending)

	reviewer_summary = sorted(
		by_reviewer.values(),
		key=lambda x: (x["pending_count"], x["max_days"]),
		reverse=True,
	)

	groups = _group_rows_by_cycle(rows)

	cycle_options = []
	if has_cycle_pair and frappe.db.exists("DocType", "Survey Cycle"):
		cycle_options = frappe.get_all(
			"Survey Cycle",
			fields=["name", "title", "status", "period_start", "period_end"],
			order_by="period_start desc, creation desc",
		)
		for c in cycle_options:
			c["period_start"] = str(c.get("period_start") or "")
			c["period_end"] = str(c.get("period_end") or "")

	return {
		"rows": rows,
		"groups": groups,
		"cycles": cycle_options,
		"total": len(rows),
		"reviewers_pending": len(by_reviewer),
		"by_reviewer": reviewer_summary,
		"sort_by": sort_key,
		"sort_order": "desc" if reverse else "asc",
	}


def _group_rows_by_cycle(rows):
	"""Group outstanding rows by Survey Cycle (open cycles first, then newest period, then unlinked)."""
	grouped = {}
	for row in rows:
		key = row.get("cycle") or "__none__"
		if key not in grouped:
			grouped[key] = {
				"cycle": row.get("cycle"),
				"cycle_title": row.get("cycle_title") or ("No Cycle" if key == "__none__" else key),
				"cycle_status": row.get("cycle_status") or "",
				"cycle_period_start": row.get("cycle_period_start") or "",
				"cycle_period_end": row.get("cycle_period_end") or "",
				"completeness_cycle": row.get("completeness_cycle") or "",
				"pending_count": 0,
				"max_days": 0,
				"rows": [],
			}
		grouped[key]["rows"].append(row)
		grouped[key]["pending_count"] += 1
		grouped[key]["max_days"] = max(grouped[key]["max_days"], row.days_pending)

	linked = [g for g in grouped.values() if g.get("cycle")]
	unlinked = [g for g in grouped.values() if not g.get("cycle")]
	# Stable sorts: newest period first, then Open cycles before others
	linked.sort(key=lambda g: g.get("cycle_period_start") or "", reverse=True)
	linked.sort(key=lambda g: 0 if (g.get("cycle_status") or "") == "Open" else 1)
	return linked + unlinked


@frappe.whitelist()
def send_survey_reminders(surveys=None, remind_all=0):
	"""Send reminder emails for one or more outstanding surveys."""
	if isinstance(surveys, str):
		import json
		surveys = json.loads(surveys)

	remind_all = cint(remind_all)
	if remind_all:
		data = get_outstanding_surveys()
		surveys = [r["survey"] for r in data.get("rows") or []]

	if not surveys:
		frappe.throw("No surveys selected for reminder")

	sent = []
	skipped = []
	failed = []

	for survey_name in surveys:
		try:
			result = _send_one_reminder(survey_name)
			if result.get("status") == "sent":
				sent.append(result)
			else:
				skipped.append(result)
		except Exception as e:
			frappe.log_error(title="Survey Reminder Failed", message=frappe.get_traceback())
			failed.append({"survey": survey_name, "error": str(e)})

	return {
		"status": "ok",
		"sent": len(sent),
		"skipped": len(skipped),
		"failed": len(failed),
		"details": {"sent": sent, "skipped": skipped, "failed": failed},
	}


def _send_one_reminder(survey_name):
	if not frappe.db.exists("Survey", survey_name):
		return {"survey": survey_name, "status": "missing"}

	# Already completed?
	if frappe.db.exists("Survey Response", {"survey": survey_name}):
		return {"survey": survey_name, "status": "already_completed"}

	survey = frappe.get_doc("Survey", survey_name)
	reviewer_user = survey.rated_by
	if not reviewer_user:
		return {"survey": survey_name, "status": "no_reviewer"}

	reviewer_email = frappe.db.get_value("User", reviewer_user, "email")
	reviewer_name = (
		frappe.db.get_value("Employee", {"user_id": reviewer_user}, "employee_name")
		or frappe.db.get_value("User", reviewer_user, "full_name")
		or reviewer_user
	)
	reviewee_name = (
		frappe.db.get_value("Employee", survey.employee_score, "employee_name")
		or survey.employee_score
	)

	if not reviewer_email:
		return {"survey": survey_name, "status": "no_email", "reviewer": reviewer_user}

	survey_url = f"{get_url()}/survey?id={survey_name}"
	days_pending = date_diff(getdate(today()), getdate(survey.creation))
	expected_completion = formatdate(add_days(today(), 3))

	subject = f"[REMINDER] Please complete your Staff 360° Review for {reviewee_name}"
	message = f"""
	<div style="font-family: Arial, sans-serif; font-size: 14px; color: #333; line-height: 1.5;">
		<div style="background:#fff4e5;border:1px solid #f0c36d;border-left:5px solid #c58a2e;padding:12px 16px;margin:0 0 18px;border-radius:4px;">
			<strong style="color:#9a6700;letter-spacing:0.4px;">REMINDER</strong>
			<div style="margin-top:4px;color:#5c4a1f;">
				This message is a reminder — your survey feedback is still outstanding.
			</div>
		</div>
		<p>Dear {reviewer_name},</p>
		<p>This is a <strong>reminder</strong> that you still need to complete the
		<strong>Staff 360° Review</strong> for <strong>{reviewee_name}</strong>.</p>
		<p>The survey was assigned <strong>{days_pending} day(s)</strong> ago and has not been submitted yet.</p>
		<p><strong>Please complete it by: {expected_completion}</strong></p>
		<p style="margin: 20px 0;">
			<a href="{survey_url}"
			   style="background-color:#2f5f73;color:#fff;padding:10px 18px;text-decoration:none;border-radius:5px;display:inline-block;">
				Complete Reminder Survey
			</a>
		</p>
		<p>If the button does not work, copy and paste this link into your browser:</p>
		<p>{survey_url}</p>
		<br>
		<p>Kind regards,<br>HR Department</p>
	</div>
	"""

	from survey_app.email_log import get_open_cycle_name, send_survey_email

	cycle_name = None
	if frappe.db.exists("DocType", "Survey Cycle Pair"):
		cycle_name = frappe.db.get_value(
			"Survey Cycle Pair",
			{"survey": survey_name},
			"parent",
		)

	send_survey_email(
		email_type="Survey Reminder",
		recipients=[reviewer_email],
		subject=subject,
		message=message,
		cycle=cycle_name or get_open_cycle_name(),
		survey=survey_name,
		employee=getattr(survey, "employee_score", None),
		recipient_name=reviewer_name,
		reference_doctype="Survey",
		reference_name=survey_name,
		expose_recipients="header",
	)

	# In-app notification so the reviewer also sees a clear reminder in desk
	try:
		from frappe.desk.doctype.notification_log.notification_log import enqueue_create_notification
		notification = {
			"type": "Alert",
			"document_type": "Survey",
			"document_name": survey_name,
			"subject": f"Reminder: complete 360° review for {reviewee_name}",
			"email_content": (
				f"<p><b>Reminder</b></p>"
				f"<p>Please complete the Staff 360° Review for <b>{reviewee_name}</b>. "
				f"It has been pending for {days_pending} day(s).</p>"
				f'<p><a href="{survey_url}">Open survey</a></p>'
			),
			"from_user": frappe.session.user,
		}
		enqueue_create_notification([reviewer_user], notification)
	except Exception:
		# Fallback: direct Notification Log
		try:
			frappe.get_doc({
				"doctype": "Notification Log",
				"type": "Alert",
				"for_user": reviewer_user,
				"document_type": "Survey",
				"document_name": survey_name,
				"subject": f"Reminder: complete 360° review for {reviewee_name}",
				"email_content": (
					f"Reminder — please complete the Staff 360° Review for {reviewee_name} "
					f"(pending {days_pending} day(s)). {survey_url}"
				),
				"from_user": frappe.session.user,
			}).insert(ignore_permissions=True)
		except Exception:
			frappe.log_error(title="Survey Reminder Notification Failed", message=frappe.get_traceback())

	# Timeline note for auditability
	frappe.get_doc({
		"doctype": "Comment",
		"comment_type": "Info",
		"reference_doctype": "Survey",
		"reference_name": survey_name,
		"content": f"Reminder email sent to {reviewer_email} at {now_datetime()}",
	}).insert(ignore_permissions=True)

	return {
		"survey": survey_name,
		"status": "sent",
		"reviewer_email": reviewer_email,
		"reviewer_name": reviewer_name,
		"reviewee_name": reviewee_name,
		"days_pending": days_pending,
	}

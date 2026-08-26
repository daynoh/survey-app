"""Survey email delivery audit: invites, reminders, and individual reports."""

from __future__ import annotations

import frappe
from frappe.utils import now_datetime

from survey_app.permissions import survey_admin_required


def get_open_cycle_name():
	if not frappe.db.exists("DocType", "Survey Cycle"):
		return None
	return frappe.db.get_value(
		"Survey Cycle",
		{"status": ["in", ["Open", "Generating", "Reporting"]]},
		"name",
		order_by="period_start desc",
	)


def _find_email_queue(reference_doctype, reference_name, recipient=None):
	filters = {
		"reference_doctype": reference_doctype,
		"reference_name": reference_name,
	}
	rows = frappe.get_all(
		"Email Queue",
		filters=filters,
		fields=["name", "status", "error"],
		order_by="creation desc",
		limit=1,
	)
	if rows:
		return rows[0]

	# Fallback: match by recipient + recent creation (sendmail without reference)
	if recipient:
		rows = frappe.db.sql(
			"""
			SELECT eq.name, eq.status, eq.error
			FROM `tabEmail Queue` eq
			INNER JOIN `tabEmail Queue Recipient` eqr ON eqr.parent = eq.name
			WHERE eqr.recipient = %s
			ORDER BY eq.creation DESC
			LIMIT 1
			""",
			recipient,
			as_dict=True,
		)
		return rows[0] if rows else None
	return None


def send_survey_email(
	*,
	email_type,
	recipients,
	subject,
	message,
	cc=None,
	cycle=None,
	survey=None,
	employee=None,
	report_log=None,
	recipient_name=None,
	reference_doctype=None,
	reference_name=None,
	expose_recipients=None,
):
	"""Send email via frappe.sendmail and create a Survey Email Log row."""
	if isinstance(recipients, str):
		recipients = [recipients]
	recipients = [r for r in (recipients or []) if r]
	cc = [c for c in (cc or []) if c]

	if not recipients:
		log = _insert_log(
			email_type=email_type,
			status="Skipped",
			recipient="(none)",
			recipient_name=recipient_name,
			subject=subject,
			message=message,
			cc=cc,
			cycle=cycle,
			survey=survey,
			employee=employee,
			report_log=report_log,
			error_message="No recipient email",
		)
		return {"status": "skipped", "log": log.name if log else None}

	primary = recipients[0]
	log = _insert_log(
		email_type=email_type,
		status="Queued",
		recipient=primary,
		recipient_name=recipient_name,
		subject=subject,
		message=message,
		cc=cc,
		cycle=cycle or get_open_cycle_name(),
		survey=survey,
		employee=employee,
		report_log=report_log,
	)

	ref_dt = reference_doctype or "Survey Email Log"
	ref_name = reference_name or (log.name if log else None)

	try:
		kwargs = {
			"recipients": recipients,
			"subject": subject,
			"message": message,
			"cc": cc,
			"reference_doctype": ref_dt,
			"reference_name": ref_name,
		}
		if expose_recipients:
			kwargs["expose_recipients"] = expose_recipients
		frappe.sendmail(**kwargs)

		eq = _find_email_queue(ref_dt, ref_name, primary)
		if eq:
			status_map = {
				"Not Sent": "Queued",
				"Sending": "Queued",
				"Sent": "Sent",
				"Error": "Failed",
				"Expired": "Failed",
			}
			updates = {
				"email_queue": eq.name,
				"delivery_status": eq.status,
				"status": status_map.get(eq.status, "Queued"),
			}
			if eq.get("error"):
				updates["error_message"] = str(eq.error)[:500]
			log.db_set(updates, update_modified=False)
		else:
			# Queued for async send, or sent immediately depending on site config
			log.db_set({"status": "Queued", "delivery_status": "Pending"}, update_modified=False)

		return {"status": "queued", "log": log.name, "email_queue": eq.name if eq else None}
	except Exception as e:
		frappe.log_error(title=f"Survey Email Failed ({email_type})", message=frappe.get_traceback())
		log.db_set(
			{"status": "Failed", "error_message": str(e)[:500], "delivery_status": "Error"},
			update_modified=False,
		)
		return {"status": "failed", "log": log.name, "error": str(e)}


def _insert_log(
	*,
	email_type,
	status,
	recipient,
	subject,
	message=None,
	cc=None,
	cycle=None,
	survey=None,
	employee=None,
	report_log=None,
	recipient_name=None,
	error_message=None,
):
	if not frappe.db.exists("DocType", "Survey Email Log"):
		return None
	doc = frappe.get_doc(
		{
			"doctype": "Survey Email Log",
			"email_type": email_type,
			"status": status,
			"recipient": recipient,
			"recipient_name": recipient_name,
			"subject": subject,
			"message_preview": message,
			"cc": ", ".join(cc or []),
			"cycle": cycle,
			"survey": survey,
			"employee": employee,
			"report_log": report_log,
			"sent_at": now_datetime(),
			"error_message": error_message,
		}
	)
	doc.insert(ignore_permissions=True)
	return doc


@frappe.whitelist()
@survey_admin_required
def refresh_log_status(name):
	doc = frappe.get_doc("Survey Email Log", name)
	doc.refresh_delivery_status()
	if doc.email_queue and frappe.db.exists("Email Queue", doc.email_queue):
		doc.db_set(
			"delivery_status",
			frappe.db.get_value("Email Queue", doc.email_queue, "status"),
			update_modified=False,
		)
	return {"name": doc.name, "status": doc.status, "delivery_status": doc.delivery_status}


@frappe.whitelist()
@survey_admin_required
def refresh_all_delivery_status(limit=200):
	logs = frappe.get_all(
		"Survey Email Log",
		filters={"status": ["in", ["Queued", "Failed"]], "email_queue": ["is", "set"]},
		pluck="name",
		limit=cint_safe(limit, 200),
	)
	updated = 0
	for name in logs:
		doc = frappe.get_doc("Survey Email Log", name)
		before = doc.status
		doc.refresh_delivery_status()
		if doc.email_queue:
			ds = frappe.db.get_value("Email Queue", doc.email_queue, "status")
			doc.db_set("delivery_status", ds, update_modified=False)
		if doc.status != before:
			updated += 1
	frappe.db.commit()
	return {"updated": updated, "checked": len(logs)}


def cint_safe(val, default=0):
	try:
		return int(val)
	except Exception:
		return default


def sync_queued_email_statuses():
	"""Scheduler-friendly sync for open/queued survey emails."""
	if not frappe.db.exists("DocType", "Survey Email Log"):
		return
	refresh_all_delivery_status(limit=500)

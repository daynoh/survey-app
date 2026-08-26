# Copyright (c) 2026, kim and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class SurveyEmailLog(Document):
	def refresh_delivery_status(self):
		"""Sync status from linked Email Queue row when present."""
		if not self.email_queue or not frappe.db.exists("Email Queue", self.email_queue):
			return self.status

		eq_status = frappe.db.get_value("Email Queue", self.email_queue, "status")
		mapping = {
			"Not Sent": "Queued",
			"Sending": "Queued",
			"Sent": "Sent",
			"Error": "Failed",
			"Expired": "Failed",
		}
		new_status = mapping.get(eq_status, self.status)
		if new_status != self.status:
			self.db_set("status", new_status, update_modified=False)
			if eq_status == "Error":
				err = frappe.db.get_value("Email Queue", self.email_queue, "error") or ""
				self.db_set("error_message", err[:500], update_modified=False)
		return new_status

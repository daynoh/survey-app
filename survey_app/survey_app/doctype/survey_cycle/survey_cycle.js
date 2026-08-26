// Copyright (c) 2026, kim and contributors
// For license information, please see license.txt

frappe.ui.form.on("Survey Cycle", {
	refresh(frm) {
		frm.add_custom_button(
			__("Email Log"),
			() => {
				frappe.set_route("List", "Survey Email Log", {
					cycle: frm.doc.name,
				});
			},
			__("View")
		);
		frm.add_custom_button(
			__("Report Log"),
			() => {
				frappe.set_route("List", "Survey Report Log", {
					cycle: frm.doc.name,
				});
			},
			__("View")
		);
		frm.add_custom_button(
			__("Survey Emails"),
			() => {
				frappe.set_route("List", "Survey Email Log", {
					cycle: frm.doc.name,
					email_type: ["in", ["Survey Invite", "Survey Reminder"]],
				});
			},
			__("View")
		);
		frm.add_custom_button(
			__("Report Emails"),
			() => {
				frappe.set_route("List", "Survey Email Log", {
					cycle: frm.doc.name,
					email_type: "Individual Report",
				});
			},
			__("View")
		);
	},
});

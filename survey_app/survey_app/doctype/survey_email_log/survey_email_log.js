// Copyright (c) 2026, kim and contributors
// For license information, please see license.txt

frappe.ui.form.on("Survey Email Log", {
	refresh(frm) {
		frm.add_custom_button(__("Refresh Delivery Status"), () => {
			frappe.call({
				method: "survey_app.email_log.refresh_log_status",
				args: { name: frm.doc.name },
				freeze: true,
				callback(r) {
					if (!r.exc) {
						frm.reload_doc();
						frappe.show_alert({ message: __("Status updated"), indicator: "green" });
					}
				},
			});
		});
		if (frm.doc.email_queue) {
			frm.add_custom_button(__("Open Email Queue"), () => {
				frappe.set_route("Form", "Email Queue", frm.doc.email_queue);
			});
		}
	},
});

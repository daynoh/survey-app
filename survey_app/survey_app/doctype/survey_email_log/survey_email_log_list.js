// Copyright (c) 2026, kim and contributors
// For license information, please see license.txt

frappe.listview_settings["Survey Email Log"] = {
	add_fields: ["status", "email_type", "cycle", "delivery_status"],
	filters: [["status", "!=", ""]],
	get_indicator(doc) {
		const colors = {
			Queued: "orange",
			Sent: "green",
			Failed: "red",
			Skipped: "darkgrey",
		};
		return [__(doc.status), colors[doc.status] || "blue", "status,=," + doc.status];
	},
	onload(listview) {
		listview.page.add_inner_button(__("Refresh All Delivery Status"), () => {
			frappe.call({
				method: "survey_app.email_log.refresh_all_delivery_status",
				freeze: true,
				freeze_message: __("Syncing with Email Queue..."),
				callback(r) {
					if (!r.exc) {
						listview.refresh();
						frappe.show_alert({
							message: __("Updated {0} log(s)", [(r.message && r.message.updated) || 0]),
							indicator: "green",
						});
					}
				},
			});
		});
	},
};

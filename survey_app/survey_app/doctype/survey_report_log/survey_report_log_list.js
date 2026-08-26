// Copyright (c) 2026, kim and contributors
// For license information, please see license.txt

frappe.listview_settings["Survey Report Log"] = {
	add_fields: ["status", "report_type", "cycle", "employee_name"],
	get_indicator(doc) {
		const colors = {
			Pending: "orange",
			Sent: "green",
			Failed: "red",
			Skipped: "darkgrey",
		};
		return [__(doc.status), colors[doc.status] || "blue", "status,=," + doc.status];
	},
};

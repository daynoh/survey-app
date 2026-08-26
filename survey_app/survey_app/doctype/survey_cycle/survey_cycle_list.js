// Copyright (c) 2026, kim and contributors
// For license information, please see license.txt

frappe.listview_settings["Survey Cycle"] = {
	add_fields: ["status", "completion_pct", "period_start", "period_end"],
	get_indicator(doc) {
		const colors = {
			Open: "blue",
			Generating: "orange",
			Reporting: "purple",
			Closed: "green",
		};
		return [__(doc.status), colors[doc.status] || "gray", "status,=," + doc.status];
	},
};

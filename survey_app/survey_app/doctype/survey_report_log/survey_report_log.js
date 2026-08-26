// Copyright (c) 2026, kim and contributors
// For license information, please see license.txt

frappe.ui.form.on("Survey Report Log", {
	refresh(frm) {
		if (frm.doc.cycle) {
			frm.add_custom_button(__("Open Cycle"), () => {
				frappe.set_route("Form", "Survey Cycle", frm.doc.cycle);
			});
		}
	},
});

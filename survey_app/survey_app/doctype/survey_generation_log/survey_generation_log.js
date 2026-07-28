// Copyright (c) 2026, kim and contributors
// For license information, please see license.txt

frappe.ui.form.on("Survey Generation Log", {
	refresh(frm) {
		frm.disable_save();
		frm.set_read_only();
	},
});

frappe.listview_settings["Survey"] = {
    onload(listview) {
        listview.page.add_inner_button(__("Generate Surveys"), function() {
            frappe.confirm(
                "This will generate 360-degree surveys for all active employees based on Value Scoring Settings.<br><br>Continue?",
                function() {
                    frappe.call({
                        method: "survey_app.surveys.generate_capped_surveys",
                        freeze: true,
                        freeze_message: __("Generating surveys..."),
                        callback: function(r) {
                            if (!r.exc) {
                                frappe.show_alert({
                                    message: __("Surveys generated successfully"),
                                    indicator: "green"
                                });
                                listview.refresh();
                            }
                        }
                    });
                }
            );
        });
    }
};

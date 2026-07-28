frappe.ui.form.on("Survey", {
    refresh(frm) {
        if (!frm.is_new()) {
            var survey_url = window.location.origin + "/survey?id=" + frm.doc.name;

            frm.add_custom_button(__("Copy Survey Link"), function() {
                navigator.clipboard.writeText(survey_url).then(function() {
                    frappe.show_alert({
                        message: __("Survey link copied: {0}", [survey_url]),
                        indicator: "green"
                    });
                });
            }, __("Actions"));

            frm.add_custom_button(__("Email Survey Link"), function() {
                var d = new frappe.ui.Dialog({
                    title: __("Send Survey Link"),
                    fields: [
                        {
                            label: __("Recipient Email"),
                            fieldname: "email",
                            fieldtype: "Data",
                            reqd: 1
                        }
                    ],
                    primary_action_label: __("Send"),
                    primary_action(values) {
                        frappe.call({
                            method: "frappe.core.doctype.communication.email.make",
                            args: {
                                recipients: values.email,
                                subject: frm.doc.title || "360 Survey",
                                content: '<p>Please complete this 360 review:</p><p><a href="' + survey_url + '">Open Survey</a></p>',
                                send_email: 1
                            },
                            callback: function() {
                                frappe.show_alert({ message: __("Email sent"), indicator: "green" });
                                d.hide();
                            }
                        });
                    }
                });
                d.show();
            }, __("Actions"));

            frm.add_custom_button(__("Open Survey"), function() {
                window.open(survey_url, "_blank");
            }, __("Actions"));
        }
    },
});


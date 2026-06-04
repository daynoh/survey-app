// Copyright (c) 2026, kim and contributors
// For license information, please see license.txt

frappe.ui.form.on("Survey Questions", {
	refresh(frm) {
// web page js begin

frappe.ready(function() {
    // 1️⃣ Robust Extraction of survey name
    // This works even if the URL has query parameters or extra slashes
    const pathSegments = window.location.pathname.split('/').filter(Boolean);
    const survey_name = pathSegments[pathSegments.length - 1]; 

    if (!survey_name || survey_name === 'survey') {
        frappe.msgprint(__("Survey ID could not be identified from the URL."));
        return;
    }

    // 2️⃣ Setup Survey Container
    // Use .toggle() or .css to ensure the layout doesn't "jump"
    $(".form-body").hide();
    
    // Check if element already exists to prevent duplicate rendering on route changes
    if ($("#surveyElement").length === 0) {
        $('<div id="surveyElement" style="display:inline-block;width:100%;min-height:500px;"></div>')
            .insertAfter(".form-body");
    }

    // 3️⃣ Fetch Dynamic Survey JSON
    frappe.call({
        method: "survey_app.survey_app.doctype.survey_questions.survey_questions.get_survey_json",
        args: {
            survey_name: survey_name
        },
        freeze: true, // Shows a loading overlay automatically
        callback: function(r) {
            if (r.message) {
                initializeSurvey(r.message, survey_name);
            } else {
                frappe.show_alert({
                    message: __("Survey configuration not found."),
                    indicator: 'red'
                });
            }
        }
    });

    function initializeSurvey(surveyJson, docName) {
        // Ensure SurveyJS library is loaded before initializing
        if (typeof Survey === "undefined") {
            console.error("SurveyJS library is missing.");
            return;
        }

        const survey = new Survey.Model(surveyJson);

        survey.applyTheme({
            cssVariables: {
                "--sjs-primary-backcolor": "#2c3e50",
                "--sjs-primary-backcolor-light": "rgba(44, 62, 80, 0.1)",
            }
        });

        survey.onComplete.add(function (sender, options) {
            options.showDataSaving(__("Submitting your responses..."));

            frappe.call({
                method: "survey_app.survey_app.doctype.survey_questions.survey_questions.submit_survey",
                args: {
                    survey_id: docName, 
                    response_data: sender.data
                },
                callback: function(res) {
                    if (res.message && res.message.status === "success") {
                        options.showDataSavingSuccess(__("Success! ") + res.message.message);
                    } else {
                        options.showDataSavingError(__("Error: ") + (res.message ? res.message.message : "Submission failed"));
                    }
                }
            });
        });

        $("#surveyElement").Survey({ model: survey });
    }
});

// web page end 

	},
});


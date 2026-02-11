// Copyright (c) 2026, kim and contributors
// For license information, please see license.txt

frappe.ui.form.on("Survey Questions", {
	refresh(frm) {
        frappe.ready(function() {
    // 1. Setup the Survey Container
    // We hide the standard Frappe form and inject our own div
    $(".form-body").hide(); 
    $('<div id="surveyElement" style="display:inline-block;width:100%;height:100%;"></div>').insertAfter(".form-body");

    // 2. Fetch the dynamic Survey Model from your Python backend
    frappe.call({
        method: "survey_app.survey_app.doctype.survey_questions.survey_questions.get_survey_json",
        args: {
            survey_name: "My Awesome Survey" // You can pull this from a URL parameter too
        },
        callback: function(r) {
            if (r.message) {
                initializeSurvey(r.message);
            }
        }
    });

    function initializeSurvey(surveyJson) {
        // Apply a modern theme (requires survey-core and survey-js-ui libraries)
        const survey = new Survey.Model(surveyJson);

        // Optional: Customizing the look
        survey.applyTheme({
            "cssVariables": {
                "--sjs-primary-backcolor": "#2c3e50", // Your brand color
                "--sjs-primary-backcolor-light": "rgba(44, 62, 80, 0.1)",
            }
        });

        // 3. Handle Completion
        survey.onComplete.add(function (sender, options) {
            // Display a loading state
            options.showDataSaving("Submitting your responses...");

            frappe.call({
                method: "survey_app.survey_app.doctype.survey_questions.survey_questions.submit_survey",
                args: {
                    survey_id: "My Awesome Survey",
                    response_data: sender.data // This is the JSON results object
                },
                callback: function(res) {
                    if (res.message.status === "success") {
                        options.showDataSavingSuccess("Success! " + res.message.message);
                    } else {
                        options.showDataSavingError("Something went wrong. Please try again.");
                    }
                }
            });
        });

        // Render the survey
        $("#surveyElement").Survey({ model: survey });
    }
});

	},
});


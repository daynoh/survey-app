import frappe
import json
from frappe.model.document import Document
from frappe.utils import slug

class SurveyQuestions(Document):

    def before_save(self):
        # Auto-generates 'what_is_your_name' from 'What is your name?'
        if not self.question_name and self.title:
            self.question_name = slug(self.title).replace('-', '_')
    

@frappe.whitelist(allow_guest=True)
def get_survey_json(survey_name):
    doc = frappe.get_doc("Survey", survey_name)
    pages = []

    # 1. Add Introduction Page
    if doc.title:
        # We use a multi-line f-string for cleaner HTML structure
        welcome_html = f"""
        <div class="survey-welcome-hero">
            <h1 class="survey-title">{doc.title}</h1>
            <div class="survey-subtitle">{doc.sub_title or ''}</div>
        </div>
        """

        pages.append({
            "name": "intro_page",
            "elements": [
                {
                    "type": "html",
                    "name": "intro_html",
                    "html": welcome_html
                }
            ]
        })

    # 2. Add Questions (One per page for Typeform feel)
    for q in doc.questions:
        question_data = {
            "name": q.question_name,
            "type": q.type,
            "title": q.title,
            "description": q.description, # Added description
            "isRequired": q.is_required
        }
        
        if q.type in ["checkbox", "radiogroup", "dropdown"]:
            question_data["choices"] = [{"value": opt.option_value, "text": opt.option_label} for opt in q.options]
            
        pages.append({
            "elements": [question_data]
        })

    return {
        "showProgressBar": "bottom",
        "firstPageIsStarted": True, # Makes the first page a 'Start' page
        "startSurveyText": "Start Survey",
        "pages": pages
    }

@frappe.whitelist(allow_guest=True)
def submit_survey(survey_id, response_data):
    # Parse stringified JSON if it arrives as a string from the frontend
    if isinstance(response_data, str):
        response_data = json.loads(response_data)

    if not frappe.db.exists("Survey", survey_id):
        frappe.throw("Invalid Survey ID")

    new_res = frappe.get_doc({
        "doctype": "Survey Response",
        "survey": survey_id,
        "submission_date": frappe.utils.now(),
        "answers": []
    })

    for key, value in response_data.items():
        # Clean the value: if it's a list (checkboxes), join with commas
        formatted_value = ", ".join(value) if isinstance(value, list) else value
        
        new_res.append("answers", {
            "question": key,
            "answer": formatted_value
        })
    
    new_res.insert(ignore_permissions=True)
    # Commit is often needed for guest submissions to persist immediately
    frappe.db.commit() 
    return {"status": "success", "message": "Thank you for your response!"}
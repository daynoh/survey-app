import frappe
import json
from frappe.model.document import Document
from frappe.utils import slug

class SurveyQuestions(Document):

    def before_save(self):
        # Auto-generates 'what_is_your_name' from 'What is your name?'
        if not self.question_name and self.title:
            self.question_name = slug(self.title).replace('-', '_')
    

import frappe
from collections import defaultdict

@frappe.whitelist(allow_guest=True)
def get_survey_json(survey_name):
    doc = frappe.get_doc("Survey", survey_name)

    pages_dict = defaultdict(list)

    # -------------------------------------------------
    # 1. Introduction Page (Page 0)
    # -------------------------------------------------
    if doc.title:
        welcome_html = f"""
        <div class="survey-welcome-hero">
            <h1 class="survey-title">{doc.title}</h1>
            <div class="survey-subtitle">{doc.sub_title or ''}</div>
        </div>
        """

        pages_dict[0].append({
            "type": "html",
            "name": "intro_html",
            "html": welcome_html
        })

    # -------------------------------------------------
    # 2. Process Questions
    # -------------------------------------------------
    for q in doc.questions:

        question_data = {
            "name": q.question_name,
            "type": q.type,
            "title": q.title,
            "description": q.description,
            "isRequired": q.is_required
        }

        # -------------------------------------------------
        # Choice-based questions
        # -------------------------------------------------
        if q.type in ["checkbox", "radiogroup", "dropdown"]:
            question_data["choices"] = [
                {
                    "value": opt.option_value,
                    "text": opt.option_label
                }
                for opt in q.options
                if not getattr(opt, "dimension_type", None)
                or opt.dimension_type == "choice"
            ]

        # -------------------------------------------------
        # Rating
        # -------------------------------------------------
        if q.type == "rating":
            if q.options:
                question_data["rateValues"] = [
                    {
                        "value": opt.option_value,
                        "text": opt.option_label
                    }
                    for opt in q.options
                ]

        # -------------------------------------------------
        # Boolean
        # -------------------------------------------------
        if q.type == "boolean":
            question_data.update({
                "valueTrue": getattr(q, "value_true", None) or "Yes",
                "valueFalse": getattr(q, "value_false", None) or "No",
                "renderAs": getattr(q, "render_as", None) or "default",
            })

            if getattr(q, "render_as", None) == "checkbox":
                question_data["useTitleAsLabel"] = True
                question_data["titleLocation"] = "hidden"

        # -------------------------------------------------
        # Matrix
        # -------------------------------------------------
        if q.type == "matrix":

            # Load full child doc (only when needed)
            question = frappe.get_doc("Survey Questions", q.name)

            rows = []
            columns = []

            for opt in question.options:
                if getattr(opt, "dimension_type", None) == "row":
                    rows.append({
                        "value": opt.option_value,
                        "text": opt.option_label
                    })
                elif getattr(opt, "dimension_type", None) == "column":
                    columns.append({
                        "value": opt.option_value,
                        "text": opt.option_label
                    })

            if not rows or not columns:
                frappe.throw(
                    f"Matrix question '{q.title}' must have at least one row and one column."
                )

            question_data.update({
                "rows": rows,
                "columns": columns
            })


        # -------------------------------------------------
        # Assign to Page Number (default = 1)
        # -------------------------------------------------
        page_number = getattr(q, "page_number", 1) or 1
        pages_dict[page_number].append(question_data)

    # -------------------------------------------------
    # 3. Build Final Pages List (Sorted)
    # -------------------------------------------------
    pages = []

    for page_no in sorted(pages_dict.keys()):
        pages.append({
            "name": f"page_{page_no}",
            "elements": pages_dict[page_no]
        })

    # -------------------------------------------------
    # 4. Final Survey JSON
    # -------------------------------------------------
    return {
        "showProgressBar": "bottom",
        "firstPageIsStarted": True,
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
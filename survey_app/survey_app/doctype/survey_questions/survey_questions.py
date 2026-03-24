import frappe
import json
from frappe.model.document import Document
from frappe.utils import slug
from collections import defaultdict


class SurveyQuestions(Document):

    def before_save(self):
        # Auto-generates 'what_is_your_name' from 'What is your name?'
        if not self.question_name and self.title:
            self.question_name = slug(self.title).replace('-', '_')
    


@frappe.whitelist(allow_guest=True)
def get_survey_json(survey_name):

    doc = frappe.get_doc("Survey", survey_name)
    pages_dict = defaultdict(list)

    # -------------------------------------------------
    # 1. Introduction Page
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
            "name": q.name,  # ✅ PRIMARY KEY
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
                    "value": opt.name,   # ✅ PRIMARY KEY
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
                        "value": opt.name,   # ✅ PRIMARY KEY
                        "text": opt.option_label
                    }
                    for opt in q.options
                ]

        # -------------------------------------------------
        # Boolean
        # -------------------------------------------------
        if q.type == "boolean":
            question_data.update({
                "valueTrue": "TRUE",
                "valueFalse": "FALSE",
                "renderAs": getattr(q, "render_as", None) or "default",
            })

        # -------------------------------------------------
        # Matrix
        # -------------------------------------------------
        if q.type == "matrix":
            question = frappe.get_doc("Survey Questions", q.name)

            rows = []
            columns = []

            for opt in question.options:
                if opt.dimension_type == "row":
                    rows.append({
                        "value": opt.name,   # ✅ PRIMARY KEY
                        "text": opt.option_label
                    })
                elif opt.dimension_type == "column":
                    columns.append({
                        "value": opt.name,   # ✅ PRIMARY KEY
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

        page_number = getattr(q, "page_number", 1) or 1
        pages_dict[page_number].append(question_data)

    # -------------------------------------------------
    # 3. Build Pages
    # -------------------------------------------------
    pages = []

    for page_no in sorted(pages_dict.keys()):
        pages.append({
            "name": f"page_{page_no}",
            "elements": pages_dict[page_no]
        })

    return {
        "showProgressBar": "bottom",
        "firstPageIsStarted": True,
        "startSurveyText": "Start Survey",
        "pages": pages
    }



@frappe.whitelist(allow_guest=True)
def submit_survey(survey_id, response_data):
    

    if isinstance(response_data, str):
        response_data = json.loads(response_data)

    if not frappe.db.exists("Survey", survey_id):
        frappe.throw("Invalid Survey ID")

    survey_doc = frappe.get_doc("Survey", survey_id)
    user = frappe.session.user if frappe.session.user != "Guest" else None

    # -----------------------------------------------------
    # Build lookup sets for validation
    # -----------------------------------------------------

    valid_questions = {q.name for q in survey_doc.questions}

    valid_options = {
        opt.name: opt.score or 0
        for q in survey_doc.questions
        for opt in frappe.get_doc("Survey Questions", q.name).options
    }

    # -----------------------------------------------------
    # Create response document
    # -----------------------------------------------------

    response_doc = frappe.get_doc({
        "doctype": "Survey Response",
        "respondent": user,
        "survey": survey_id,
        "submission_date": frappe.utils.now(),
        "answers": []
    }).insert(ignore_permissions=True)
    frappe.db.commit()


    total_score = 0

    # -----------------------------------------------------
    # Process answers
    # -----------------------------------------------------

    for question_id, value in response_data.items():

        # Skip invalid questions
        if question_id not in valid_questions:
            continue

        question_doc = frappe.get_doc("Survey Questions", question_id)

        answer_row = response_doc.append("answers", {
            "question": question_id,
            "question_type": question_doc.type
        }).save(ignore_permissions=True)

        qtype = question_doc.type

        # ---------------------------
        # TEXT
        # ---------------------------
        if qtype == "text":
            answer_row.text_answer = value

        # ---------------------------
        # RATING
        # ---------------------------
        elif qtype == "rating":
            answer_row.number_answer = float(value)

        # ---------------------------
        # RADIO / DROPDOWN
        # ---------------------------
        elif qtype in ["radiogroup", "dropdown"]:

            if value in valid_options:
                answer_row.selected_option = value
                # total_score += valid_options[value]

        # ---------------------------
        # CHECKBOX
        # ---------------------------
        elif qtype == "checkbox" and isinstance(value, list):

            for opt_id in value:
                if opt_id in valid_options:
                    answer_row.append("selections", {
                        "option": opt_id,
                        "score": valid_options[opt_id]
                    })
                    # total_score += valid_options[opt_id]

        # ---------------------------
        # MATRIX
        # value = { row_id: column_id }
        # ---------------------------
        elif qtype == "matrix" and isinstance(value, dict):

            for row_id, column_id in value.items():

                if column_id in valid_options:
                    score = valid_options[column_id]
                    answer_selections = frappe.get_doc("Survey Response Answer", answer_row)


                    answer_selections.append("selections", {
                        "row_option": row_id,
                        "column_option": column_id,
                        "score": score
                    })      
                    answer_selections.save(ignore_permissions=True)

                    # answer_row.append("selections", {
                    #     "row_option": row_id,
                    #     "column_option": column_id,
                    #     "score": score
                    # })
                    # answer_row.append("selections",answer_selections)

                    # total_score += score

    # response_doc.total_score = total_score
    response_doc.save(ignore_permissions=True)

    return {
        "status": "success",
        "message": "Thank you for your response!",
        "total_score": total_score
    }

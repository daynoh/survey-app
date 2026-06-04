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


import json
import frappe

@frappe.whitelist(allow_guest=True)
def submit_survey(survey_id, response_data):
    """
    Submit survey responses with comprehensive error handling and logging.
    
    Args:
        survey_id: ID of the survey
        response_data: JSON string or dict of responses
    
    Returns:
        dict with status, message, total_score, and response_id
    
    Raises:
        frappe.ValidationError: If validation fails
        frappe.ServerError: If database operation fails
    """
    
    try:
        # Parse response data
        if isinstance(response_data, str):
            try:
                response_data = json.loads(response_data)
            except json.JSONDecodeError as e:
                frappe.throw(f"Invalid JSON in response_data: {str(e)}")

        # Validate survey exists
        if not frappe.db.exists("Survey", survey_id):
            frappe.throw(f"Survey with ID '{survey_id}' does not exist")

        survey_doc = frappe.get_doc("Survey", survey_id)
        user = frappe.session.user if frappe.session.user != "Guest" else None

        # ========== BUILD LOOKUP SETS ==========
        try:
            valid_questions = {q.name for q in survey_doc.questions}
            
            valid_options = {}
            for q in survey_doc.questions:
                question_doc = frappe.get_doc("Survey Questions", q.name)
                for opt in question_doc.options:
                    valid_options[opt.name] = opt.score or 0
            
            frappe.logger().info(f"Survey {survey_id}: {len(valid_questions)} questions loaded")
        except Exception as e:
            frappe.logger().error(f"Error loading survey data: {frappe.get_traceback()}")
            frappe.throw(f"Error loading survey questions: {str(e)}")

        # ========== CREATE RESPONSE DOCUMENT ==========
        try:
            response_doc = frappe.get_doc({
                "doctype": "Survey Response",
                "respondent": user,
                "survey": survey_id,
                "submission_date": frappe.utils.now(),
                "answers": []
            })
            frappe.logger().info(f"Survey response initialized for survey {survey_id}")
        except Exception as e:
            frappe.logger().error(f"Error creating response document: {frappe.get_traceback()}")
            frappe.throw(f"Failed to create response record: {str(e)}")

        total_score = 0
        processing_errors = []
        answer_count = 0
        
        # Store selections to insert separately after parent is created
        selections_to_insert = {}

        # ========== PROCESS ANSWERS ==========
        for question_id, value in response_data.items():
            try:
                # Skip invalid questions
                if question_id not in valid_questions:
                    frappe.logger().warning(f"Skipping invalid question: {question_id}")
                    continue

                question_doc = frappe.get_doc("Survey Questions", question_id)
                
                # Create answer row
                try:
                    answer_row = response_doc.append("answers", {
                        "question": question_id,
                        "question_type": question_doc.type
                    })
                    answer_count += 1
                except Exception as e:
                    error_msg = f"Error appending answer for question {question_id}: {str(e)}"
                    frappe.logger().error(error_msg)
                    processing_errors.append(error_msg)
                    continue

                qtype = question_doc.type

                # ------ TEXT ------
                if qtype == "text":
                    try:
                        answer_row.text_answer = value
                    except Exception as e:
                        processing_errors.append(f"Text answer error for {question_id}: {str(e)}")
                        frappe.logger().error(f"Text answer error: {str(e)}")

                # ------ RATING ------
                elif qtype == "rating":
                    try:
                        answer_row.number_answer = float(value)
                    except (ValueError, TypeError) as e:
                        processing_errors.append(f"Invalid rating value for {question_id}: {value}")
                        frappe.logger().error(f"Rating conversion error: {str(e)}")

                # ------ RADIO / DROPDOWN ------
                elif qtype in ["radiogroup", "dropdown"]:
                    try:
                        if value in valid_options:
                            answer_row.selected_option = value
                            total_score += valid_options[value]
                        else:
                            frappe.logger().warning(f"Invalid option '{value}' for question {question_id}")
                            processing_errors.append(f"Invalid option for {question_id}")
                    except Exception as e:
                        processing_errors.append(f"Radio/dropdown error for {question_id}: {str(e)}")
                        frappe.logger().error(f"Radio/dropdown error: {str(e)}")

                # ------ CHECKBOX ------
                elif qtype == "checkbox" and isinstance(value, list):
                    try:
                        selections_list = []
                        for opt_id in value:
                            if opt_id in valid_options:
                                selections_list.append({
                                    "option": opt_id,
                                    "score": valid_options[opt_id]
                                })
                                total_score += valid_options[opt_id]
                            else:
                                frappe.logger().warning(f"Invalid checkbox option '{opt_id}' for question {question_id}")
                        
                        if selections_list:
                            selections_to_insert[answer_row.idx] = selections_list
                    except Exception as e:
                        processing_errors.append(f"Checkbox error for {question_id}: {str(e)}")
                        frappe.logger().error(f"Checkbox error: {str(e)}")

                # ------ MATRIX ------
                elif qtype == "matrix" and isinstance(value, dict):
                    try:
                        selections_list = []
                        for row_id, column_id in value.items():
                            if column_id in valid_options:
                                score = valid_options[column_id]
                                selections_list.append({
                                    "row_option": row_id,
                                    "column_option": column_id,
                                    "score": score
                                })
                                total_score += score
                            else:
                                frappe.logger().warning(
                                    f"Invalid matrix option '{column_id}' for row '{row_id}' in question {question_id}"
                                )
                        
                        if selections_list:
                            selections_to_insert[answer_row.idx] = selections_list
                    except Exception as e:
                        processing_errors.append(f"Matrix error for {question_id}: {str(e)}")
                        frappe.logger().error(f"Matrix processing error: {frappe.get_traceback()}")

                elif qtype == "matrix" and not isinstance(value, dict):
                    frappe.logger().error(f"Invalid matrix data type for {question_id}: expected dict, got {type(value)}")
                    processing_errors.append(f"Invalid matrix format for {question_id}")

            except Exception as e:
                error_msg = f"Unexpected error processing question {question_id}: {str(e)}"
                frappe.logger().error(error_msg)
                processing_errors.append(error_msg)
                continue

        # ========== INSERT RESPONSE DOC FIRST ==========
        try:
            response_doc.total_score = total_score
            response_doc.insert(ignore_permissions=True)
            frappe.db.commit()
            frappe.logger().info(f"Survey response {response_doc.name} inserted successfully with score: {total_score}")
        except Exception as e:
            frappe.logger().error(f"Error inserting response document: {frappe.get_traceback()}")
            frappe.throw(f"Failed to save survey response: {str(e)}")

        # ========== INSERT SELECTIONS AFTER PARENT ==========
        selection_count = 0
        try:
            for answer_row in response_doc.answers:
                if answer_row.idx in selections_to_insert:
                    for selection_data in selections_to_insert[answer_row.idx]:
                        selection_doc = frappe.get_doc({
                            "doctype": "Survey Response Selection",
                            "parent": answer_row.name,
                            "parenttype": "Survey Response Answer",
                            "parentfield": "selections",
                            **selection_data
                        })
                        selection_doc.insert(ignore_permissions=True)
                        selection_count += 1
            
            frappe.db.commit()
            frappe.logger().info(f"Inserted {selection_count} selections successfully")
        except Exception as e:
            frappe.logger().error(f"Error inserting selections: {frappe.get_traceback()}")
            frappe.throw(f"Failed to save selections: {str(e)}")

        # ========== RETURN RESPONSE ==========
        response = {
            "status": "success",
            "message": "Thank you for your response!",
            "total_score": total_score,
            "response_id": response_doc.name
        }

        if processing_errors:
            response["status"] = "completed_with_errors"
            response["processing_errors"] = processing_errors
            frappe.logger().warning(f"Survey {survey_id} completed with {len(processing_errors)} errors")

        return response

    except frappe.ValidationError:
        raise
    except Exception as e:
        frappe.logger().error(f"Unexpected error in submit_survey: {frappe.get_traceback()}")
        frappe.throw(f"Survey submission failed: {str(e)}")
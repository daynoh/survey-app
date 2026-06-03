# your_app/your_app/report/user_scores_by_category/user_scores_by_category.py

import frappe
from frappe import _
from collections import defaultdict


def execute(filters=None):
    filters = filters or {}

    columns = get_columns()
    data = get_data(filters)

    return columns, data


def get_columns():
    return [
        {
            "label": _("Employee"),
            "fieldname": "employee",
            "fieldtype": "Link",
            "options": "Employee",
            "width": 180,
        },
        {
            "label": _("User ID"),
            "fieldname": "user_id",
            "fieldtype": "Data",
            "width": 220,
        },
        {
            "label": _("Rated By"),
            "fieldname": "rated_by",
            "fieldtype": "Link",
            "options": "User",
            "width": 180,
        },
        {
            "label": _("Survey"),
            "fieldname": "survey",
            "fieldtype": "Link",
            "options": "Survey",
            "width": 180,
        },
        {
            "label": _("Category"),
            "fieldname": "category",
            "fieldtype": "Link",
            "options": "Value Performance Categories",
            "width": 200,
        },
        {
            "label": _("Score"),
            "fieldname": "score",
            "fieldtype": "Float",
            "width": 120,
        },
        {
            "label": _("Submission Date"),
            "fieldname": "submission_date",
            "fieldtype": "Datetime",
            "width": 180,
        },
    ]


def get_data(filters):
    conditions = ""
    values = {}

    # FILTERS

    if filters.get("from_date"):
        conditions += " AND sr.submission_date >= %(from_date)s"
        values["from_date"] = filters.get("from_date")

    if filters.get("to_date"):
        conditions += " AND sr.submission_date <= %(to_date)s"
        values["to_date"] = filters.get("to_date")

    if filters.get("survey"):
        conditions += " AND sr.survey = %(survey)s"
        values["survey"] = filters.get("survey")

    if filters.get("user_id"):
        conditions += " AND emp.user_id = %(user_id)s"
        values["user_id"] = filters.get("user_id")

    # MAIN QUERY

    responses = frappe.db.sql(
        f"""
        SELECT
            sr.name AS response_name,
            sr.survey,
            sr.respondent,
            sr.submission_date,

            s.employee_score,
            s.rated_by,

            emp.user_id,

            sra.name AS answer_name,
            sra.question,
            sra.selected_option,

            vq.category

        FROM `tabSurvey Response` sr

        INNER JOIN `tabSurvey` s
            ON s.name = sr.survey

        LEFT JOIN `tabEmployee` emp
            ON emp.name = s.employee_score

        INNER JOIN `tabSurvey Response Answer` sra
            ON sra.parent = sr.name

        LEFT JOIN `tabValue Questions` vq
            ON vq.name = sra.question

        WHERE sr.docstatus < 2
        {conditions}
        """,
        values,
        as_dict=True,
    )

    data = []

    for row in responses:

        total_score = 0

        # SINGLE OPTION SCORE
        if row.selected_option:

            option_score = frappe.db.get_value(
                "Survey Question Options",
                row.selected_option,
                "score"
            )

            total_score += option_score or 0

        # MATRIX / MULTISELECT SCORES
        selections = frappe.get_all(
            "Survey Response Selection",
            filters={"parent": row.answer_name},
            fields=["score"]
        )

        for selection in selections:
            total_score += selection.score or 0

        data.append({
            "employee": row.employee_score,
            "user_id": row.user_id,
            "rated_by": row.rated_by,
            "survey": row.survey,
            "category": row.category,
            "score": total_score,
            "submission_date": row.submission_date,
        })

    return merge_scores(data)


def merge_scores(data):
    """
    Merge rows by:
    Employee + User ID + Rated By + Survey + Category
    """

    grouped_scores = defaultdict(float)
    grouped_meta = {}

    for row in data:

        key = (
            row["employee"],
            row["user_id"],
            row["rated_by"],
            row["survey"],
            row["category"],
        )

        grouped_scores[key] += row["score"]

        grouped_meta[key] = row

    output = []

    for key, score in grouped_scores.items():

        meta = grouped_meta[key]

        output.append({
            "employee": meta["employee"],
            "user_id": meta["user_id"],
            "rated_by": meta["rated_by"],
            "survey": meta["survey"],
            "category": meta["category"],
            "score": score,
            "submission_date": meta["submission_date"],
        })

    return output
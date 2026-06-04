"""
Report: User Scores By Category
Doctype: Survey Response

Schema clarifications:
  - Survey.questions          → child table: tabSurvey Questions  (sq)
                                 sq.name (docname), sq.question_name, sq.title, sq.type
  - Survey.questions          → also has child: tabValue Questions (vq)
                                 vq.parent = Survey.name
                                 vq.category (Link → Value Performance Categories)
                                 vq.question (Long Text – stores the question TEXT, not the name)

  Join strategy:
    sra.question  →  sq.name   (Survey Response Answer.question is a Link to Survey Questions)
    sq.title      →  vq.question  (Value Questions.question stores the display text = sq.title)

  This avoids the "Unknown column vq.parent" error which happened because the previous
  version tried to alias vq.parent in the ON clause before the subquery was resolved.
"""

import frappe
from frappe import _
from frappe.utils import flt, cstr


def execute(filters=None):
    filters = filters or {}
    columns = get_columns(filters)
    data    = get_data(filters)
    chart   = get_chart(data, filters)
    summary = get_report_summary(data, filters)
    return columns, data, None, chart, summary


# ---------------------------------------------------------------------------
# Columns
# ---------------------------------------------------------------------------

def get_columns(filters):
    return [
        {
            "label":     _("Employee"),
            "fieldname": "employee",
            "fieldtype": "Link",
            "options":   "Employee",
            "width":     140,
        },
        {
            "label":     _("Employee Name"),
            "fieldname": "employee_name",
            "fieldtype": "Data",
            "width":     160,
        },
        {
            "label":     _("Survey"),
            "fieldname": "survey",
            "fieldtype": "Link",
            "options":   "Survey",
            "width":     160,
        },
        {
            "label":     _("Survey Title"),
            "fieldname": "survey_title",
            "fieldtype": "Data",
            "width":     180,
        },
        {
            "label":     _("Rated By"),
            "fieldname": "rated_by",
            "fieldtype": "Link",
            "options":   "User",
            "width":     150,
        },
        {
            "label":     _("Category"),
            "fieldname": "category",
            "fieldtype": "Link",
            "options":   "Value Performance Categories",
            "width":     160,
        },
        {
            "label":     _("Total Questions"),
            "fieldname": "total_questions",
            "fieldtype": "Int",
            "width":     120,
        },
        {
            "label":     _("Total Score"),
            "fieldname": "total_score",
            "fieldtype": "Float",
            "precision": 2,
            "width":     110,
        },
        {
            "label":     _("Max Possible Score"),
            "fieldname": "max_possible_score",
            "fieldtype": "Float",
            "precision": 2,
            "width":     150,
        },
        {
            "label":     _("Score %"),
            "fieldname": "score_percentage",
            "fieldtype": "Percent",
            "width":     100,
        },
        {
            "label":     _("Responses"),
            "fieldname": "response_count",
            "fieldtype": "Int",
            "width":     100,
        },
        {
            "label":     _("Last Response"),
            "fieldname": "last_response",
            "fieldtype": "Datetime",
            "width":     160,
        },
    ]


# ---------------------------------------------------------------------------
# Main data fetch
# ---------------------------------------------------------------------------

def get_data(filters):
    conditions, values = get_conditions(filters)

    # ------------------------------------------------------------------
    # STEP 1 – Fetch all answer rows with their category
    #
    # Join path:
    #   Survey Response (sr)
    #     → Survey (s)                         ON s.name = sr.survey
    #     → Survey Response Answer (sra)       ON sra.parent = sr.name
    #     → Survey Questions (sq)              ON sq.name = sra.question
    #     → Value Questions (vq)               ON vq.parent = s.name
    #                                          AND vq.question = sq.title
    #     → Survey Question Options (sqo)      ON sqo.name = sra.selected_option  [direct pick]
    #     → max_scores subquery                ON max_scores.survey_question = sq.name
    #
    # NOTE: vq.question is Long Text that stores the question's display title (sq.title).
    # ------------------------------------------------------------------

    sql = f"""
SELECT
    sr.name                    AS response_name,
    sr.survey                  AS survey,
    s.title                    AS survey_title,
    s.employee_score           AS employee,
    s.rated_by                AS rated_by,
    sr.respondent              AS respondent,
    sr.submission_date        AS submission_date,

    sra.name                  AS answer_name,
    sra.question              AS question,
    sra.question_type         AS question_type,

    srs.row_option           AS row_option,
    srs.column_option        AS column_option,
    srs.score                AS selection_score,

    row_opt.option_label     AS competency_question,

    vq.category              AS category,

    col_opt.score            AS column_score,

    max_scores.max_score_per_row

FROM `tabSurvey Response` sr
INNER JOIN `tabSurvey` s
    ON s.name = sr.survey

INNER JOIN `tabSurvey Response Answer` sra
    ON sra.parent = sr.name

-- 🔴 IMPORTANT: keep selection join
INNER JOIN `tabSurvey Response Selection` srs
    ON srs.parent = sra.name

LEFT JOIN `tabSurvey Question Options` row_opt
    ON row_opt.name = srs.row_option

LEFT JOIN `tabValue Questions` vq
    ON vq.question = row_opt.option_label

LEFT JOIN `tabSurvey Question Options` col_opt
    ON col_opt.name = srs.column_option

LEFT JOIN (
    SELECT
        parent,
        MAX(score) AS max_score_per_row
    FROM `tabSurvey Question Options`
    WHERE dimension_type = 'column'
    GROUP BY parent
) max_scores
    ON max_scores.parent = sra.question

WHERE {conditions}

ORDER BY
    s.employee_score,
    vq.category,
    sr.submission_date
"""

    raw_rows = frappe.db.sql(sql, values, as_dict=True)

    if not raw_rows:
        return []


    # ------------------------------------------------------------------
    # STEP 3 – Aggregate by (employee, survey, rated_by, category)
    # ------------------------------------------------------------------
    aggregation = {}

    for row in raw_rows:

        category = row.category or "Uncategorised"

        key = (
            cstr(row.employee),
            cstr(row.survey),
            cstr(row.rated_by),
            cstr(category),
        )

        if key not in aggregation:
            aggregation[key] = {
                "employee": row.employee,
                "employee_name": "",
                "survey": row.survey,
                "survey_title": row.survey_title,
                "rated_by": row.rated_by,
                "category": category,
                "total_score": 0.0,
                "max_possible_score": 0.0,
                "total_questions": 0,
                "response_names": set(),
                "competencies": set(),
                "last_response": row.submission_date,
            }

        bucket = aggregation[key]

        bucket["response_names"].add(row.response_name)

        competency = row.competency_question

        if competency and competency not in bucket["competencies"]:
            bucket["competencies"].add(competency)

            bucket["total_questions"] += 1

            bucket["max_possible_score"] += flt(
                row.max_score_per_row
            )

        bucket["total_score"] += flt(
            row.column_score or row.selection_score or 0
        )

        if (
            row.submission_date
            and row.submission_date > bucket["last_response"]
        ):
            bucket["last_response"] = row.submission_date

    # ------------------------------------------------------------------
    # STEP 4 – Resolve employee names in one query
    # ------------------------------------------------------------------
    employee_ids = list({v["employee"] for v in aggregation.values() if v["employee"]})
    employee_name_map = {}
    if employee_ids:
        emp_rows = frappe.get_all(
            "Employee",
            filters={"name": ["in", employee_ids]},
            fields=["name", "employee_name"],
        )
        employee_name_map = {e.name: e.employee_name for e in emp_rows}

    # ------------------------------------------------------------------
    # STEP 5 – Build output rows
    # ------------------------------------------------------------------
    data = []
    for bucket in aggregation.values():
        emp       = bucket["employee"]
        max_score = flt(bucket["max_possible_score"])
        total     = flt(bucket["total_score"])
        pct       = round((total / max_score * 100) if max_score else 0.0, 2)

        data.append({
            "employee":           emp,
            "employee_name":      employee_name_map.get(emp, ""),
            "survey":             bucket["survey"],
            "survey_title":       bucket["survey_title"],
            "rated_by":           bucket["rated_by"],
            "category":           bucket["category"],
            "total_questions":    bucket["total_questions"],
            "total_score":        round(total, 2),
            "max_possible_score": round(max_score, 2),
            "score_percentage":   pct,
            "response_count":     len(bucket["response_names"]),
            "last_response":      bucket["last_response"],
        })

    data.sort(key=lambda r: (cstr(r["employee"]), cstr(r["category"])))
    return data


# ---------------------------------------------------------------------------
# Condition builder
# ---------------------------------------------------------------------------

def get_conditions(filters):
    conditions = ["sr.docstatus < 2"]
    values     = {}

    if filters.get("from_date"):
        conditions.append("sr.submission_date >= %(from_date)s")
        values["from_date"] = filters["from_date"]

    if filters.get("to_date"):
        # Include the entire to_date day
        conditions.append("DATE(sr.submission_date) <= %(to_date)s")
        values["to_date"] = filters["to_date"]

    if filters.get("survey"):
        conditions.append("sr.survey = %(survey)s")
        values["survey"] = filters["survey"]

    if filters.get("employee"):
        conditions.append("s.employee_score = %(employee)s")
        values["employee"] = filters["employee"]

    if filters.get("rated_by"):
        conditions.append("s.rated_by = %(rated_by)s")
        values["rated_by"] = filters["rated_by"]

    if filters.get("category"):
        conditions.append("vq.category = %(category)s")
        values["category"] = filters["category"]

    return " AND ".join(conditions), values


# ---------------------------------------------------------------------------
# Chart – average score % per category (bar)
# ---------------------------------------------------------------------------

def get_chart(data, filters):
    if not data:
        return None

    cat_map = {}
    for row in data:
        cat = row.get("category") or "Uncategorised"
        if cat not in cat_map:
            cat_map[cat] = {"total": 0.0, "count": 0}
        cat_map[cat]["total"] += flt(row["score_percentage"])
        cat_map[cat]["count"] += 1

    labels = sorted(cat_map.keys())
    values = [
        round(cat_map[c]["total"] / cat_map[c]["count"], 2)
        for c in labels
    ]

    return {
        "data": {
            "labels":   labels,
            "datasets": [{"name": _("Avg Score %"), "values": values}],
        },
        "type":      "bar",
        "fieldtype": "Percent",
        "colors":    ["#5E64FF"],
    }


# ---------------------------------------------------------------------------
# Report summary cards
# ---------------------------------------------------------------------------

def get_report_summary(data, filters):
    if not data:
        return None

    total_responses   = sum(r["response_count"]     for r in data)
    total_score_sum   = sum(r["total_score"]         for r in data)
    total_max_sum     = sum(r["max_possible_score"]  for r in data)
    overall_pct       = round((total_score_sum / total_max_sum * 100) if total_max_sum else 0.0, 2)
    unique_employees  = len({r["employee"] for r in data if r["employee"]})
    unique_categories = len({r["category"] for r in data if r["category"]})

    return [
        {
            "value":     unique_employees,
            "label":     _("Employees Rated"),
            "datatype":  "Int",
            "indicator": "blue",
        },
        {
            "value":     unique_categories,
            "label":     _("Categories"),
            "datatype":  "Int",
            "indicator": "blue",
        },
        {
            "value":     total_responses,
            "label":     _("Total Responses"),
            "datatype":  "Int",
            "indicator": "blue",
        },
        {
            "value":     overall_pct,
            "label":     _("Overall Score %"),
            "datatype":  "Percent",
            "indicator": (
                "green"  if overall_pct >= 70 else
                "orange" if overall_pct >= 50 else
                "red"
            ),
        },
    ]
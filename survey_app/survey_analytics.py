import frappe
from frappe.utils import flt, cstr
from datetime import datetime, timedelta


@frappe.whitelist()
def test_page_load():
    doc = frappe.get_doc("Page", "survey-analytics")
    doc.load_assets()
    return {"script_len": len(doc.script or ""), "module": doc.module}


@frappe.whitelist()
def test_setup_page():
    doc = frappe.get_doc("Page", "survey-setup")
    doc.load_assets()
    slen = len(doc.script or "")
    preview = (doc.script or "")[:200]
    return {"script_len": slen, "module": doc.module, "preview": preview}


@frappe.whitelist()
def test_filters():
    import json
    return get_analytics({"department": "HR - A"})


@frappe.whitelist()
def get_analytics(filters=None):
    if isinstance(filters, str):
        import json
        filters = json.loads(filters)
    filters = filters or {}

    conditions, values = build_conditions(filters)
    raw = get_raw_data(conditions, values)

    if not raw:
        return {
            "summary": [],
            "insights": {},
            "by_employee": {"labels": [], "values": []},
            "by_category": {"labels": [], "values": []},
            "by_department": {"labels": [], "values": []},
            "over_time": {"labels": [], "responses": [], "avg_score": []},
            "reviewer_activity": {"labels": [], "values": []},
            "detail": [],
        }

    # Aggregate
    aggregated = aggregate_data(raw)
    detail = build_detail(aggregated, raw)

    return {
        "summary": build_summary(aggregated, filters),
        "insights": build_insights(aggregated),
        "by_employee": build_by_employee(aggregated),
        "by_category": build_by_category(aggregated),
        "by_department": build_by_department(aggregated),
        "over_time": build_over_time(raw),
        "reviewer_activity": build_reviewer_activity(aggregated, raw),
        "detail": detail,
    }


def build_conditions(filters):
    conditions = ["sr.docstatus < 2"]
    values = {}

    if filters.get("from_date"):
        conditions.append("sr.submission_date >= %(from_date)s")
        values["from_date"] = filters["from_date"]
    if filters.get("to_date"):
        conditions.append("DATE(sr.submission_date) <= %(to_date)s")
        values["to_date"] = filters["to_date"]
    if filters.get("department"):
        conditions.append("emp.department = %(department)s")
        values["department"] = filters["department"]
    if filters.get("employee"):
        conditions.append("s.employee_score = %(employee)s")
        values["employee"] = filters["employee"]
    if filters.get("category"):
        conditions.append("vq.category = %(category)s")
        values["category"] = filters["category"]
    if filters.get("survey"):
        conditions.append("sr.survey = %(survey)s")
        values["survey"] = filters["survey"]

    return " AND ".join(conditions), values


def get_raw_data(conditions, values):
    sql = f"""
SELECT
    sr.name AS response_name,
    sr.survey,
    s.title AS survey_title,
    s.employee_score AS employee,
    s.rated_by,
    sr.submission_date,
    srs.row_option,
    srs.column_option,
    srs.score AS selection_score,
    row_opt.option_label AS competency_question,
    vq.category,
    col_opt.score AS column_score,
    col_opt.option_label AS rating_label,
    sra.question AS question_id,
    emp.department AS employee_department,
    emp.employee_name AS employee_name_raw
FROM `tabSurvey Response` sr
INNER JOIN `tabSurvey` s ON s.name = sr.survey
INNER JOIN `tabSurvey Response Answer` sra ON sra.parent = sr.name
INNER JOIN `tabSurvey Response Selection` srs ON srs.parent = sra.name
LEFT JOIN `tabSurvey Question Options` row_opt ON row_opt.name = srs.row_option
LEFT JOIN `tabValue Questions` vq ON vq.question = row_opt.option_label
LEFT JOIN `tabSurvey Question Options` col_opt ON col_opt.name = srs.column_option
LEFT JOIN `tabEmployee` emp ON emp.name = s.employee_score
WHERE {conditions}
ORDER BY sr.submission_date
"""
    return frappe.db.sql(sql, values, as_dict=True)


def aggregate_data(raw):
    MAX_PER_ROW = 5

    employees = {}
    for row in raw:
        emp = cstr(row.employee)
        cat = row.category or "Uncategorized"

        if emp not in employees:
            employees[emp] = {
                "employee": emp,
                "employee_name": row.employee_name_raw or emp,
                "department": row.employee_department or "No Department",
                "scores": 0.0,
                "max_scores": 0.0,
                "count": 0,
                "response_ids": set(),
                "categories": {},
                "by_rated_by": {},
            }

        e = employees[emp]
        e["count"] += 1
        e["response_ids"].add(row.response_name)
        e["scores"] += flt(row.column_score or row.selection_score or 0)
        e["max_scores"] += MAX_PER_ROW

        if cat not in e["categories"]:
            e["categories"][cat] = {"scores": 0.0, "count": 0, "max_scores": 0.0}
        e["categories"][cat]["scores"] += flt(row.column_score or row.selection_score or 0)
        e["categories"][cat]["count"] += 1
        e["categories"][cat]["max_scores"] += MAX_PER_ROW

        rater = row.rated_by or "Unknown"
        if rater not in e["by_rated_by"]:
            e["by_rated_by"][rater] = {"scores": 0.0, "count": 0}
        e["by_rated_by"][rater]["scores"] += flt(row.column_score or row.selection_score or 0)
        e["by_rated_by"][rater]["count"] += 1

    return employees


def build_summary(aggregated, filters=None):
    filters = filters or {}
    total_emp = len(aggregated)
    total_responses = sum(len(e["response_ids"]) for e in aggregated.values())
    total_score = sum(e["scores"] for e in aggregated.values())
    total_max = sum(e["max_scores"] for e in aggregated.values())
    departments = {e.get("department") or "No Department" for e in aggregated.values()}

    avg_pct = round((total_score / total_max * 100), 1) if total_max else 0

    # Open surveys in period (for completion context)
    survey_filters = {"docstatus": ["<", 2]}
    open_surveys = frappe.db.count("Survey", survey_filters) or 0
    completion_rate = round((total_responses / open_surveys * 100), 1) if open_surveys else 0

    return [
        {
            "value": total_emp,
            "label": "Employees Reviewed",
            "sublabel": f"{len(departments)} department(s)",
            "indicator": "navy",
        },
        {
            "value": total_responses,
            "label": "Feedback Received",
            "sublabel": f"{open_surveys} surveys issued" if open_surveys else "Responses in period",
            "indicator": "teal",
        },
        {
            "value": avg_pct,
            "label": "Organisation Score",
            "sublabel": "Average across all ratings",
            "indicator": "green" if avg_pct >= 70 else "amber" if avg_pct >= 50 else "red",
            "datatype": "Percent",
        },
        {
            "value": completion_rate,
            "label": "Completion Rate",
            "sublabel": "Responses vs surveys issued",
            "indicator": "green" if completion_rate >= 70 else "amber" if completion_rate >= 40 else "red",
            "datatype": "Percent",
        },
    ]


def build_insights(aggregated):
    if not aggregated:
        return {}

    scored = []
    for emp, e in aggregated.items():
        pct = round(e["scores"] / e["max_scores"] * 100, 1) if e["max_scores"] else 0
        scored.append({
            "employee": emp,
            "employee_name": e.get("employee_name") or emp,
            "department": e.get("department") or "No Department",
            "score_pct": pct,
            "responses": len(e.get("response_ids") or []),
        })
    scored.sort(key=lambda x: x["score_pct"], reverse=True)

    cat_map = {}
    for e in aggregated.values():
        for cat, cd in e["categories"].items():
            if cat not in cat_map:
                cat_map[cat] = {"scores": 0.0, "max_scores": 0.0}
            cat_map[cat]["scores"] += cd["scores"]
            cat_map[cat]["max_scores"] += cd["max_scores"]

    cat_scored = []
    for cat, cd in cat_map.items():
        pct = round(cd["scores"] / cd["max_scores"] * 100, 1) if cd["max_scores"] else 0
        cat_scored.append({"category": cat, "score_pct": pct})
    cat_scored.sort(key=lambda x: x["score_pct"], reverse=True)

    top = scored[0] if scored else None
    bottom = scored[-1] if scored and len(scored) > 1 else None
    strong_cat = cat_scored[0] if cat_scored else None
    weak_cat = cat_scored[-1] if cat_scored and len(cat_scored) > 1 else None

    return {
        "top_performer": top,
        "needs_attention": bottom if bottom and top and bottom["employee"] != top["employee"] else None,
        "strongest_category": strong_cat,
        "development_focus": weak_cat if weak_cat and strong_cat and weak_cat["category"] != strong_cat["category"] else None,
        "high_performers": [s for s in scored if s["score_pct"] >= 80][:5],
        "at_risk": [s for s in scored if s["score_pct"] < 50][:5],
    }


def build_by_employee(aggregated):
    rows = []
    for emp, e in aggregated.items():
        pct = round(e["scores"] / e["max_scores"] * 100, 1) if e["max_scores"] else 0
        rows.append({
            "employee": emp,
            "employee_name": e.get("employee_name", emp),
            "department": e.get("department") or "No Department",
            "score_pct": pct,
        })
    rows.sort(key=lambda x: x["score_pct"], reverse=True)

    return {
        "labels": [r["employee_name"] for r in rows],
        "values": [r["score_pct"] for r in rows],
        "rows": rows,
        "total": len(rows),
        "title": "Score % by Employee",
    }


def build_by_category(aggregated):
    cat_map = {}
    for e in aggregated.values():
        for cat, cd in e["categories"].items():
            if cat not in cat_map:
                cat_map[cat] = {"scores": 0.0, "max_scores": 0.0, "count": 0}
            cat_map[cat]["scores"] += cd["scores"]
            cat_map[cat]["max_scores"] += cd["max_scores"]
            cat_map[cat]["count"] += cd["count"]

    labels = []
    values = []
    for cat in sorted(cat_map.keys()):
        cd = cat_map[cat]
        pct = round(cd["scores"] / cd["max_scores"] * 100, 1) if cd["max_scores"] else 0
        labels.append(cat)
        values.append(pct)

    return {
        "labels": labels,
        "values": values,
        "title": "Avg Score % by Category",
    }


def build_by_department(aggregated):
    dept_map = {}
    for e in aggregated.values():
        dept = e.get("department", "No Department")
        if dept not in dept_map:
            dept_map[dept] = {"scores": 0.0, "max_scores": 0.0, "count": 0}
        dept_map[dept]["scores"] += e["scores"]
        dept_map[dept]["max_scores"] += e["max_scores"]
        dept_map[dept]["count"] += 1

    labels = []
    values = []
    for dept in sorted(dept_map.keys()):
        dd = dept_map[dept]
        pct = round(dd["scores"] / dd["max_scores"] * 100, 1) if dd["max_scores"] else 0
        labels.append(dept)
        values.append(pct)

    return {
        "labels": labels,
        "values": values,
        "title": "Avg Score % by Department",
    }


def build_over_time(raw):
    monthly = {}
    for row in raw:
        if row.submission_date:
            month = row.submission_date.strftime("%Y-%m")
            if month not in monthly:
                monthly[month] = {"count": 0, "scores": 0.0}
            monthly[month]["count"] += 1
            monthly[month]["scores"] += flt(row.column_score or row.selection_score or 0)

    months = sorted(monthly.keys())
    return {
        "labels": months,
        "responses": [monthly[m]["count"] for m in months],
        "avg_score": [round(monthly[m]["scores"] / monthly[m]["count"], 1) if monthly[m]["count"] else 0 for m in months],
        "title": "Responses Over Time",
    }


def build_reviewer_activity(aggregated, raw):
    rater_map = {}
    for row in raw:
        rater = row.rated_by or "Unknown"
        if rater not in rater_map:
            rater_map[rater] = 0
        rater_map[rater] += 1

    sorted_raters = sorted(rater_map.items(), key=lambda x: x[1], reverse=True)
    return {
        "labels": [r[0] for r in sorted_raters],
        "values": [r[1] for r in sorted_raters],
        "title": "Reviews Completed by Rater",
    }


def build_detail(aggregated, raw):
    detail = []
    seen = set()
    for row in raw:
        key = (row.employee, row.rated_by, row.category, row.survey)
        if key in seen:
            continue
        seen.add(key)

        emp = row.employee
        e = aggregated.get(emp, {})
        cat = row.category or "Uncategorized"
        cat_data = e.get("categories", {}).get(cat, {})

        detail.append({
            "employee": emp,
            "employee_name": e.get("employee_name", emp),
            "department": e.get("department", ""),
            "rated_by": row.rated_by,
            "category": cat,
            "survey": row.survey,
            "survey_title": row.survey_title,
            "score": round(cat_data.get("scores", 0), 1),
            "score_pct": round(cat_data["scores"] / cat_data["max_scores"] * 100, 1) if cat_data.get("max_scores") else 0,
            "responses": len(e.get("response_ids", set())),
            "last_response": row.submission_date.strftime("%Y-%m-%d %H:%M") if row.submission_date else "",
        })

    return sorted(detail, key=lambda x: x["score_pct"], reverse=True)

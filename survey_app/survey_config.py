import frappe
from frappe.utils import now


@frappe.whitelist()
def get_config_data():
    categories = frappe.get_all(
        "Value Performance Categories",
        fields=["name"],
        order_by="name"
    )

    cat_data = []
    for cat in categories:
        questions = frappe.get_all(
            "Value Questions",
            filters={"category": cat.name},
            fields=["name", "question"]
        )
        cat_data.append({
            "name": cat.name,
            "question_count": len(questions),
            "questions": questions
        })

    nearness_factors = frappe.get_all(
        "Departmental Nearness Factor",
        fields=["name", "department", "department2", "factor"]
    )

    settings = {}
    if frappe.db.exists("Value Scoring Settings", "Value Scoring Settings"):
        doc = frappe.get_doc("Value Scoring Settings", "Value Scoring Settings")
        settings = {
            "questions_per_category": doc.questions_per_category,
            "max_surveys_per_employee": doc.max_surveys_per_employee,
            "max_surveys_per_reviewer": doc.max_surveys_per_reviewer,
            "exclude_rated": [{"user": d.user} for d in doc.exclude_rated],
            "exclude_rating": [{"user": d.user} for d in doc.exclude_rating],
            "enable_scheduled_generation": doc.enable_scheduled_generation or 0,
            "generation_frequency": doc.generation_frequency or "",
            "last_generation_date": str(doc.last_generation_date or ""),
        }

    departments = frappe.get_all("Department", fields=["name"], order_by="name")

    generation_trail = []
    if frappe.db.exists("DocType", "Survey Generation Log"):
        generation_trail = get_generation_trail(limit=10).get("logs") or []

    return {
        "categories": cat_data,
        "nearness_factors": nearness_factors,
        "settings": settings,
        "departments": departments,
        "generation_trail": generation_trail,
    }


@frappe.whitelist()
def save_category(name):
    if isinstance(name, dict):
        name = name.get("value") or name.get("name") or ""
    name = (name or "").strip()
    if not name:
        frappe.throw("Category name is required")

    if frappe.db.exists("Value Performance Categories", name):
        return {"status": "exists", "message": "Category already exists"}

    doc = frappe.get_doc({"doctype": "Value Performance Categories", "name1": name})
    doc.insert(ignore_permissions=True)
    return {"status": "created", "name": doc.name}


@frappe.whitelist()
def delete_category(name):
    if not frappe.db.exists("Value Performance Categories", name):
        frappe.throw("Category not found")

    frappe.db.delete("Value Questions", {"category": name})

    frappe.delete_doc("Value Performance Categories", name, ignore_permissions=True)
    return {"status": "deleted"}


@frappe.whitelist()
def save_question(category, question_text):
    if isinstance(question_text, dict):
        question_text = question_text.get("value") or question_text.get("question") or ""
    if not frappe.db.exists("Value Performance Categories", category):
        frappe.throw("Category does not exist")

    question_text = (question_text or "").strip()
    if not question_text:
        frappe.throw("Question text is required")

    doc = frappe.get_doc({
        "doctype": "Value Questions",
        "category": category,
        "question": question_text
    })
    doc.insert(ignore_permissions=True)
    return {"status": "created", "name": doc.name, "question": question_text}


@frappe.whitelist()
def delete_question(name):
    if not frappe.db.exists("Value Questions", name):
        frappe.throw("Question not found")

    frappe.delete_doc("Value Questions", name, ignore_permissions=True)
    return {"status": "deleted"}


@frappe.whitelist()
def save_nearness_factor(department, department2, factor):
    factor = float(factor)
    if factor < 0:
        frappe.throw("Factor must be a positive number")

    existing = frappe.db.exists(
        "Departmental Nearness Factor",
        {"department": department, "department2": department2}
    )

    if existing:
        doc = frappe.get_doc("Departmental Nearness Factor", existing)
        doc.factor = factor
        doc.save(ignore_permissions=True)
        return {"status": "updated", "name": doc.name}
    else:
        doc = frappe.get_doc({
            "doctype": "Departmental Nearness Factor",
            "department": department,
            "department2": department2,
            "factor": factor
        })
        doc.insert(ignore_permissions=True)
    return {"status": "created", "name": doc.name}


@frappe.whitelist()
def create_users():
    users_to_create = [
        {"email": "musingiladennis@gmail.com", "first_name": "Musingila", "last_name": "Dennis"},
        {"email": "justdaynoh8@gmail.com", "first_name": "Justine", "last_name": "Daynoh"},
        {"email": "dennis.musingila@actserv-africa.com", "first_name": "Dennis", "last_name": "Musingila"},
    ]

    results = []

    for u in users_to_create:
        if frappe.db.exists("User", u["email"]):
            results.append({"email": u["email"], "status": "exists"})
            continue

        doc = frappe.get_doc({
            "doctype": "User",
            "email": u["email"],
            "first_name": u["first_name"],
            "last_name": u["last_name"],
            "full_name": f"{u['first_name']} {u['last_name']}",
            "enabled": 1,
            "send_welcome_email": 0,
            "roles": [{"role": "Employee Self Service"}],
        })
        doc.flags.in_fixtures = True
        doc.insert(ignore_permissions=True)
        frappe.db.commit()
        results.append({"email": u["email"], "status": "created", "name": doc.name})

    return {"users": results}


@frappe.whitelist()
def create_employees():
    user_emp_map = [
        {"email": "musingiladennis@gmail.com", "first_name": "Musingila", "last_name": "Dennis", "department": "Engineering - A"},
        {"email": "justdaynoh8@gmail.com", "first_name": "Justine", "last_name": "Daynoh", "department": "HR - A"},
        {"email": "dennis.musingila@actserv-africa.com", "first_name": "Dennis", "last_name": "Musingila", "department": "Finance - A"},
    ]

    results = []

    for emp in user_emp_map:
        if not frappe.db.exists("User", emp["email"]):
            results.append({"email": emp["email"], "status": "no_user"})
            continue

        existing = frappe.db.exists("Employee", {"user_id": emp["email"]})
        if existing:
            results.append({"email": emp["email"], "status": "employee_exists"})
            continue

        doc = frappe.get_doc({
            "doctype": "Employee",
            "first_name": emp["first_name"],
            "last_name": emp["last_name"],
            "user_id": emp["email"],
            "department": emp["department"],
            "status": "Active",
            "gender": "Male",
            "date_of_birth": "1995-01-01",
            "date_of_joining": "2026-07-01",
            "employment_type": "Full-time",
        })
        doc.flags.in_fixtures = True
        doc.insert(ignore_permissions=True)
        frappe.db.commit()
        results.append({"email": emp["email"], "status": "created", "employee": doc.name})

    return {"employees": results}


@frappe.whitelist()
def delete_nearness_factor(name):
    if not frappe.db.exists("Departmental Nearness Factor", name):
        frappe.throw("Nearness factor not found")
    frappe.delete_doc("Departmental Nearness Factor", name, ignore_permissions=True)
    return {"status": "deleted"}


@frappe.whitelist()
def save_scoring_settings(settings_data):
    if isinstance(settings_data, str):
        import json
        settings_data = json.loads(settings_data)

    if not frappe.db.exists("Value Scoring Settings", "Value Scoring Settings"):
        doc = frappe.get_doc({"doctype": "Value Scoring Settings"})
    else:
        doc = frappe.get_doc("Value Scoring Settings", "Value Scoring Settings")

    doc.questions_per_category = settings_data.get("questions_per_category") or 3
    doc.max_surveys_per_employee = settings_data.get("max_surveys_per_employee") or 10
    doc.max_surveys_per_reviewer = settings_data.get("max_surveys_per_reviewer") or 10

    doc.exclude_rated = []
    if settings_data.get("exclude_rated"):
        for entry in settings_data["exclude_rated"]:
            doc.append("exclude_rated", {"user": entry.get("user")})

    doc.exclude_rating = []
    if settings_data.get("exclude_rating"):
        for entry in settings_data["exclude_rating"]:
            doc.append("exclude_rating", {"user": entry.get("user")})

    doc.enable_scheduled_generation = settings_data.get("enable_scheduled_generation") or 0
    doc.generation_frequency = settings_data.get("generation_frequency") or ""
    if settings_data.get("last_generation_date"):
        doc.last_generation_date = settings_data["last_generation_date"]

    doc.save(ignore_permissions=True)
    return {"status": "saved"}


@frappe.whitelist()
def preview_surveys():
    if frappe.db.exists("Value Scoring Settings", "Value Scoring Settings"):
        settings = frappe.get_doc("Value Scoring Settings")
        max_reviewer_cap = settings.max_surveys_per_reviewer or 10
        max_employee_cap = settings.max_surveys_per_employee or 10
    else:
        max_reviewer_cap = 10
        max_employee_cap = 10

    employees = frappe.get_all(
        "Employee",
        filters={"status": "Active"},
        fields=["name", "employee_name", "department"]
    )

    nearness_records = frappe.get_all(
        "Departmental Nearness Factor",
        fields=["department", "department2", "factor"]
    )

    nearness_map = {}
    for nf in nearness_records:
        key = (nf.department, nf.department2)
        nearness_map[key] = nf.factor

    by_department = {}
    for emp in employees:
        dept = emp.department or "No Department"
        if dept not in by_department:
            by_department[dept] = {"count": 0, "employees": []}
        by_department[dept]["count"] += 1
        by_department[dept]["employees"].append(emp.employee_name)

    total_surveys = len(employees) * min(max_employee_cap, len(employees) - 1 if len(employees) > 1 else 0)

    return {
        "total_employees": len(employees),
        "estimated_surveys": total_surveys,
        "caps": {
            "per_reviewer": max_reviewer_cap,
            "per_employee": max_employee_cap
        },
        "by_department": by_department,
        "nearness_factors_count": len(nearness_records)
    }


@frappe.whitelist()
def get_generation_trail(limit=20):
    """Return recent automatic/manual survey generation runs with recipients."""
    limit = min(cint_safe(limit, 20), 100)

    if not frappe.db.exists("DocType", "Survey Generation Log"):
        return {"logs": []}

    logs = frappe.get_all(
        "Survey Generation Log",
        fields=[
            "name",
            "triggered_at",
            "trigger_source",
            "frequency",
            "status",
            "surveys_created",
            "emails_sent",
            "summary",
            "error_message",
        ],
        order_by="triggered_at desc",
        limit_page_length=limit,
    )

    trail = []
    for log in logs:
        details = frappe.get_all(
            "Survey Generation Detail",
            filters={"parent": log.name, "parenttype": "Survey Generation Log"},
            fields=[
                "survey",
                "reviewer",
                "reviewer_name",
                "reviewer_email",
                "reviewee",
                "reviewee_name",
                "task",
                "email_sent",
            ],
            order_by="idx asc",
        )
        trail.append({
            **log,
            "triggered_at": str(log.triggered_at or ""),
            "details": details,
        })

    return {"logs": trail}


def cint_safe(val, default=0):
    from frappe.utils import cint
    try:
        return cint(val) if val is not None else default
    except Exception:
        return default


@frappe.whitelist()
def get_dashboard_stats():
    total_surveys = frappe.db.count("Survey")
    total_responses = frappe.db.count("Survey Response")

    pending = total_surveys - total_responses
    completion_rate = round((total_responses / total_surveys * 100), 1) if total_surveys > 0 else 0

    categories_count = frappe.db.count("Value Performance Categories")
    questions_count = frappe.db.count("Value Questions")
    employees_count = frappe.db.count("Employee", {"status": "Active"})

    top_scores = frappe.db.sql("""
        SELECT
            sr.survey,
            s.employee_score,
            sr.total_score,
            s.title
        FROM `tabSurvey Response` sr
        JOIN `tabSurvey` s ON sr.survey = s.name
        WHERE sr.total_score > 0
        ORDER BY sr.total_score DESC
        LIMIT 5
    """, as_dict=True)

    return {
        "total_surveys": total_surveys,
        "total_responses": total_responses,
        "pending": pending,
        "completion_rate": completion_rate,
        "categories_count": categories_count,
        "questions_count": questions_count,
        "employees_count": employees_count,
        "top_scores": top_scores
    }


@frappe.whitelist()
def install_workspace():
    import json
    import os

    base = os.path.dirname(__file__)

    # Ensure standard pages exist
    for page_name, rel_path in (
        ("survey-analytics", os.path.join("survey_app", "page", "survey_analytics", "survey_analytics.json")),
        ("outstanding-surveys", os.path.join("survey_app", "page", "outstanding_surveys", "outstanding_surveys.json")),
    ):
        page_json_path = os.path.join(base, rel_path)
        if os.path.exists(page_json_path) and not frappe.db.exists("Page", page_name):
            with open(page_json_path) as f:
                page_data = json.load(f)
            page_doc = frappe.get_doc(page_data)
            page_doc.flags.in_fixtures = True
            page_doc.insert(ignore_permissions=True)
            frappe.db.commit()

    ws_path = os.path.join(
        base, "survey_app", "workspace", "survey-administration", "survey_administration.json"
    )

    if not os.path.exists(ws_path):
        return {"status": "error", "message": "Workspace JSON not found"}

    if frappe.db.exists("Workspace", "Survey Administration"):
        frappe.delete_doc("Workspace", "Survey Administration", ignore_permissions=True)
        frappe.db.commit()

    with open(ws_path) as f:
        data = json.load(f)

    data["roles"] = [{"role": "System Manager"}, {"role": "HR Manager"}]
    data["public"] = 1
    data["is_hidden"] = 0

    doc = frappe.get_doc(data)
    doc.flags.in_fixtures = True
    doc.insert(ignore_permissions=True)
    frappe.db.commit()

    return {"status": "created", "name": doc.name}

@frappe.whitelist()
def test_auto_generation():
    """Test auto-generation: enable scheduling, run, then disable (temporary test)"""
    settings = frappe.get_doc("Value Scoring Settings")
    
    # Save original state
    orig_enabled = settings.enable_scheduled_generation
    orig_freq = settings.generation_frequency
    orig_last = settings.last_generation_date
    
    # Enable and set frequency
    settings.enable_scheduled_generation = 1
    settings.generation_frequency = "Monthly"
    settings.save(ignore_permissions=True)
    frappe.db.commit()
    
    # Run
    from survey_app.surveys import auto_generate_if_due
    result = auto_generate_if_due()
    
    # Check email queue
    emails = frappe.db.sql("SELECT status, count(*) FROM `tabEmail Queue` GROUP BY status")
    
    # Count generated surveys
    survey_count = frappe.db.count("Survey", {"docstatus": 0})
    
    # Restore original state
    settings = frappe.get_doc("Value Scoring Settings")
    settings.enable_scheduled_generation = orig_enabled
    settings.generation_frequency = orig_freq
    settings.last_generation_date = orig_last
    settings.save(ignore_permissions=True)
    frappe.db.commit()
    
    return {
        "auto_gen_result": result,
        "email_queue_status": emails,
        "total_surveys": survey_count,
        "settings_restored": True
    }

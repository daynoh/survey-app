import frappe
from html import escape
from frappe.utils import now

from survey_app.permissions import survey_admin_required
from survey_app.surveys import sample_360_question_sections


@frappe.whitelist()
@survey_admin_required
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
            "balanced_reviews_per_employee": getattr(doc, "balanced_reviews_per_employee", None) or 6,
            "balanced_max_surveys_per_reviewer": getattr(doc, "balanced_max_surveys_per_reviewer", None) or 10,
            "max_surveys_per_employee": doc.max_surveys_per_employee,
            "min_surveys_per_batch": getattr(doc, "min_surveys_per_batch", None) or 3,
            "max_surveys_per_reviewer": doc.max_surveys_per_reviewer,
            "exclude_rated": [{"user": d.user} for d in doc.exclude_rated],
            "exclude_rating": [{"user": d.user} for d in doc.exclude_rating],
            "enable_scheduled_generation": doc.enable_scheduled_generation or 0,
            "generation_frequency": doc.generation_frequency or "",
            "last_generation_date": str(doc.last_generation_date or ""),
            "generation_mode": getattr(doc, "generation_mode", None) or "Cycle Matrix",
            "role_resolution_mode": getattr(doc, "role_resolution_mode", None) or "Hybrid",
            "md_employee": getattr(doc, "md_employee", None) or "",
            "team_leader_designations": getattr(doc, "team_leader_designations", None) or "",
            "team_leaders": [
                {
                    "department": d.department,
                    "employee": d.employee,
                    "employee_name": d.employee_name,
                }
                for d in (getattr(doc, "team_leaders", None) or [])
            ],
            "exco_oversight": [
                {
                    "department": d.department,
                    "employee": d.employee,
                    "employee_name": d.employee_name,
                }
                for d in (getattr(doc, "exco_oversight", None) or [])
            ],
            "completeness_cycle": getattr(doc, "completeness_cycle", None) or "Quarterly",
            "enable_scheduled_reports": getattr(doc, "enable_scheduled_reports", None) or 0,
            "report_frequency": getattr(doc, "report_frequency", None) or "",
            "min_completion_pct_for_final_report": getattr(doc, "min_completion_pct_for_final_report", None) or 90,
            "cc_team_leader_on_report": getattr(doc, "cc_team_leader_on_report", None) or 0,
            "cc_hr_on_report": getattr(doc, "cc_hr_on_report", None) or 0,
            "last_report_date": str(getattr(doc, "last_report_date", None) or ""),
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
@survey_admin_required
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
@survey_admin_required
def delete_category(name):
    if not frappe.db.exists("Value Performance Categories", name):
        frappe.throw("Category not found")

    frappe.db.delete("Value Questions", {"category": name})

    frappe.delete_doc("Value Performance Categories", name, ignore_permissions=True)
    return {"status": "deleted"}


@frappe.whitelist()
@survey_admin_required
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
@survey_admin_required
def delete_question(name):
    if not frappe.db.exists("Value Questions", name):
        frappe.throw("Question not found")

    frappe.delete_doc("Value Questions", name, ignore_permissions=True)
    return {"status": "deleted"}


@frappe.whitelist()
@survey_admin_required
def save_nearness_factor(department, department2, factor):
    factor = float(factor)
    if factor < 0:
        frappe.throw("Factor must be a positive number")
    if department == department2:
        frappe.throw("Departments must be different")

    disabled = frappe.get_all(
        "Department",
        filters={"name": ["in", [department, department2]], "disabled": 1},
        pluck="name",
    )
    if disabled:
        frappe.throw(
            "Disabled departments cannot be used in nearness factors: {0}".format(
                ", ".join(sorted(disabled))
            )
        )

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
@survey_admin_required
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
@survey_admin_required
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
@survey_admin_required
def delete_nearness_factor(name):
    if not frappe.db.exists("Departmental Nearness Factor", name):
        frappe.throw("Nearness factor not found")
    frappe.delete_doc("Departmental Nearness Factor", name, ignore_permissions=True)
    return {"status": "deleted"}


@frappe.whitelist()
@survey_admin_required
def save_scoring_settings(settings_data):
    if isinstance(settings_data, str):
        import json
        settings_data = json.loads(settings_data)

    if not frappe.db.exists("Value Scoring Settings", "Value Scoring Settings"):
        doc = frappe.get_doc({"doctype": "Value Scoring Settings"})
    else:
        doc = frappe.get_doc("Value Scoring Settings", "Value Scoring Settings")

    doc.questions_per_category = settings_data.get("questions_per_category") or 3
    balanced_target = max(1, cint_safe(settings_data.get("balanced_reviews_per_employee"), 6))
    balanced_cap = max(balanced_target, cint_safe(settings_data.get("balanced_max_surveys_per_reviewer"), 10))
    doc.balanced_reviews_per_employee = balanced_target
    doc.balanced_max_surveys_per_reviewer = balanced_cap
    doc.max_surveys_per_employee = settings_data.get("max_surveys_per_employee") or 10
    if "min_surveys_per_batch" in settings_data:
        doc.min_surveys_per_batch = settings_data.get("min_surveys_per_batch") or 3
    elif not cint_safe(getattr(doc, "min_surveys_per_batch", None), 0):
        doc.min_surveys_per_batch = 3
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

    if "generation_mode" in settings_data:
        doc.generation_mode = settings_data.get("generation_mode") or "Cycle Matrix"
    if "role_resolution_mode" in settings_data:
        doc.role_resolution_mode = settings_data.get("role_resolution_mode") or "Hybrid"
    if "md_employee" in settings_data:
        doc.md_employee = settings_data.get("md_employee") or None
    if "team_leader_designations" in settings_data:
        doc.team_leader_designations = settings_data.get("team_leader_designations") or ""
    if "team_leaders" in settings_data:
        doc.team_leaders = []
        for entry in settings_data.get("team_leaders") or []:
            if entry.get("department") and entry.get("employee"):
                doc.append("team_leaders", {
                    "department": entry.get("department"),
                    "employee": entry.get("employee"),
                })
    if "exco_oversight" in settings_data:
        doc.exco_oversight = []
        for entry in settings_data.get("exco_oversight") or []:
            if entry.get("department") and entry.get("employee"):
                doc.append("exco_oversight", {
                    "department": entry.get("department"),
                    "employee": entry.get("employee"),
                })
    if "completeness_cycle" in settings_data:
        doc.completeness_cycle = settings_data.get("completeness_cycle") or "Quarterly"
    if "enable_scheduled_reports" in settings_data:
        doc.enable_scheduled_reports = settings_data.get("enable_scheduled_reports") or 0
    if "report_frequency" in settings_data:
        doc.report_frequency = settings_data.get("report_frequency") or ""
    if "min_completion_pct_for_final_report" in settings_data:
        doc.min_completion_pct_for_final_report = settings_data.get("min_completion_pct_for_final_report") or 90
    if "cc_team_leader_on_report" in settings_data:
        doc.cc_team_leader_on_report = settings_data.get("cc_team_leader_on_report") or 0
    if "cc_hr_on_report" in settings_data:
        doc.cc_hr_on_report = settings_data.get("cc_hr_on_report") or 0

    doc.save(ignore_permissions=True)
    return {"status": "saved"}


@frappe.whitelist()
@survey_admin_required
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
@survey_admin_required
def preview_reviewer_survey(reviewee=None):
    """Build a non-persistent 360° SurveyJS payload for HR preview."""
    employee = None
    if reviewee:
        employee = frappe.db.get_value(
            "Employee",
            {"name": reviewee, "status": "Active"},
            ["name", "employee_name", "department"],
            as_dict=True,
        )
    else:
        employees = frappe.get_all(
            "Employee",
            filters={"status": "Active"},
            fields=["name", "employee_name", "department"],
            order_by="employee_name asc",
            limit=1,
        )
        employee = employees[0] if employees else None

    if not employee:
        frappe.throw("Select an active employee to preview the reviewer experience.")

    sections = sample_360_question_sections()
    employee_name = employee.employee_name or employee.name
    safe_employee_name = escape(employee_name)
    pages = [
        {
            "name": "page_0",
            "elements": [
                {
                    "type": "html",
                    "name": "intro_html",
                    "html": (
                        '<div class="survey-welcome-hero">'
                        f'<h1 class="survey-title">Staff 360° Review for {safe_employee_name}</h1>'
                        '<div class="survey-subtitle">Confidential reviewer experience preview</div>'
                        '</div>'
                    ),
                }
            ],
        }
    ]

    scale = [
        (1, "Poor"),
        (2, "Below Expectation"),
        (3, "Good"),
        (4, "Very Good"),
        (5, "Excellent"),
    ]
    question_count = 0
    for page_number, section in enumerate(sections, start=1):
        category = section["category"]
        category_key = frappe.scrub(category) or f"category_{page_number}"
        questions = section["questions"]
        question_count += len(questions)
        pages.append(
            {
                "name": f"page_{page_number}",
                "elements": [
                    {
                        "name": f"preview_{category_key}",
                        "type": "matrix",
                        "title": f"Core Competency Assessment: {category}",
                        "description": (
                            f"Please rate {employee_name}'s performance regarding {category} "
                            "on a scale of 1 to 5."
                        ),
                        "isRequired": True,
                        "rows": [
                            {
                                "value": f"preview_{category_key}_row_{index}",
                                "text": question,
                            }
                            for index, question in enumerate(questions, start=1)
                        ],
                        "columns": [
                            {"value": f"preview_col_{score}", "text": label}
                            for score, label in scale
                        ],
                    }
                ],
            }
        )

    return {
        "reviewee": {
            "name": employee.name,
            "employee_name": employee_name,
            "department": employee.department or "",
        },
        "category_count": len(sections),
        "question_count": question_count,
        "survey_json": {
            "showProgressBar": "bottom",
            "firstPageIsStarted": True,
            "startSurveyText": "Start Preview",
            "completeText": "Finish Preview",
            "pages": pages,
        },
        "preview_only": True,
    }


@frappe.whitelist()
@survey_admin_required
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
@survey_admin_required
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
@survey_admin_required
def install_workspace():
    import json
    import os

    from frappe.modules.import_file import import_file_by_path

    base = os.path.dirname(__file__)

    # Force-sync standard pages so role changes and new pages are applied on upgrades.
    synced_pages = []
    for page_name, rel_path in (
        ("survey-analytics", os.path.join("survey_app", "page", "survey_analytics", "survey_analytics.json")),
        ("outstanding-surveys", os.path.join("survey_app", "page", "outstanding_surveys", "outstanding_surveys.json")),
        ("my-surveys", os.path.join("survey_app", "page", "my_surveys", "my_surveys.json")),
    ):
        page_json_path = os.path.join(base, rel_path)
        if not os.path.exists(page_json_path):
            frappe.throw(f"Page JSON not found: {page_name}")
        import_file_by_path(page_json_path, force=True, ignore_version=True)
        synced_pages.append(page_name)

    # Re-sync desk DocTypes so list routes (/app/survey-cycle etc.) resolve after deploy
    doctype_dir = os.path.join(base, "survey_app", "doctype")
    for folder in (
        "survey_cycle",
        "survey_cycle_pair",
        "survey_report_log",
        "survey_email_log",
        "survey_team_leader",
        "survey_exco_oversight",
    ):
        json_path = os.path.join(doctype_dir, folder, f"{folder}.json")
        if os.path.exists(json_path):
            try:
                import_file_by_path(json_path, force=True, ignore_version=True)
            except Exception:
                frappe.log_error(title=f"Sync DocType failed: {folder}", message=frappe.get_traceback())

    workspace_specs = (
        (
            "Survey Administration",
            os.path.join(
                base,
                "survey_app",
                "workspace",
                "survey-administration",
                "survey_administration.json",
            ),
            [{"role": "System Manager"}, {"role": "HR Manager"}],
        ),
        (
            "My Survey Home",
            os.path.join(base, "survey_app", "workspace", "my_surveys", "my_surveys.json"),
            [],
        ),
    )
    synced_workspaces = []

    def sync_workspace(workspace_name, workspace_path, roles):
        previous_fixture_flag = frappe.flags.in_fixtures
        frappe.flags.in_fixtures = True
        try:
            if not os.path.exists(workspace_path):
                frappe.throw(f"Workspace JSON not found: {workspace_name}")
            # Remove the pre-release name, which conflicts with the /app/my-surveys Page route.
            if workspace_name == "My Survey Home" and frappe.db.exists("Workspace", "My Surveys"):
                frappe.delete_doc("Workspace", "My Surveys", ignore_permissions=True)
            if frappe.db.exists("Workspace", workspace_name):
                frappe.delete_doc("Workspace", workspace_name, ignore_permissions=True)

            with open(workspace_path) as workspace_file:
                data = json.load(workspace_file)
            data["title"] = data.get("title") or data.get("label") or workspace_name
            data["label"] = workspace_name
            data["roles"] = roles
            data["public"] = 1
            data["is_hidden"] = 0
            if workspace_name == "My Survey Home":
                # A blank module avoids Frappe's DocType-module gate for ordinary employees.
                data["module"] = ""

            workspace_doc = frappe.get_doc(data)
            workspace_doc.insert(ignore_permissions=True)
            return workspace_doc.name
        finally:
            frappe.flags.in_fixtures = previous_fixture_flag

    for workspace_name, workspace_path, roles in workspace_specs:
        synced_workspaces.append(sync_workspace(workspace_name, workspace_path, roles))

    frappe.db.commit()
    frappe.clear_cache()

    return {
        "status": "synced",
        "pages": synced_pages,
        "workspaces": synced_workspaces,
        "doctypes": [
            d for d in (
                "Survey Cycle",
                "Survey Report Log",
                "Survey Email Log",
            )
            if frappe.db.exists("DocType", d)
        ],
    }

@frappe.whitelist()
@survey_admin_required
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

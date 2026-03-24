import frappe
import random
from itertools import count


def generate_capped_surveys():
    settings = frappe.get_doc("Value Scoring Settings")

    max_per_reviewer = settings.max_surveys_per_reviewer or 2
    max_per_employee = settings.max_surveys_per_employee or 2

    employees = frappe.get_all(
        "Employee",
        filters={"status": "Active"},
        fields=["name", "department", "reports_to"]
    )

    # Track how many surveys each person reviews
    reviewer_count = {}

    # Track how many times each person is reviewed
    reviewed_count = {}

    for emp in employees:

        # Stop if reviewer reached their cap
        if reviewer_count.get(emp.name, 0) >= max_per_reviewer:
            continue

        potential_targets = []

        # ---- 1. Manager ----
        manager = [emp.reports_to] if emp.reports_to else []

        # ---- 2. Direct Reports ----
        reports = frappe.get_all(
            "Employee",
            filters={"reports_to": emp.name, "status": "Active"},
            pluck="name"
        )

        # ---- 3. Peers ----
        peers = []
        if emp.department:
            peers = frappe.get_all(
                "Employee",
                filters={
                    "department": emp.department,
                    "name": ["not in", [emp.name] + manager + reports],
                    "status": "Active"
                },
                pluck="name"
            )

        combined_list = manager + reports + peers

        for target in combined_list:

            # Reviewer cap check
            if reviewer_count.get(emp.name, 0) >= max_per_reviewer:
                break

            # Reviewed cap check
            if reviewed_count.get(target, 0) >= max_per_employee:
                continue

            # ---- CREATE SURVEY ----
            # create_survey_and_send_invitation(sender=emp.name, receiver=target)

            receiver_name = frappe.db.get_value("Employee", target, "employee_name")
            reviewer_name = frappe.db.get_value("Employee", emp.name, "employee_name")
                        # ---- Update counters ----
            reviewer_count[emp.name] = reviewer_count.get(emp.name, 0) + 1
            reviewed_count[target] = reviewed_count.get(target, 0) + 1

            print(f"Create survey for {reviewer_name} {reviewer_count[emp.name]} to review {receiver_name} {reviewed_count[target]}")





def create_survey_and_send_invitation(sender_employee, receiver_employee):
    settings = frappe.get_doc("Value Scoring Settings")
    questions_per_cat = settings.questions_per_category or 5
    categories = frappe.get_all("Value Performance Categories", pluck="name")

    receiver_name = frappe.db.get_value("Employee", receiver_employee, "employee_name")
    reviewer_name = frappe.db.get_value("Employee", sender_employee, "employee_name")

    # Step 1: Create Survey with empty questions
    survey_doc = frappe.get_doc({
        "doctype": "Survey",
        "title": f"Value Score Review for {receiver_name}",
        "sub_title": f"Feedback provided by {reviewer_name}",
        "employee_score": receiver_employee,
        "rated_by": frappe.db.get_value("Employee", sender_employee, "user_id"),
        "is_internal_scoring": 1,
        "questions": []
    })

    selected_questions_map = {}
    page_counter = count(1)
    # Append Survey Questions to the parent (just the skeleton)
    for cat in categories:
        pool = frappe.get_all("Value Questions", filters={"category": cat}, fields=["question"])
        sample_size = min(len(pool), questions_per_cat)
        questions = random.sample(pool, sample_size) if pool else []
        if not questions:
            continue

        survey_doc.append("questions", {
            "question_name": frappe.scrub(cat),
            "type": "matrix",
            "title": f"Core Competency Assessment: {cat}",
            "description": f"Please rate the employee's performance regarding {cat} on a scale of 1 to 5.",
            "is_required": 1,
            "page_number": next(page_counter)
        })

        selected_questions_map[frappe.scrub(cat)] = questions

    # Insert parent survey (Survey Questions now exist in DB)
    survey_doc.insert(ignore_permissions=True)
    frappe.db.commit()
    
    # Fetch the parent survey first
    # survey_doc = frappe.get_doc("Survey", survey_doc.name)
    survey_questions = frappe.get_all(
    "Survey Questions",
    filters={"parent": survey_doc.name, "parenttype": "Survey"},
    fields=["name", "question_name"]
)
    for sq in survey_questions:
        # sq.name is the actual DB name for this Survey Question
        # fetch it freshly from DB
        sq_doc = frappe.get_doc("Survey Questions", sq.name)

        cat = sq_doc.question_name
        questions = selected_questions_map.get(cat, [])



        # Add columns 1-5
        for i in range(1, 6):
            sq_doc.append("options", {
                "option_value": f"col_{i}",
                "option_label": str(i),
                "score": i,
                "dimension_type": "column"
            })

        # Add rows (Value Questions)
        for q in questions:
            sq_doc.append("options", {
                "option_value": frappe.scrub(q["question"]),
                "option_label": q["question"],
                "dimension_type": "row"
            })

        # Save the Survey Question with options
        sq_doc.save(ignore_permissions=True)
        frappe.db.commit()
        
    return survey_doc.name

def send_survey_notification_and_task(survey_name, sender_employee, receiver_employee):
    """
    Sends survey email notification and creates a Task
    assigned to the reviewer.
    """

    # ---------------------------------------------
    # Fetch Required Details
    # ---------------------------------------------
    receiver_name = frappe.db.get_value("Employee", receiver_employee, "employee_name")
    receiver_department = frappe.db.get_value("Employee", receiver_employee, "department")
    reviewer_name = frappe.db.get_value("Employee", sender_employee, "employee_name")
    reviewer_user = frappe.db.get_value("Employee", sender_employee, "user_id")
    reviewer_email = frappe.db.get_value("User", reviewer_user, "email")

    # ---------------------------------------------
    # Build Survey URL
    # ---------------------------------------------
    base_url = frappe.utils.get_url()
    survey_url = f"{base_url}/survey?id={survey_name}"

    # ---------------------------------------------
    # Professional HTML Email
    # ---------------------------------------------
    email_subject = f"Performance Survey : Value Score Review for {receiver_name}"

    email_message = f"""
    <div style="font-family: Arial, sans-serif; font-size: 14px; color: #333;">
        <p>Dear {reviewer_name},</p>

        <p>You have been selected to provide feedback for the 
        <strong>Value Score Review</strong> of <strong>{receiver_name}</strong>.</p>

        <p>Your feedback plays an important role in the employee’s performance evaluation process.</p>

        <p>Please complete the survey by clicking the button below:</p>

        <p style="margin: 20px 0;">
            <a href="{survey_url}" 
               style="background-color: #2E86C1;
                      color: #ffffff;
                      padding: 10px 18px;
                      text-decoration: none;
                      border-radius: 5px;
                      display: inline-block;">
                Complete Survey
            </a>
        </p>

        <p>If the button does not work, copy and paste the link below into your browser:</p>

        <p>{survey_url}</p>

        <br>
        <p>Kind regards,<br>
        HR Department</p>
    </div>
    """

    # Send Email
    frappe.sendmail(
        recipients=[reviewer_email],
        subject=email_subject,
        message=email_message
    )

    # ---------------------------------------------
    # Create Task Assigned to Reviewer
    # ---------------------------------------------
    task_description = f"""
Employee Value Score Performance Review Task

Employee Being Reviewed: {receiver_name}
Reviewer: {reviewer_name}

You are required to complete the Value Score Survey.

Survey Link:
{survey_url}

Please ensure this is completed within the required timeline.
    """

    task_doc = frappe.get_doc({
        "doctype": "Task",
        "subject": f"Complete Value Score Review for {receiver_name}: {survey_name}",
        "description": task_description,
        "status": "Open",
        "priority": "Medium",
        "exp_start_date": frappe.utils.today(),
        "exp_end_date": frappe.utils.add_days(frappe.utils.today(), 3),
        "is_survey_task":True,
        "survey": survey_name,
        "department": receiver_department,
        "expected_time":1,  # 1 hour expected time
        "owner": reviewer_user
    })

    task_doc.insert(ignore_permissions=True)
    frappe.db.commit()
    # Create ToDo assignment manually
    todo = frappe.get_doc({
        "doctype": "ToDo",
        "allocated_to": reviewer_user,
        "reference_type": "Task",
        "reference_name": task_doc.name,
        "description": f"Complete Value Score Review for {receiver_name}",
    })
    todo.insert(ignore_permissions=True)
    frappe.db.commit()

    return {
        "status": "success",
        "survey_url": survey_url,
        "task": task_doc.name
    }
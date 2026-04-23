import frappe
import random,math
from itertools import count
from collections import defaultdict
from frappe.utils import add_days, today, formatdate


# def generate_capped_surveys():
#     settings = frappe.get_doc("Value Scoring Settings")

#     max_per_reviewer = settings.max_surveys_per_reviewer or 2
#     max_per_employee = settings.max_surveys_per_employee or 2

#     employees = frappe.get_all(
#         "Employee",
#         filters={"status": "Active"},
#         fields=["name", "department", "reports_to"]
#     )

#     # Track how many surveys each person reviews
#     reviewer_count = {}

#     # Track how many times each person is reviewed
#     reviewed_count = {}

#     for emp in employees:

#         # Stop if reviewer reached their cap
#         if reviewer_count.get(emp.name, 0) >= max_per_reviewer:
#             continue

#         potential_targets = []

#         # ---- 1. Manager ----
#         manager = [emp.reports_to] if emp.reports_to else []

#         # ---- 2. Direct Reports ----
#         reports = frappe.get_all(
#             "Employee",
#             filters={"reports_to": emp.name, "status": "Active"},
#             pluck="name"
#         )

#         # ---- 3. Peers ----
#         peers = []
#         if emp.department:
#             peers = frappe.get_all(
#                 "Employee",
#                 filters={
#                     "department": emp.department,
#                     "name": ["not in", [emp.name] + manager + reports],
#                     "status": "Active"
#                 },
#                 pluck="name"
#             )

#         combined_list = manager + reports + peers

#         for target in combined_list:

#             # Reviewer cap check
#             if reviewer_count.get(emp.name, 0) >= max_per_reviewer:
#                 break

#             # Reviewed cap check
#             if reviewed_count.get(target, 0) >= max_per_employee:
#                 continue

#             # ---- CREATE SURVEY ----
#             # create_survey_and_send_invitation(sender=emp.name, receiver=target)

#             receiver_name = frappe.db.get_value("Employee", target, "employee_name")
#             reviewer_name = frappe.db.get_value("Employee", emp.name, "employee_name")
#                         # ---- Update counters ----
#             reviewer_count[emp.name] = reviewer_count.get(emp.name, 0) + 1
#             reviewed_count[target] = reviewed_count.get(target, 0) + 1

#             print(f"Create survey for {reviewer_name} {reviewer_count[emp.name]} to review {receiver_name} {reviewed_count[target]}")



# def generate_capped_surveys():
#     settings = frappe.get_doc("Value Scoring Settings")


#     # --- Load configs ---
#     max_reviewer_cap = settings.max_surveys_per_reviewer or 10
#     max_employee_cap = settings.max_surveys_per_employee or 10

#     # Assuming settings.exclude_rated and settings.exclude_rating contain email addresses
#     excluded_rated_emails = {d.user for d in settings.exclude_rated}
#     excluded_reviewers_emails = {d.user for d in settings.exclude_rating}

#     # Fetch employee IDs or names corresponding to these emails
#     excluded_rated = set(frappe.get_all('Employee', filters={'user_id': ['in', list(excluded_rated_emails)]}, pluck='name'))
#     excluded_reviewers = set(frappe.get_all('Employee', filters={'user_id': ['in', list(excluded_reviewers_emails)]}, pluck='name'))

#     nearness_records = frappe.get_all(
#         "Departmental Nearness Factor",
#         fields=["department", "department2", "factor"]
#     )

#     # Nearness map
#     nearness_map = {
#         (df.department, df.department2): df.factor
#         for df in nearness_records
#     }

#     employees = frappe.get_all(
#         "Employee",
#         filters={"status": "Active", "name": ["not in", list(excluded_rated)]},
#         fields=["name", "department"]
#     )
 
#     # --- Counters ---
#     reviewer_count = defaultdict(int)
#     employee_review_count = defaultdict(int)

#     created_pairs = set()

#     # --- Helpers ---
#     def get_all_managers(emp):
#         managers = []
#         current = emp.reports_to
#         while current:
#             managers.append(current)
#             current = frappe.db.get_value("Employee", current, "reports_to")
#         return managers

#     def get_all_reports(emp_name):
#         result = []
#         def recurse(manager):
#             reports = frappe.get_all(
#                 "Employee",
#                 filters={"reports_to": manager, "status": "Active"},
#                 pluck="name"
#             )
#             for r in reports:
#                 result.append(r)
#                 recurse(r)
#         recurse(emp_name)
#         return result

#     # --- Phase 1: Build candidate graph ---
#     reviewee_targets = {}  # reviewee -> {target, candidates}

#     for reviewee in employees:
#         dept = reviewee.department
#         if not dept:
#             continue

#         managers = get_all_managers(reviewee)
#         reports = get_all_reports(reviewee.name)

#         department_peers = frappe.get_all(
#             "Employee",
#             filters={
#                 "department": dept,
#                 "name": ["!=", reviewee.name],
#                 "status": "Active"
#             },
#             pluck="name",
#             limit=7
#         )

#         internal_peers = list(set(department_peers + managers + reports))
#         n_internal = len(internal_peers)

#         if n_internal == 0:
#             total_needed = max(7, min(14, max_employee_cap))  # or just 7 if you want strict minimum
#             internal_peers = []
#             external_slots = total_needed
#         else:
#             total_needed = math.ceil(n_internal / 0.6)
#             total_needed = max(7, min(14, total_needed))
#             external_slots = total_needed - n_internal



#         # --- External candidates ---
#         external_candidates = []
#         other_depts = frappe.get_all(
#             "Department",
#             filters={"name": ["!=", dept]},
#             pluck="name"
#         )

#         total_weight = sum(nearness_map.get((dept, od), 0) for od in other_depts)

#         if total_weight > 0:
#             for od in other_depts:
#                 weight = nearness_map.get((dept, od), 0)
#                 if weight <= 0:
#                     continue

#                 quota = math.ceil((weight / total_weight) * external_slots)

#                 dept_emps = frappe.get_all(
#                     "Employee",
#                     filters={"department": od, "status": "Active"},
#                     pluck="name",
#                     limit=quota
#                 )
#                 external_candidates.extend(dept_emps)

#         candidates = list(set(internal_peers + external_candidates))

#         # Remove excluded reviewers
#         candidates = [c for c in candidates if c not in excluded_reviewers]

#         if not candidates:
#             continue

#         reviewee_targets[reviewee.name] = {
#             "target": total_needed,
#             "candidates": candidates
#         }

#     # --- Phase 2: Balanced assignment ---
#     # Shuffle to remove bias
#     reviewees = list(reviewee_targets.keys())
#     random.shuffle(reviewees)

#     progress = True

#     while progress:
#         progress = False

#         # Sort reviewees by least assigned (fairness)
#         reviewees.sort(key=lambda r: employee_review_count[r])

#         for reviewee in reviewees:
#             target = reviewee_targets[reviewee]["target"]

#             if employee_review_count[reviewee] >= target:
#                 continue

#             if employee_review_count[reviewee] >= max_employee_cap:
#                 continue

#             candidates = reviewee_targets[reviewee]["candidates"]

#             # Sort candidates by least load (fairness)
#             candidates_sorted = sorted(candidates, key=lambda c: reviewer_count[c])

#             for reviewer in candidates_sorted:
#                 if reviewer_count[reviewer] >= max_reviewer_cap:
#                     continue
#                 pair = (reviewer, reviewee)
#                 if pair in created_pairs:
#                     continue

#                 # Assign
#                 ALLOWED_REVIEWERS = {

#     "HR-EMP-00045",
# }
#                 # create_survey_log(reviewer=reviewer, reviewee=reviewee)
#                 if reviewer in ALLOWED_REVIEWERS:
#                     print(f"Assigning {reviewer} to review {reviewee}")
                        
#                     survey_name= create_survey_and_send_invitation(sender_employee=reviewer, receiver_employee=reviewee)
#                     send_survey_notification_and_task(survey_name, sender_employee=reviewer, receiver_employee=reviewee)
                    
#                 created_pairs.add(pair)

#                 reviewer_count[reviewer] += 1
#                 employee_review_count[reviewee] += 1

#                 progress = True
#                 break  # Move to next reviewee




import math
import random
from collections import defaultdict

def generate_capped_surveys():
    settings = frappe.get_doc("Value Scoring Settings")

    # --- Load configs ---
    max_reviewer_cap = settings.max_surveys_per_reviewer or 10
    max_employee_cap = settings.max_surveys_per_employee or 10  # Fixed number of surveys per employee

    # Assuming settings.exclude_rated and settings.exclude_rating contain email addresses
    excluded_rated_emails = {d.user for d in settings.exclude_rated}
    excluded_reviewers_emails = {d.user for d in settings.exclude_rating}

    # Fetch employee IDs or names corresponding to these emails
    excluded_rated = set(frappe.get_all('Employee', filters={'user_id': ['in', list(excluded_rated_emails)]}, pluck='name'))
    excluded_reviewers = set(frappe.get_all('Employee', filters={'user_id': ['in', list(excluded_reviewers_emails)]}, pluck='name'))

    nearness_records = frappe.get_all(
        "Departmental Nearness Factor",
        fields=["department", "department2", "factor"]
    )

    # Nearness map
    nearness_map = {
        (df.department, df.department2): df.factor
        for df in nearness_records
    }

    # --- Fetch all active employees ---
    employees = frappe.get_all(
        "Employee",
        filters={"status": "Active", "name": ["not in", list(excluded_rated)]},
        fields=["name", "department"]
    )

    # --- Counters ---
    reviewer_count = defaultdict(int)
    employee_review_count = defaultdict(int)

    created_pairs = set()

    # --- Helpers ---
    def get_all_managers(emp):
        managers = []
        current = emp.reports_to
        while current:
            managers.append(current)
            current = frappe.db.get_value("Employee", current, "reports_to")
        return managers

    def get_all_reports(emp_name):
        result = []
        def recurse(manager):
            reports = frappe.get_all(
                "Employee",
                filters={"reports_to": manager, "status": "Active"},
                pluck="name"
            )
            for r in reports:
                result.append(r)
                recurse(r)
        recurse(emp_name)
        return result

    # --- Phase 1: Build candidate graph ---
    reviewee_targets = {}  # reviewee -> {target, candidates}

    for reviewee in employees:
        dept = reviewee.department
        if not dept:
            continue

        # Collect internal peers (managers, reports, department peers)
        managers = get_all_managers(reviewee)
        reports = get_all_reports(reviewee.name)

        department_peers = frappe.get_all(
            "Employee",
            filters={
                "department": dept,
                "name": ["!=", reviewee.name],
                "status": "Active"
            },
            pluck="name",
            limit=7
        )

        internal_peers = list(set(department_peers + managers + reports))
        n_internal = len(internal_peers)

        # 60% of total_needed should be internal, 40% will be external
        total_needed = max_employee_cap
        internal_needed = math.ceil(total_needed * 0.6)  # 60% from internal
        external_needed = total_needed - internal_needed  # Remaining 40% from external

        # --- Internal candidates (internal peers) ---
        # If not enough internal reviewers, we'll just use all available internal reviewers
        # and fill the remaining spots with external reviewers.
        if len(internal_peers) < internal_needed:
            internal_needed = len(internal_peers)  # Use all internal peers
            external_needed = total_needed - internal_needed  # Fill the rest with external reviewers

        # --- External candidates ---
        external_candidates = []
        other_depts = frappe.get_all(
            "Department",
            filters={"name": ["!=", dept]},
            pluck="name"
        )

        total_weight = sum(nearness_map.get((dept, od), 0) for od in other_depts)

        if total_weight > 0:
            for od in other_depts:
                weight = nearness_map.get((dept, od), 0)
                if weight <= 0:
                    continue

                quota = math.ceil((weight / total_weight) * external_needed)

                dept_emps = frappe.get_all(
                    "Employee",
                    filters={"department": od, "status": "Active"},
                    pluck="name",
                    limit=quota
                )
                external_candidates.extend(dept_emps)

        # Randomize internal and external candidate pools
        random.shuffle(internal_peers)  # Shuffle internal reviewers to randomize selection
        random.shuffle(external_candidates)  # Shuffle external candidates to randomize selection

        # Combine internal and external candidates, ensuring internal reviewers are 60% max
        candidates = list(set(internal_peers + external_candidates))

        # Remove excluded reviewers
        candidates = [c for c in candidates if c not in excluded_reviewers]

        if not candidates:
            continue

        # Store target number of surveys for the reviewee
        reviewee_targets[reviewee.name] = {
            "target": total_needed,
            "candidates": candidates
        }

    # --- Phase 2: Balanced assignment ---
    # Shuffle reviewees to randomize assignment order
    reviewees = list(reviewee_targets.keys())
    random.shuffle(reviewees)

    progress = True

    while progress:
        progress = False

        # Sort reviewees by least assigned (fairness)
        reviewees.sort(key=lambda r: employee_review_count[r])

        for reviewee in reviewees:
            target = reviewee_targets[reviewee]["target"]

            if employee_review_count[reviewee] >= target:
                continue

            if employee_review_count[reviewee] >= max_employee_cap:
                continue

            candidates = reviewee_targets[reviewee]["candidates"]

            # Sort candidates by least load (fairness)
            candidates_sorted = sorted(candidates, key=lambda c: reviewer_count[c])

            for reviewer in candidates_sorted:
                # Ensure reviewer is not over-assigned
                if reviewer_count[reviewer] >= max_reviewer_cap:
                    continue

                pair = (reviewer, reviewee)
                if pair in created_pairs:
                    continue

                # # Assign
                # ALLOWED_REVIEWERS = {"HR-EMP-00045"}

                # # create_survey_log(reviewer=reviewer, reviewee=reviewee)
                # if reviewer in ALLOWED_REVIEWERS:
                #     print(f"Assigning {reviewer} to review {reviewee}")
                    
                survey_name = create_survey_and_send_invitation(sender_employee=reviewer, receiver_employee=reviewee)
                send_survey_notification_and_task(survey_name, sender_employee=reviewer, receiver_employee=reviewee)

                created_pairs.add(pair)

                reviewer_count[reviewer] += 1
                employee_review_count[reviewee] += 1

                progress = True
                break  # Move to next reviewee



def create_survey_log(reviewer, reviewee):
    reviewer_name = frappe.db.get_value("Employee", reviewer, "employee_name")
    reviewee_name = frappe.db.get_value("Employee", reviewee, "employee_name")

    print(f"Reviewer: {reviewer_name} ({reviewer}) -> Reviewing: {reviewee_name} ({reviewee})")



def create_survey_and_send_invitation(sender_employee, receiver_employee):
    settings = frappe.get_doc("Value Scoring Settings")
    questions_per_cat = settings.questions_per_category or 5
    categories = frappe.get_all("Value Performance Categories", pluck="name")

    receiver_name = frappe.db.get_value("Employee", receiver_employee, "employee_name")
    reviewer_name = frappe.db.get_value("Employee", sender_employee, "employee_name")

    # Step 1: Create Survey with empty questions
    survey_doc = frappe.get_doc({
        "doctype": "Survey",
        "title": f"Staff 360° Review for {receiver_name}",
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
            "description": f"Please rate {receiver_name}'s performance regarding {cat} on a scale of 1 to 5.",
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


        # Add columns with descriptive labels
        column_labels = [
            "Excellent",     # for 1
            "Very Good",     # for 2
            "Good",          # for 3
            "Below Expectation",  # for 4
            "Poor"           # for 5
        ]
        # Add columns 1-5
        for i in range(1, 6):
            sq_doc.append("options", {
                "option_value": f"col_{i}",
                "option_label": column_labels[i-1],
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
    # Calculate expected completion date (3 days from today)
    expected_completion_date = add_days(today(), 3)

    # Format the date to a readable format (optional, but recommended)
    formatted_completion_date = formatdate(expected_completion_date)

    email_subject = f"Performance Survey : Staff 360° Review for {receiver_name}"

    email_message = f"""
    <div style="font-family: Arial, sans-serif; font-size: 14px; color: #333;">
        <p>Dear {reviewer_name},</p>

        <p>You have been selected to provide feedback for the 
        <strong>Staff 360° Review</strong> of <strong>{receiver_name}</strong>.</p>

        <p>Your feedback plays an important role in the employee’s performance evaluation process.</p>
        <p><strong>Expected Completion Date: {formatted_completion_date}</strong></p>

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
Employee Staff 360° Performance Review Task

Employee Being Reviewed: {receiver_name}
Reviewer: {reviewer_name}

You are required to complete the Staff 360° Survey.

Survey Link:
{survey_url}

Please ensure this is completed within the required timeline.
    """

    task_doc = frappe.get_doc({
        "doctype": "Task",
        "subject": f"Complete Staff 360° Review for {receiver_name}: {survey_name}",
        "description": task_description,
        "status": "Open",
        "priority": "Medium",
        "exp_start_date": frappe.utils.today(),
        "exp_end_date": frappe.utils.add_days(frappe.utils.today(), 7),
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
        "description": f"Complete Staff 360° Review for {receiver_name}",
    })
    todo.insert(ignore_permissions=True)
    frappe.db.commit()

    return {
        "status": "success",
        "survey_url": survey_url,
        "task": task_doc.name
    }
# Survey App

Actserv Survey Engine for ERPNext / Frappe.

360° employee surveys: cycle planning, automated generation, public responses, employee dashboards, administration analytics, outstanding follow-ups, and scheduled reports.

## Application status and dependencies

Survey App is a **separate Frappe application**, but it is not a standalone web
service. It runs inside a Frappe Bench and uses the ERP's HR records.

| Capability | Requirement |
|---|---|
| Application runtime | Frappe Framework |
| People and organisation data | ERPNext / HRMS `Employee`, `Department`, and `Designation` records |
| Authentication and permissions | Frappe `User`, roles, sessions, and Desk |
| Employee dashboard mapping | Each employee's ERP login must be set in `Employee.user_id` |
| Email and automation | A configured outgoing email account, scheduler, and workers |

The app has its own Survey DocTypes, pages, workspaces, reports, website route,
and scheduled jobs. It does not copy employee master data into a separate
database.

---

## Environments (read this first)

| | Dev laptop / local bench | Production ERP server |
|---|---|---|
| Purpose | Build and test features | Real company data |
| Database | Local site DB (e.g. `erp.localhost`) | **The live ERP database on the server** |
| URL (example) | `http://erp.localhost:8001` | Your real ERP site URL |
| This README’s install section | Optional — for local testing only | **Use for the real server** |

Installing this app on production **writes DocTypes, pages, and workspace records into that site’s database**. Do not point a production install at the local/dev database.

---

## Prerequisites (production)

On the **production** bench / site you already run:

1. **Frappe** + **ERPNext / HRMS** with the `Employee`, `Department`, and related HR DocTypes available.
2. SSH / shell access to the server as the bench user.
3. Ability to run `bench` for the correct site name (e.g. `yourcompany.com` — use your real site, not `erp.localhost`).
4. Git access to this repo:

   `https://gitlab.actserv-africa.com/md-projects/erp-project/survey-app.git`

5. A maintenance window if you prefer fewer users online during `migrate`.

---

## Install on the real ERP (production)

Run these on the **production server**, from the production bench directory (the one that serves your live site).

### 1. Go to the bench

```bash
cd /path/to/your/frappe-bench
# example: cd /home/frappe/frappe-bench
```

Activate the bench Python env if your server uses one:

```bash
source env/bin/activate
# or whatever path your ops team uses
```

### 2. Confirm the site name

```bash
bench --site all list-apps
# or
ls sites/
```

Note the **production site name** (folder under `sites/`). You will use it in every command below as `YOUR_SITE`.

### 3. Get the app into the bench

**If the app is not on the server yet:**

```bash
bench get-app survey_app https://gitlab.actserv-africa.com/md-projects/erp-project/survey-app.git
```

**If the code is already cloned elsewhere on the server**, link/copy it into `apps/` as `survey_app` (Frappe app folder name must be `survey_app`), then:

```bash
# from bench root, only if apps/survey_app is not already present:
# bench get-app /absolute/path/to/survey-app
```

Confirm:

```bash
ls apps/survey_app
```

### 4. Install the app on the production site

This registers the app on **that site’s database**:

```bash
bench --site YOUR_SITE install-app survey_app
```

If the app was already installed and you are only deploying an update, skip `install-app` and use the update steps below.

### 5. Migrate (create / update DocTypes and schema)

```bash
bench --site YOUR_SITE migrate
```

### 6. Build assets and clear cache

```bash
bench build --app survey_app
bench --site YOUR_SITE clear-cache
bench --site YOUR_SITE clear-website-cache
```

### 7. Install / refresh the workspaces and pages

This idempotently synchronizes:

- **Survey Administration** for System Managers and HR Managers
- **My Survey Home** for authenticated Desk users
- Survey Analytics, Outstanding Surveys, and My Surveys pages
- Survey cycle, report-log, email-log, and team-leader metadata

```bash
bench --site YOUR_SITE execute survey_app.survey_config.install_workspace
bench --site YOUR_SITE clear-cache
```

### 8. Restart production processes

Use whatever your server normally uses, for example:

```bash
bench restart
# or: sudo supervisorctl restart all
# or: sudo systemctl restart frappe-bench.target
```

Do **not** use `bench start` on production unless that is how this specific server is run (most production sites use supervisor / systemd / nginx + gunicorn).

### 9. Smoke-check in the browser

1. Log in to the **production** ERP URL (not the local dev URL).
2. With an HR Manager or System Manager account, open **Survey Administration**.
3. Confirm the administration pages open:
   - Survey Setup (`/app/survey-setup`)
   - Outstanding Surveys (`/app/outstanding-surveys`)
   - Analytics (`/app/survey-analytics`)
4. With an ordinary mapped employee account, open:
   - My Surveys (`/app/my-surveys`)
5. Confirm the employee sees only their own aggregate results and assignments.
6. Open **Value Scoring Settings** and configure automation / scoring as needed.

---

## Update an existing production install

When new Survey App code is released:

```bash
cd /path/to/your/frappe-bench
cd apps/survey_app
git pull
cd ../..

bench --site YOUR_SITE migrate
bench build --app survey_app
bench --site YOUR_SITE execute survey_app.survey_config.install_workspace
bench --site YOUR_SITE clear-cache
bench restart   # or your normal process restart
```

`install_workspace` recreates both standard workspaces from the app JSON. Survey
Administration is restricted to **System Manager** and **HR Manager**; My Survey
Home remains available to authenticated Desk users. If you customized workspace
roles only in the UI, re-apply those customizations after this step or change
the workspace JSON and `install_workspace()` before deployment.

---

## Access and privacy model

| Surface | Access |
|---|---|
| Survey Administration workspace and APIs | System Manager, HR Manager, or Administrator |
| My Survey Home workspace | Authenticated Desk users |
| `/app/my-surveys` data | The employee mapped to the current session through `Employee.user_id` |
| Survey invitation and submission URLs | Existing public-token behavior is retained |

The My Surveys API never accepts an employee identifier from the browser.
Changing request arguments cannot select another employee. Employee results
contain aggregate scores and participation counts only—never reviewer
identities, individual answers, comments, or coworker-level benchmark records.

### Change who sees the workspace (desk)

1. Open **Survey Administration** → Edit workspace → Roles → add/remove roles → Save.
2. Hard-refresh the browser.

### Change who sees it permanently (in code)

1. Edit `survey_app/survey_app/workspace/survey-administration/survey_administration.json` → `roles`.
2. Edit `survey_app/survey_config.py` → `install_workspace()` so it keeps the same roles (it currently sets System Manager + HR Manager).
3. Redeploy / `install_workspace` as above.

List all roles on the site: Desk → awesome bar → **Role** (`/app/role`).

**Note:** Workspace roles control sidebar visibility. Individual **Pages** (e.g. Outstanding Surveys) also have their own roles. Users need both where applicable.

---

## Optional: local / dev install only

Use this only on a developer machine. It does **not** update the production database.

```bash
cd ~/frappe-bench   # or your local bench
source ~/bench-env/bin/activate   # if you use a separate venv

# get or link the app
bench get-app survey_app https://gitlab.actserv-africa.com/md-projects/erp-project/survey-app.git
# or: ln -s /path/to/workProjects/survey-app apps/survey_app

bench --site YOUR_LOCAL_SITE install-app survey_app
bench --site YOUR_LOCAL_SITE migrate
bench --site YOUR_LOCAL_SITE execute survey_app.survey_config.install_workspace
bench --site YOUR_LOCAL_SITE clear-cache
bench start
```

Local example site from development: `erp.localhost` on port `8001`. That site’s DB is separate from production.

---

## After install — first-time configuration

1. Open **Survey Setup → Roles & Org**
   - Set **Managing Director**
   - Add **Team Leaders** per department (or rely on Hybrid org/role fallback)
   - Use **Preview Resolved Roster**, **Preview Cycle Load**, and **Who Reviews Who**
2. Open **Survey Setup → Automation**
   - Generation mode: **Cycle Matrix** (recommended) or Legacy Capped
   - Cycle strategy defaults to **Balanced Coverage**. For an intentional first-cycle organisation baseline, select **Full Baseline Matrix**, review the workload preview, and click **Apply to This Cycle** before any batch is generated.
   - Choose **Survey Frequency** (e.g. Weekly) and **Completeness Cycle** (e.g. Quarterly)
   - Optionally enable **Automatic Individual Reports** + **Report Frequency** (e.g. Monthly)
   - **Build / Refresh Cycle**, then **Run Survey Batch Now** to smoke-test
3. Open **Survey Setup → Generate Surveys**, select an active employee, and use **Preview Reviewer Experience** to test the current sampled 360° form without saving a response.
4. **Value Performance Categories** / **Value Questions** — survey content
5. **Departmental Nearness Factor** — cross-department required reviewers
6. Confirm **Email** / email queue works (invites, reminders, reports)
7. Scheduler must be running so survey batches + report jobs can fire (`*/5` cron)

### How Cycle Matrix load math works

- **Balanced Coverage** is the recurring default. It preserves Team Leader→team and Team Leader→MD constraints, targets a configurable number of reviews received per employee, allocates internal/external coverage using the nearness weights, and selects the least-loaded eligible reviewers up to the configured per-cycle safety cap.
- **Full Baseline Matrix** is a deliberate first-cycle option. It retains comprehensive peer and weighted-nearness coverage and can therefore create a substantially heavier workload.
- Survey Setup previews total pairs plus average/minimum/maximum reviewer load before HR applies a strategy. The strategy can be changed only before the first assignment or batch is generated.
- New cycles automatically return to **Balanced Coverage**; choosing Full Baseline Matrix does not become a permanent default.
- Spreads unassigned pairs across remaining batches in the completeness cycle
- Reports at the chosen report frequency: **Final** if cycle completion ≥ threshold, else **Progress** (+ reminders)

### Prepare employees for My Surveys

1. Open each participating **Employee** record.
2. Set **User ID** to that employee's ERP user.
3. Confirm the Employee status is **Active**.
4. Give the user normal Desk access.
5. Ask the employee to open `/app/my-surveys`.

Unmapped users receive setup guidance instead of data. Inactive employees
receive a safe inactive-profile state.

---

## My Surveys employee dashboard

The employee dashboard provides:

- Identity, designation, department, and active-cycle context
- Released-period selector for closed Survey Cycles and legacy Earlier Surveys
- Overall score, prior-cycle change, organisation percentile, anonymous
  organisation average, and reviews received
- Competency score bars with organisation-average markers
- Released-period performance trend and review-coverage chart
- Executive readout for strongest competency, development priority, and
  benchmark position
- Pending assignments with **Complete survey** links
- The 20 most recent completed assignments
- Server-side From/To date filtering for pending and completed survey activity

### Result release behavior

- Scores from an open, generating, or reporting cycle remain locked.
- Closing a Survey Cycle is HR's explicit release action for the dashboard.
- The latest closed cycle is selected by default.
- Trends use released periods only and compare a closed cycle with the
  preceding closed cycle.
- Legacy responses that are not associated with a cycle appear under
  **Earlier Surveys**.
- Activity date filters affect the task lists, not released score boundaries.

---

## Reporting and automation

- Individual employee reports use the same cycle-aware aggregation as My
  Surveys.
- Team Leader, Managing Director, and HR digests provide role-appropriate
  aggregate views.
- Survey Email Log tracks invitations, reminders, individual reports, and
  management reports.
- Survey Report Log records report generation history.
- Scheduled survey generation, report sending, and email-status synchronization
  run through the five-minute scheduler hook; each job evaluates its configured
  frequency before doing work.

---

## Main features (quick map)

| Feature | Where |
|--------|--------|
| Roles, cycle load, automation | Survey Setup page |
| Required review cycle | Survey Cycle DocType |
| Pending reviews + reminders | Outstanding Surveys page |
| Employee personal results and assignments | My Surveys (`/app/my-surveys`) |
| Organisation scores and dashboards | Survey Analytics page |
| Released-period trend and review coverage | My Surveys |
| Activity date filtering | My Surveys task lists |
| Individual report history | Survey Report Log |
| Email delivery queue (invites / reminders / reports) | Survey Email Log — filter by Email Type + Survey Cycle |
| Hub for all of the above | Survey Administration workspace |
| Generation history | Survey Generation Log |

---

## Verification

From the bench root:

```bash
# Enable only while running tests, then restore it.
bench --site YOUR_SITE set-config allow_tests true
bench --site YOUR_SITE run-tests --app survey_app --module survey_app.tests.test_my_surveys
bench --site YOUR_SITE set-config allow_tests false

# Static and asset checks
env/bin/python -m compileall -q apps/survey_app/survey_app
node --check apps/survey_app/survey_app/survey_app/page/my_surveys/my_surveys.js
bench build --app survey_app
```

Before release, manually verify `/app/my-surveys` with an ordinary employee
account and Survey Administration with an HR Manager account at desktop and
mobile widths.

---

## License

MIT

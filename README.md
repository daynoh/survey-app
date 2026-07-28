# Survey App

Actserv Survey Engine for ERPNext / Frappe.

360° employee surveys: setup, automated generation, responses, analytics, outstanding follow-ups, and generation logs.

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

1. **Frappe** + **ERPNext** (Employee and related HR data must exist; HRMS recommended if you use it for employees).
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

### 7. Install / refresh the Survey Administration workspace

This creates the desk workspace (shortcuts, Outstanding Surveys, Analytics, etc.) and ensures key pages exist:

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
2. Open the awesome bar → search **Survey Administration**.
3. Confirm you can open:
   - Survey Setup (`/app/survey-setup`)
   - Outstanding Surveys (`/app/outstanding-surveys`)
   - Analytics (`/app/survey-analytics`)
4. Open **Value Scoring Settings** and configure automation / scoring as needed.

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

`install_workspace` recreates the **Survey Administration** workspace from the app JSON (roles default to **System Manager** and **HR Manager**). If you customized workspace roles only in the UI, re-apply those customizations after this step, or change the roles in the workspace JSON / `install_workspace` before running it.

---

## Who can see Survey Administration

By default after `install_workspace`:

- **System Manager**
- **HR Manager**

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

1. **Value Scoring Settings** — scoring, departments, auto-generation frequency, enable/disable schedule.
2. **Value Performance Categories** / **Value Questions** — survey content (also via Survey Setup).
3. **Departmental Nearness Factor** — who rates whom across departments.
4. Confirm **Email** / email queue works (survey invites and reminders).
5. Scheduler must be running on production so `auto_generate_if_due` can fire (cron every 5 minutes; actual run depends on settings).

---

## Main features (quick map)

| Feature | Where |
|--------|--------|
| Setup / automation / generation trail | Survey Setup page |
| Pending reviews + reminders | Outstanding Surveys page |
| Scores / dashboards | Survey Analytics page |
| Hub for all of the above | Survey Administration workspace |
| Generation history DocType | Survey Generation Log |

---

## License

MIT

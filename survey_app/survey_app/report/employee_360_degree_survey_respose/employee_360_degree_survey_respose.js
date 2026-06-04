// Report: User Scores By Category
// Filters definition

frappe.query_reports["Employee 360 Degree Survey Respose"] = {
    filters: [
        {
            fieldname: "from_date",
            label: __("From Date"),
            fieldtype: "Date",
            default: frappe.datetime.add_months(frappe.datetime.get_today(), -1),
            reqd: 1,
        },
        {
            fieldname: "to_date",
            label: __("To Date"),
            fieldtype: "Date",
            default: frappe.datetime.get_today(),
            reqd: 1,
        },
        {
            fieldname: "survey",
            label: __("Survey"),
            fieldtype: "Link",
            options: "Survey",
            on_change: function () {
                const survey = frappe.query_report.get_filter_value("survey");
                if (!survey) {
                    frappe.query_report.set_filter_value("employee", "");
                    frappe.query_report.set_filter_value("rated_by", "");
                }
            },
        },
        {
            fieldname: "employee",
            label: __("Employee (Rated)"),
            fieldtype: "Link",
            options: "Employee",
        },
        {
            fieldname: "rated_by",
            label: __("Rated By"),
            fieldtype: "Link",
            options: "User",
        },
        {
            fieldname: "category",
            label: __("Category"),
            fieldtype: "Link",
            options: "Value Performance Categories",
        },
    ],

    // -----------------------------------------------------------------------
    // Formatter: colour-code the Score % column
    // -----------------------------------------------------------------------
    formatter: function (value, row, column, data, default_formatter) {
        value = default_formatter(value, row, column, data);

        if (column.fieldname === "score_percentage" && data) {
            const pct = parseFloat(data.score_percentage) || 0;
            let colour = "#d9534f"; // red  < 50
            if (pct >= 70) {
                colour = "#5cb85c"; // green ≥ 70
            } else if (pct >= 50) {
                colour = "#f0ad4e"; // orange 50–69
            }
            value = `<span style="color:${colour}; font-weight:600;">${value}</span>`;
        }

        return value;
    },

    // -----------------------------------------------------------------------
    // After render: add an export-to-Excel button in the toolbar
    // -----------------------------------------------------------------------
    onload: function (report) {
        report.page.add_inner_button(__("Export to Excel"), function () {
            frappe.query_report.export_report("xlsx");
        });
    },

    // -----------------------------------------------------------------------
    // Get chart: override default to ensure bar chart renders well
    // -----------------------------------------------------------------------
    get_datatable_options(options) {
        return Object.assign(options, {
            checkboxColumn: true,
            events: {
                onCheckRow: function () { },
            },
        });
    },
};
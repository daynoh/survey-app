
frappe.query_reports["User Scores By Category"] = {
    filters: [
        {
            fieldname: "from_date",
            label: "From Date",
            fieldtype: "Date",
        },
        {
            fieldname: "to_date",
            label: "To Date",
            fieldtype: "Date",
        },
        {
            fieldname: "user_id",
            label: "User ID",
            fieldtype: "Data",
        },
        {
            fieldname: "survey",
            label: "Survey",
            fieldtype: "Link",
            options: "Survey",
        },
    ]
};
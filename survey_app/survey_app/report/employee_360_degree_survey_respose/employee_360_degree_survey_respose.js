// Report: Employee 360 Degree Survey Respose

function survey_report_download(file_format) {
	const report = frappe.query_report;
	if (!report) {
		frappe.msgprint(__("Open the report first, then try Export again."));
		return;
	}

	let filters;
	try {
		filters = report.get_filter_values(true) || {};
	} catch (e) {
		frappe.msgprint(__("Please set From Date and To Date, then click Refresh."));
		return;
	}

	frappe.dom.freeze(__("Preparing export…"));

	frappe.call({
		method: "frappe.desk.query_report.run",
		args: {
			report_name: report.report_name,
			filters: filters,
			are_default_filters: false,
		},
		callback: function (r) {
			frappe.dom.unfreeze();
			const result = (r.message && r.message.result) || [];

			if (!result.length) {
				frappe.msgprint({
					title: __("Nothing to export"),
					indicator: "orange",
					message: __(
						"No survey scores match the filters at the top of this page.<br><br>" +
						"<b>What to do:</b><ol>" +
						"<li>Widen <b>From Date</b> / <b>To Date</b> (or clear Survey / Employee filters)</li>" +
						"<li>Click <b>Refresh</b> and wait until the table shows rows</li>" +
						"<li>Then use <b>Export → Excel</b> or <b>Export → CSV</b></li>" +
						"</ol>"
					),
				});
				return;
			}

			open_url_post(frappe.request.url, {
				cmd: "frappe.desk.query_report.export_query",
				report_name: report.report_name,
				file_format_type: file_format,
				filters: filters,
				visible_idx: result.map((_, i) => i),
				custom_columns: [],
				csv_delimiter: ",",
				csv_quoting: 1,
				include_indentation: 0,
			});
		},
		error: function () {
			frappe.dom.unfreeze();
		},
	});
}

frappe.query_reports["Employee 360 Degree Survey Respose"] = {
	filters: [
		{
			fieldname: "from_date",
			label: __("From Date"),
			fieldtype: "Date",
			// Wide default so rows appear without hunting for the right month
			default: frappe.datetime.add_months(frappe.datetime.get_today(), -12),
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

	formatter: function (value, row, column, data, default_formatter) {
		try {
			value = default_formatter(value, row, column, data);
		} catch (e) {
			value = value == null ? "" : value;
		}

		const fieldname = (column && (column.fieldname || column.id)) || "";
		if (fieldname === "score_percentage" && data) {
			const pct = parseFloat(data.score_percentage) || 0;
			let colour = "#d9534f";
			if (pct >= 70) {
				colour = "#5cb85c";
			} else if (pct >= 50) {
				colour = "#f0ad4e";
			}
			value = `<span style="color:${colour}; font-weight:600;">${value}</span>`;
		}

		return value;
	},

	onload: function (report) {
		// If the chart crashes, Frappe never reaches $report.show() — so you see
		// summary cards but an empty table. Guard both render paths.
		const _render_chart = report.render_chart.bind(report);
		report.render_chart = function (options) {
			try {
				_render_chart(options);
			} catch (e) {
				console.error("Survey 360 chart error", e);
				report.$chart && report.$chart.empty().hide();
			}
		};

		const _render_datatable = report.render_datatable.bind(report);
		report.render_datatable = function () {
			try {
				// Show wrapper before DataTable measures layout
				report.$report && report.$report.show();
				_render_datatable();
			} catch (e) {
				console.error("Survey 360 table error", e);
				report.$report && report.$report.show();
				frappe.show_alert({
					message: __("Could not draw the results table. Try Refresh, or Export still works."),
					indicator: "orange",
				});
			} finally {
				report.$report && report.$report.show();
			}
		};

		report.page.add_inner_button(__("Excel"), function () {
			survey_report_download("Excel");
		}, __("Export"));

		report.page.add_inner_button(__("CSV"), function () {
			survey_report_download("CSV");
		}, __("Export"));
	},
};

frappe.pages['survey-analytics'].on_page_load = function (wrapper) {
	var page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __('360° Performance Dashboard'),
		single_column: true
	});
	frappe.breadcrumbs.add('Survey App');

	var $main = $(page.main).css({ padding: '0', background: '#f3f5f7' });
	var data = null;

	$main.html(`
		<div class="sa-root">
			<div class="sa-hero">
				<div class="sa-hero-text">
					<div class="sa-eyebrow">${__('People Analytics')}</div>
					<h1>${__('360° Performance Dashboard')}</h1>
					<p>${__('Executive view of feedback completion, organisational scores, and development priorities.')}</p>
				</div>
				<div class="sa-hero-meta" id="sa-period-label"></div>
			</div>

			<div class="sa-filters">
				<div class="sa-filter-group">
					<span class="sa-filter-label">${__('Period')}</span>
					<div class="btn-group btn-group-sm date-presets">
						<button class="btn btn-default preset-btn" data-preset="30">${__('30 Days')}</button>
						<button class="btn btn-default preset-btn active" data-preset="90">${__('90 Days')}</button>
						<button class="btn btn-default preset-btn" data-preset="180">${__('6 Months')}</button>
						<button class="btn btn-default preset-btn" data-preset="365">${__('1 Year')}</button>
						<button class="btn btn-default preset-btn" data-preset="all">${__('All Time')}</button>
					</div>
				</div>
				<div class="sa-filter-group">
					<span class="sa-filter-label">${__('Range')}</span>
					<div class="date-range">
						<input type="date" class="form-control input-sm" id="f-from">
						<span class="text-muted">–</span>
						<input type="date" class="form-control input-sm" id="f-to">
					</div>
				</div>
				<div class="sa-filter-group">
					<span class="sa-filter-label">${__('Department')}</span>
					<select class="form-control input-sm" id="f-dept"><option value="">${__('All Departments')}</option></select>
				</div>
				<div class="sa-filter-group">
					<span class="sa-filter-label">${__('Employee')}</span>
					<select class="form-control input-sm" id="f-emp"><option value="">${__('All Employees')}</option></select>
				</div>
				<div class="sa-filter-group">
					<span class="sa-filter-label">${__('Category')}</span>
					<select class="form-control input-sm" id="f-cat"><option value="">${__('All Categories')}</option></select>
				</div>
				<button class="btn btn-default btn-sm" id="f-reset" title="${__('Reset Filters')}">
					<i class="fa fa-refresh"></i> ${__('Reset')}
				</button>
			</div>

			<div class="sa-content">
				<section class="sa-section">
					<div class="sa-section-head">
						<h2>${__('Executive Summary')}</h2>
						<p>${__('Key outcomes for the selected period')}</p>
					</div>
					<div class="row" id="sa-summary"></div>
					<div class="row" id="sa-insights" style="margin-top:4px;"></div>
				</section>

				<section class="sa-section">
					<div class="sa-section-head">
						<h2>${__('Performance Overview')}</h2>
						<p>${__('Compare scores across people and capability areas')}</p>
					</div>
					<div class="row chart-row">
						<div class="col-md-6">
							<div class="chart-panel">
								<div class="chart-title-row">
									<div>
										<div class="chart-title">${__('Score by Employee')}</div>
										<div class="chart-sub" id="ch-emp-sub">${__('Average 360° score percentage')}</div>
									</div>
									<div class="chart-controls">
										<select class="form-control input-sm" id="emp-view">
											<option value="top15">${__('Top 15')}</option>
											<option value="bottom15">${__('Bottom 15')}</option>
											<option value="all">${__('All (scrollable)')}</option>
										</select>
										<select class="form-control input-sm" id="emp-sort">
											<option value="desc">${__('Highest first')}</option>
											<option value="asc">${__('Lowest first')}</option>
										</select>
									</div>
								</div>
								<div id="ch-emp" class="chart-body chart-body-scroll"></div>
							</div>
						</div>
						<div class="col-md-6">
							<div class="chart-panel">
								<div class="chart-title">${__('Score by Competency')}</div>
								<div class="chart-sub">${__('Organisational strength by category')}</div>
								<div id="ch-cat" class="chart-body"></div>
							</div>
						</div>
					</div>
				</section>

				<section class="sa-section">
					<div class="sa-section-head">
						<h2>${__('Organisational Insights')}</h2>
						<p>${__('Department health, competency mix, and feedback momentum')}</p>
					</div>
					<div class="row chart-row">
						<div class="col-md-6">
							<div class="chart-panel">
								<div class="chart-title-row">
									<div>
										<div class="chart-title">${__('Score by Department')}</div>
										<div class="chart-sub" id="ch-dept-sub">${__('Overall average — toggle a category to compare')}</div>
									</div>
									<div class="chart-controls">
										<select class="form-control input-sm" id="dept-cat-view" title="${__('Category')}">
											<option value="__all__">${__('All Categories')}</option>
										</select>
									</div>
								</div>
								<div id="ch-dept" class="chart-body"></div>
							</div>
						</div>
						<div class="col-md-6">
							<div class="chart-panel">
								<div class="chart-title-row">
									<div>
										<div class="chart-title">${__('Competency by Department')}</div>
										<div class="chart-sub" id="ch-comp-dept-sub">${__('How one department scores across skills')}</div>
									</div>
									<div class="chart-controls">
										<select class="form-control input-sm" id="comp-dept-view" title="${__('Department')}">
											<option value="">${__('Select department')}</option>
										</select>
									</div>
								</div>
								<div id="ch-comp-dept" class="chart-body"></div>
							</div>
						</div>
					</div>
					<div class="row chart-row">
						<div class="col-md-12">
							<div class="chart-panel">
								<div class="chart-title">${__('Feedback Over Time')}</div>
								<div class="chart-sub">${__('Response volume and average score trend')}</div>
								<div id="ch-time" class="chart-body"></div>
							</div>
						</div>
					</div>
				</section>

				<section class="sa-section">
					<div class="sa-section-head">
						<h2>${__('Participation & Detail')}</h2>
						<p>${__('Reviewer coverage and employee-level outcomes')}</p>
					</div>
					<div class="row chart-row">
						<div class="col-md-5">
							<div class="chart-panel">
								<div class="chart-title">${__('Reviewer Activity')}</div>
								<div class="chart-sub">${__('Who completed the most feedback')}</div>
								<div id="ch-rev" class="chart-body"></div>
							</div>
						</div>
						<div class="col-md-7">
							<div class="chart-panel">
								<div class="chart-title-row">
									<div>
										<div class="chart-title">${__('Employee Scorecard')}</div>
										<div class="chart-sub" id="scorecard-sub">${__('Average across all skills')}</div>
									</div>
									<div class="chart-controls">
										<select class="form-control input-sm" id="scorecard-view" style="width:160px;">
											<option value="__overall__">${__('Average — all skills')}</option>
										</select>
									</div>
								</div>
								<div class="table-scroll">
									<table class="table table-hover" id="tbl-detail">
										<thead>
											<tr>
												<th data-sort="employee_name">${__('Employee')}</th>
												<th data-sort="department">${__('Department')}</th>
												<th data-sort="category">${__('Skill')}</th>
												<th data-sort="score_pct">${__('Score')}</th>
												<th>${__('Band')}</th>
											</tr>
										</thead>
										<tbody></tbody>
									</table>
								</div>
							</div>
						</div>
					</div>
				</section>
			</div>
		</div>
		<style>
			.sa-root {
				min-width: 100%;
				color: #243342;
				font-family: "IBM Plex Sans", "Segoe UI", "Helvetica Neue", Arial, sans-serif;
			}
			.sa-hero {
				background: linear-gradient(135deg, #1f3a4d 0%, #2f5f73 55%, #3d7a7a 100%);
				color: #fff;
				padding: 28px 32px 24px;
				display: flex;
				justify-content: space-between;
				gap: 24px;
				align-items: flex-end;
			}
			.sa-eyebrow {
				font-size: 11px;
				letter-spacing: 1.2px;
				text-transform: uppercase;
				opacity: 0.8;
				margin-bottom: 8px;
				font-weight: 600;
			}
			.sa-hero h1 {
				margin: 0 0 8px;
				font-size: 28px;
				font-weight: 650;
				letter-spacing: -0.3px;
			}
			.sa-hero p {
				margin: 0;
				max-width: 560px;
				opacity: 0.88;
				font-size: 14px;
				line-height: 1.5;
			}
			.sa-hero-meta {
				background: rgba(255,255,255,0.12);
				border: 1px solid rgba(255,255,255,0.18);
				border-radius: 10px;
				padding: 12px 16px;
				min-width: 180px;
				font-size: 13px;
			}
			.sa-filters {
				background: #fff;
				border-bottom: 1px solid #e2e8ee;
				padding: 14px 28px;
				display: flex;
				align-items: flex-end;
				gap: 14px;
				flex-wrap: wrap;
				position: sticky;
				top: 0;
				z-index: 5;
			}
			.sa-filter-group { display: flex; flex-direction: column; gap: 4px; }
			.sa-filter-label {
				font-size: 10px;
				font-weight: 700;
				letter-spacing: 0.7px;
				text-transform: uppercase;
				color: #7a8794;
			}
			.sa-filters input[type="date"] { width: 140px; }
			.sa-filters .date-range { display: flex; align-items: center; gap: 6px; }
			.sa-filters select { width: 170px; }
			.sa-filters .preset-btn { font-weight: 500; padding: 5px 12px; font-size: 12px; }
			.sa-filters .preset-btn.active,
			.sa-filters .preset-btn.btn-primary {
				background: #2f5f73 !important;
				border-color: #2f5f73 !important;
				color: #fff !important;
			}
			.sa-content { padding: 24px 28px 40px; }
			.sa-section { margin-bottom: 28px; }
			.sa-section-head { margin-bottom: 14px; }
			.sa-section-head h2 {
				margin: 0 0 4px;
				font-size: 18px;
				font-weight: 650;
				color: #1f3a4d;
			}
			.sa-section-head p {
				margin: 0;
				color: #6d7b88;
				font-size: 13px;
			}
			.chart-row { margin-bottom: 18px; }
			.chart-panel {
				background: #fff;
				border: 1px solid #e2e8ee;
				border-radius: 12px;
				box-shadow: 0 1px 2px rgba(31,58,77,0.04);
				overflow: hidden;
				height: 100%;
			}
			.chart-panel .chart-title {
				font-size: 14px;
				font-weight: 650;
				color: #1f3a4d;
				padding: 16px 18px 0;
			}
			.chart-panel .chart-title-row {
				display: flex;
				justify-content: space-between;
				gap: 12px;
				align-items: flex-start;
				padding-right: 12px;
			}
			.chart-panel .chart-controls {
				display: flex;
				gap: 6px;
				padding-top: 14px;
			}
			.chart-panel .chart-controls select { width: 150px; max-width: 200px; }
			.chart-panel .chart-sub {
				font-size: 12px;
				color: #7a8794;
				padding: 4px 18px 10px;
			}
			.chart-panel .chart-body { min-height: 280px; padding: 4px 10px 10px; }
			.chart-panel .chart-body-scroll { max-height: 480px; overflow-y: auto; }
			.summary-card {
				background: #fff;
				border: 1px solid #e2e8ee;
				border-radius: 12px;
				padding: 18px 18px 16px;
				box-shadow: 0 1px 2px rgba(31,58,77,0.04);
				height: 100%;
				border-top: 3px solid #2f5f73;
			}
			.summary-card.ind-navy { border-top-color: #1f3a4d; }
			.summary-card.ind-teal { border-top-color: #3d7a7a; }
			.summary-card.ind-green { border-top-color: #2f8f6b; }
			.summary-card.ind-amber { border-top-color: #c58a2e; }
			.summary-card.ind-red { border-top-color: #c44b4b; }
			.summary-value {
				font-size: 30px;
				font-weight: 700;
				line-height: 1.15;
				color: #1f3a4d;
				font-variant-numeric: tabular-nums;
			}
			.summary-label {
				font-size: 12px;
				font-weight: 650;
				color: #3d4f5f;
				margin-top: 8px;
			}
			.summary-sub {
				font-size: 11px;
				color: #7a8794;
				margin-top: 4px;
			}
			.insight-card {
				background: #fff;
				border: 1px solid #e2e8ee;
				border-radius: 12px;
				padding: 16px 18px;
				height: 100%;
			}
			.insight-card .insight-kicker {
				font-size: 10px;
				font-weight: 700;
				letter-spacing: 0.8px;
				text-transform: uppercase;
				color: #7a8794;
				margin-bottom: 6px;
			}
			.insight-card .insight-title {
				font-size: 15px;
				font-weight: 650;
				color: #1f3a4d;
				margin-bottom: 4px;
			}
			.insight-card .insight-meta {
				font-size: 12px;
				color: #6d7b88;
			}
			.insight-card.positive { background: #f3faf7; border-color: #d5ebe1; }
			.insight-card.watch { background: #fff8ef; border-color: #f0e0c4; }
			.band {
				display: inline-block;
				padding: 2px 8px;
				border-radius: 999px;
				font-size: 11px;
				font-weight: 650;
			}
			.band-high { background: #e7f6ef; color: #1f7a55; }
			.band-mid { background: #fff4e5; color: #9a6700; }
			.band-low { background: #fdecea; color: #b42318; }
			.table-scroll { max-height: 340px; overflow-y: auto; }
			#tbl-detail { margin: 0; font-size: 12px; }
			#tbl-detail thead { position: sticky; top: 0; background: #f7f9fb; z-index: 1; }
			#tbl-detail th {
				border-top: none;
				padding: 11px 14px;
				color: #5b6b7a;
				font-weight: 650;
				text-transform: uppercase;
				font-size: 10px;
				letter-spacing: 0.5px;
				cursor: pointer;
				user-select: none;
			}
			#tbl-detail th[data-sort].active { color: #2f5f73; }
			#tbl-detail td { padding: 10px 14px; vertical-align: middle; color: #314354; }
			.sa-empty {
				text-align: center;
				padding: 48px 20px;
				color: #8a97a4;
				font-size: 13px;
			}
			@media (max-width: 992px) {
				.sa-hero { flex-direction: column; align-items: flex-start; padding: 22px 18px; }
				.sa-content { padding: 18px 16px 32px; }
				.sa-filters { padding: 12px 16px; }
				.sa-filters input[type="date"] { width: 125px; }
				.sa-filters select { width: 150px; }
			}
		</style>
	`);

	var today = frappe.datetime.get_today();
	$('#f-to').val(today);

	frappe.call({
		method: 'frappe.client.get_list',
		args: { doctype: 'Department', fields: ['name'], limit_page_length: 200, order_by: 'name asc' },
		callback: function (r) {
			(r.message || []).forEach(function (d) {
				$('#f-dept').append('<option value="' + frappe.utils.escape_html(d.name) + '">' + frappe.utils.escape_html(d.name) + '</option>');
			});
		}
	});
	frappe.call({
		method: 'frappe.client.get_list',
		args: { doctype: 'Value Performance Categories', fields: ['name'], limit_page_length: 200, order_by: 'name asc' },
		callback: function (r) {
			(r.message || []).forEach(function (d) {
				$('#f-cat').append('<option value="' + frappe.utils.escape_html(d.name) + '">' + frappe.utils.escape_html(d.name) + '</option>');
			});
		}
	});
	load_employees();

	function load_employees() {
		var dep = $('#f-dept').val() || undefined;
		var args = {
			doctype: 'Employee',
			fields: ['name', 'employee_name'],
			filters: { status: 'Active' },
			limit_page_length: 500,
			order_by: 'employee_name asc'
		};
		if (dep) args.filters.department = dep;
		frappe.call({
			method: 'frappe.client.get_list',
			args: args,
			callback: function (r) {
				$('#f-emp').empty().append('<option value="">' + __('All Employees') + '</option>');
				(r.message || []).forEach(function (e) {
					$('#f-emp').append(
						'<option value="' + frappe.utils.escape_html(e.name) + '">' +
						frappe.utils.escape_html(e.employee_name || e.name) + '</option>'
					);
				});
			}
		});
	}

	set_preset(90);
	update_period_label();

	$('.preset-btn').on('click', function () {
		$('.preset-btn').removeClass('active btn-primary').addClass('btn-default');
		$(this).addClass('active btn-primary').removeClass('btn-default');
		var days = $(this).data('preset');
		if (days === 'all') {
			$('#f-from').val('');
			$('#f-to').val(today);
		} else {
			set_preset(days);
		}
		update_period_label();
		load_data();
	});

	function set_preset(days) {
		$('#f-from').val(frappe.datetime.add_days(today, -days));
		$('#f-to').val(today);
	}

	function update_period_label() {
		var from = $('#f-from').val();
		var to = $('#f-to').val() || today;
		var text = from
			? (__('Reporting period') + '<br><b>' + frappe.utils.escape_html(from) + '</b> → <b>' + frappe.utils.escape_html(to) + '</b>')
			: (__('Reporting period') + '<br><b>' + __('All time') + '</b> → <b>' + frappe.utils.escape_html(to) + '</b>');
		$('#sa-period-label').html(text);
	}

	$('#f-from, #f-to').on('change', function () {
		$('.preset-btn').removeClass('active btn-primary').addClass('btn-default');
		update_period_label();
		load_data();
	});
	$('#f-dept').on('change', function () {
		load_employees();
		load_data();
	});
	$('#f-emp, #f-cat').on('change', function () { load_data(); });
	$('#f-reset').on('click', function () {
		set_preset(90);
		$('.preset-btn').removeClass('active btn-primary').addClass('btn-default');
		$('.preset-btn[data-preset="90"]').addClass('active btn-primary').removeClass('btn-default');
		$('#f-dept, #f-emp, #f-cat').val('');
		update_period_label();
		load_data();
	});

	load_data();

	function load_data() {
		show_loading();
		var filters = {
			from_date: $('#f-from').val() || undefined,
			to_date: $('#f-to').val() || undefined,
			department: $('#f-dept').val() || undefined,
			employee: $('#f-emp').val() || undefined,
			category: $('#f-cat').val() || undefined
		};
		frappe.call({
			method: 'survey_app.survey_analytics.get_analytics',
			args: { filters: filters },
			callback: function (r) {
				if (!r.exc && r.message) {
					data = r.message;
					render(data);
				} else {
					show_empty();
				}
			}
		});
	}

	function show_loading() {
		$('.chart-body').html('<div class="sa-empty"><i class="fa fa-spinner fa-spin fa-2x"></i><div style="margin-top:10px;">' + __('Loading insights...') + '</div></div>');
		$('#sa-summary, #sa-insights').html('');
	}

	function show_empty() {
		$('.chart-body').html('<div class="sa-empty">' + __('No feedback data for this period') + '</div>');
		$('#sa-summary, #sa-insights').html('');
	}

	function render(d) {
		populate_view_controls(d);
		render_summary(d.summary || []);
		render_insights(d.insights || {});
		render_employee_chart(d.by_employee || {});
		bar('ch-cat', d.by_category, '#3d7a7a', false);
		render_department_chart();
		render_competency_by_department();
		pie('ch-rev', d.reviewer_activity);
		over_time(d.over_time);
		render_scorecard();
	}

	function populate_view_controls(d) {
		var cats = (d.categories || (d.scorecard && d.scorecard.categories) || []).slice();
		var deptCatSel = $('#dept-cat-view');
		var currentDeptCat = deptCatSel.val() || '__all__';
		deptCatSel.empty().append('<option value="__all__">' + __('All Categories') + '</option>');
		cats.forEach(function (c) {
			deptCatSel.append(
				'<option value="' + frappe.utils.escape_html(c) + '">' +
				frappe.utils.escape_html(c) + '</option>'
			);
		});
		if (currentDeptCat === '__all__' || cats.indexOf(currentDeptCat) >= 0) {
			deptCatSel.val(currentDeptCat);
		}

		var depts = ((d.competency_by_department || {}).departments || []).slice();
		var compDeptSel = $('#comp-dept-view');
		var currentDept = compDeptSel.val() || '';
		compDeptSel.empty().append('<option value="">' + __('Select department') + '</option>');
		depts.forEach(function (dep) {
			compDeptSel.append(
				'<option value="' + frappe.utils.escape_html(dep) + '">' +
				frappe.utils.escape_html(dep) + '</option>'
			);
		});
		if (currentDept && depts.indexOf(currentDept) >= 0) {
			compDeptSel.val(currentDept);
		} else if (depts.length) {
			compDeptSel.val(depts[0]);
		}

		var scoreSel = $('#scorecard-view');
		var currentScore = scoreSel.val() || '__overall__';
		scoreSel.empty().append(
			'<option value="__overall__">' + __('Average — all skills') + '</option>'
		);
		cats.forEach(function (c) {
			scoreSel.append(
				'<option value="' + frappe.utils.escape_html(c) + '">' +
				frappe.utils.escape_html(c) + '</option>'
			);
		});
		if (currentScore === '__overall__' || cats.indexOf(currentScore) >= 0) {
			scoreSel.val(currentScore);
		}
	}

	function render_department_chart() {
		if (!data) return;
		var pack = data.department_by_category || {};
		var key = $('#dept-cat-view').val() || '__all__';
		var chartData;
		if (key === '__all__') {
			chartData = pack.overall || data.by_department || {};
			$('#ch-dept-sub').text(__('Overall average across all competencies'));
		} else {
			chartData = (pack.by_category && pack.by_category[key]) || { labels: [], values: [] };
			$('#ch-dept-sub').text(__('Department scores for {0}', [key]));
		}
		bar('ch-dept', chartData, '#c58a2e', false);
	}

	function render_competency_by_department() {
		if (!data) return;
		var pack = data.competency_by_department || {};
		var dept = $('#comp-dept-view').val();
		if (!dept) {
			$('#ch-comp-dept-sub').text(__('Select a department to see competency scores'));
			bar('ch-comp-dept', { labels: [], values: [] }, '#2f5f73', false);
			return;
		}
		var chartData = (pack.by_department && pack.by_department[dept]) || { labels: [], values: [] };
		$('#ch-comp-dept-sub').text(__('Competency breakdown for {0}', [dept]));
		bar('ch-comp-dept', chartData, '#2f5f73', false);
	}

	function render_scorecard() {
		if (!data) return;
		var sc = data.scorecard || {};
		var key = $('#scorecard-view').val() || '__overall__';
		var rows;
		if (key === '__overall__') {
			rows = sc.overall || [];
			$('#scorecard-sub').text(__('One row per employee — average of all skills'));
		} else {
			rows = (sc.by_category || []).filter(function (r) { return r.category === key; });
			$('#scorecard-sub').text(__('Scores for skill: {0}', [key]));
		}
		detail_rows_cache = rows;
		render_detail_rows(rows);
	}

	$('#emp-view, #emp-sort').on('change', function () {
		if (data) render_employee_chart(data.by_employee || {});
	});
	$('#dept-cat-view').on('change', function () {
		render_department_chart();
	});
	$('#comp-dept-view').on('change', function () {
		render_competency_by_department();
	});
	$('#scorecard-view').on('change', function () {
		render_scorecard();
	});

	function render_employee_chart(emp_data) {
		var rows = (emp_data.rows || []).slice();
		if (!rows.length && emp_data.labels) {
			rows = emp_data.labels.map(function (label, i) {
				return { employee_name: label, score_pct: emp_data.values[i] };
			});
		}

		var total = rows.length;
		var view = $('#emp-view').val() || 'top15';
		var sort = $('#emp-sort').val() || 'desc';

		rows.sort(function (a, b) {
			return sort === 'asc' ? (a.score_pct - b.score_pct) : (b.score_pct - a.score_pct);
		});

		var shown = rows;
		if (view === 'top15') shown = rows.slice(0, 15);
		else if (view === 'bottom15') {
			var asc = rows.slice().sort(function (a, b) { return a.score_pct - b.score_pct; });
			shown = asc.slice(0, 15);
			if (sort === 'desc') shown.reverse();
		}

		$('#ch-emp-sub').text(
			__('Showing {0} of {1} employees — use controls to change view', [shown.length, total])
		);

		bar('ch-emp', {
			labels: shown.map(function (r) { return r.employee_name; }),
			values: shown.map(function (r) { return r.score_pct; })
		}, '#2f5f73', true);
	}

	function render_summary(cards) {
		var html = '';
		(cards || []).forEach(function (c) {
			var val = (c.datatype === 'Percent') ? c.value + '%' : c.value;
			var ind = c.indicator || 'navy';
			html += '<div class="col-md-3 col-sm-6" style="margin-bottom:14px;">' +
				'<div class="summary-card ind-' + frappe.utils.escape_html(ind) + '">' +
				'<div class="summary-value">' + frappe.utils.escape_html(String(val)) + '</div>' +
				'<div class="summary-label">' + frappe.utils.escape_html(c.label || '') + '</div>' +
				(c.sublabel ? '<div class="summary-sub">' + frappe.utils.escape_html(c.sublabel) + '</div>' : '') +
				'</div></div>';
		});
		$('#sa-summary').html(html || '<div class="col-md-12"><div class="sa-empty">' + __('No summary available') + '</div></div>');
	}

	function render_insights(insights) {
		var cards = [];
		if (insights.top_performer) {
			cards.push({
				cls: 'positive',
				kicker: __('Top Performer'),
				title: insights.top_performer.employee_name,
				meta: insights.top_performer.score_pct + '% · ' + (insights.top_performer.department || '')
			});
		}
		if (insights.needs_attention) {
			cards.push({
				cls: 'watch',
				kicker: __('Needs Attention'),
				title: insights.needs_attention.employee_name,
				meta: insights.needs_attention.score_pct + '% · ' + (insights.needs_attention.department || '')
			});
		}
		if (insights.strongest_category) {
			cards.push({
				cls: 'positive',
				kicker: __('Strongest Competency'),
				title: insights.strongest_category.category,
				meta: insights.strongest_category.score_pct + '% ' + __('organisation average')
			});
		}
		if (insights.development_focus) {
			cards.push({
				cls: 'watch',
				kicker: __('Development Focus'),
				title: insights.development_focus.category,
				meta: insights.development_focus.score_pct + '% ' + __('organisation average')
			});
		}

		if (!cards.length) {
			$('#sa-insights').html('');
			return;
		}

		var html = cards.map(function (c) {
			return '<div class="col-md-3 col-sm-6" style="margin-bottom:14px;">' +
				'<div class="insight-card ' + c.cls + '">' +
				'<div class="insight-kicker">' + frappe.utils.escape_html(c.kicker) + '</div>' +
				'<div class="insight-title">' + frappe.utils.escape_html(c.title || '') + '</div>' +
				'<div class="insight-meta">' + frappe.utils.escape_html(c.meta || '') + '</div>' +
				'</div></div>';
		}).join('');
		$('#sa-insights').html(html);
	}

	function bar(id, d, color, horizontal) {
		var el = document.getElementById(id);
		if (!el) return;
		el.innerHTML = '';
		if (!d || !d.labels || !d.labels.length) {
			el.innerHTML = '<div class="sa-empty">' + __('No data') + '</div>';
			return;
		}
		el.innerHTML = '<div id="' + id + '-c"></div>';
		var count = d.labels.length;
		var height = horizontal ? Math.max(280, Math.min(count * 28, 1200)) : 300;
		new frappe.Chart('#' + id + '-c', {
			data: { labels: d.labels, datasets: [{ values: d.values }] },
			type: 'bar',
			height: height,
			colors: [color],
			barOptions: {
				spaceRatio: horizontal ? 0.25 : 0.35,
				horizontal: !!horizontal
			},
			axisOptions: { xAxisMode: 'tick', xIsSeries: !horizontal },
			tooltipOptions: { formatTooltipY: function (v) { return v + '%'; } }
		});
	}

	function pie(id, d) {
		var el = document.getElementById(id);
		if (!el) return;
		el.innerHTML = '';
		if (!d || !d.labels || !d.labels.length) {
			el.innerHTML = '<div class="sa-empty">' + __('No data') + '</div>';
			return;
		}

		// Cap pie slices for readability at org scale
		var labels = d.labels.slice();
		var values = d.values.slice();
		var pairs = labels.map(function (label, i) { return { label: label, value: values[i] || 0 }; });
		pairs.sort(function (a, b) { return b.value - a.value; });
		if (pairs.length > 8) {
			var top = pairs.slice(0, 7);
			var other = pairs.slice(7).reduce(function (sum, p) { return sum + p.value; }, 0);
			top.push({ label: __('Others'), value: other });
			pairs = top;
		}

		el.innerHTML = '<div id="' + id + '-c"></div>';
		new frappe.Chart('#' + id + '-c', {
			data: {
				labels: pairs.map(function (p) { return p.label; }),
				datasets: [{ values: pairs.map(function (p) { return p.value; }) }]
			},
			type: 'pie',
			height: 300,
			colors: ['#2f5f73', '#3d7a7a', '#c58a2e', '#6d8b9c', '#8aa39a', '#b08968', '#5b6b7a', '#9bb0a5']
		});
	}

	function over_time(d) {
		var el = document.getElementById('ch-time');
		if (!el) return;
		el.innerHTML = '';
		if (!d || !d.labels || !d.labels.length) {
			el.innerHTML = '<div class="sa-empty">' + __('No data') + '</div>';
			return;
		}
		el.innerHTML = '<div id="ch-time-c"></div>';
		new frappe.Chart('#ch-time-c', {
			data: {
				labels: d.labels,
				datasets: [
					{ name: __('Responses'), values: d.responses, chartType: 'bar' },
					{ name: __('Avg Score'), values: d.avg_score, chartType: 'line' }
				]
			},
			type: 'axis-mixed',
			height: 300,
			colors: ['#2f5f73', '#2f8f6b'],
			axisOptions: { xAxisMode: 'tick', xIsSeries: true },
			lineOptions: { hideDots: 0, heatline: 1, regionFill: 1 }
		});
	}

	var detail_sort = { key: 'score_pct', order: 'desc' };
	var detail_rows_cache = [];

	$('#tbl-detail').on('click', 'th[data-sort]', function () {
		var key = $(this).data('sort');
		if (detail_sort.key === key) {
			detail_sort.order = detail_sort.order === 'asc' ? 'desc' : 'asc';
		} else {
			detail_sort.key = key;
			detail_sort.order = key === 'score_pct' ? 'desc' : 'asc';
		}
		render_detail_rows(detail_rows_cache);
	});

	function band_for(pct) {
		if (pct >= 70) return { cls: 'band-high', label: __('Strong') };
		if (pct >= 50) return { cls: 'band-mid', label: __('Developing') };
		return { cls: 'band-low', label: __('At Risk') };
	}

	function detail(d) {
		var seen = {};
		var rows = [];
		(d || []).forEach(function (r) {
			var key = r.employee + '|' + r.category;
			if (!seen[key]) {
				seen[key] = true;
				rows.push(r);
			}
		});
		detail_rows_cache = rows;
		render_detail_rows(rows);
	}

	function render_detail_rows(rows) {
		var tbody = document.querySelector('#tbl-detail tbody');
		if (!tbody) return;
		tbody.innerHTML = '';
		if (!rows || !rows.length) {
			tbody.innerHTML = '<tr><td colspan="5" class="sa-empty">' + __('No scorecard rows for this period') + '</td></tr>';
			return;
		}

		$('#tbl-detail thead th[data-sort]').removeClass('active');
		$('#tbl-detail thead th[data-sort="' + detail_sort.key + '"]').addClass('active');

		var sorted = rows.slice().sort(function (a, b) {
			var av = a[detail_sort.key];
			var bv = b[detail_sort.key];
			if (typeof av === 'number' && typeof bv === 'number') {
				return detail_sort.order === 'asc' ? av - bv : bv - av;
			}
			av = String(av || '').toLowerCase();
			bv = String(bv || '').toLowerCase();
			if (av < bv) return detail_sort.order === 'asc' ? -1 : 1;
			if (av > bv) return detail_sort.order === 'asc' ? 1 : -1;
			return 0;
		});

		sorted.slice(0, 100).forEach(function (r) {
			var band = band_for(r.score_pct || 0);
			tbody.innerHTML +=
				'<tr>' +
				'<td><b>' + frappe.utils.escape_html(r.employee_name || '') + '</b></td>' +
				'<td>' + frappe.utils.escape_html(r.department || '') + '</td>' +
				'<td>' + frappe.utils.escape_html(r.category || '') + '</td>' +
				'<td><b>' + frappe.utils.escape_html(String(r.score_pct)) + '%</b></td>' +
				'<td><span class="band ' + band.cls + '">' + band.label + '</span></td>' +
				'</tr>';
		});
	}
};

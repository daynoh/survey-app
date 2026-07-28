frappe.pages['outstanding-surveys'].on_page_load = function (wrapper) {
	var page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __('Outstanding Surveys'),
		single_column: true
	});
	frappe.breadcrumbs.add('Survey App');

	var state = {
		rows: [],
		sort_by: 'days_pending',
		sort_order: 'desc',
		selected: {}
	};

	$(page.main).css({ padding: '0', background: '#f3f5f7' }).html(`
		<div class="os-root">
			<div class="os-hero">
				<div>
					<div class="os-eyebrow">${__('Follow-up')}</div>
					<h1>${__('Outstanding Surveys')}</h1>
					<p>${__('People who still need to complete surveys that were sent to them. Sort, select, and send reminders.')}</p>
				</div>
				<div class="os-stats" id="os-stats"></div>
			</div>

			<div class="os-toolbar">
				<div class="os-filters">
					<select class="form-control input-sm" id="os-dept"><option value="">${__('All Departments')}</option></select>
					<input type="number" class="form-control input-sm" id="os-min-days" min="0" placeholder="${__('Min days pending')}" style="width:140px;">
					<select class="form-control input-sm" id="os-sort">
						<option value="days_pending:desc">${__('Sort: Days pending (high → low)')}</option>
						<option value="days_pending:asc">${__('Sort: Days pending (low → high)')}</option>
						<option value="sent_on:asc">${__('Sort: Sent date (oldest)')}</option>
						<option value="sent_on:desc">${__('Sort: Sent date (newest)')}</option>
						<option value="reviewer_name:asc">${__('Sort: Reviewer A–Z')}</option>
						<option value="reviewer_name:desc">${__('Sort: Reviewer Z–A')}</option>
						<option value="reviewee_name:asc">${__('Sort: Reviewee A–Z')}</option>
						<option value="department:asc">${__('Sort: Department A–Z')}</option>
					</select>
					<button class="btn btn-default btn-sm" id="os-refresh"><i class="fa fa-refresh"></i> ${__('Refresh')}</button>
				</div>
				<div class="os-actions">
					<button class="btn btn-default btn-sm" id="os-remind-selected" disabled>
						<i class="fa fa-bell"></i> ${__('Remind Selected')}
					</button>
					<button class="btn btn-primary btn-sm" id="os-remind-all">
						<i class="fa fa-envelope"></i> ${__('Remind All')}
					</button>
				</div>
			</div>

			<div class="os-body">
				<div class="os-panel">
					<div class="table-responsive">
						<table class="table table-hover" id="os-table">
							<thead>
								<tr>
									<th style="width:36px;"><input type="checkbox" id="os-check-all"></th>
									<th data-sort="reviewer_name">${__('Reviewer')}</th>
									<th data-sort="reviewee_name">${__('Reviewee')}</th>
									<th data-sort="department">${__('Department')}</th>
									<th data-sort="sent_on">${__('Sent On')}</th>
									<th data-sort="days_pending">${__('Days Pending')}</th>
									<th>${__('Survey')}</th>
									<th></th>
								</tr>
							</thead>
							<tbody></tbody>
						</table>
					</div>
				</div>
			</div>
		</div>
		<style>
			.os-root { font-family: "IBM Plex Sans", "Segoe UI", Arial, sans-serif; color: #243342; }
			.os-hero {
				background: linear-gradient(135deg, #1f3a4d 0%, #2f5f73 60%, #3d7a7a 100%);
				color: #fff; padding: 26px 28px; display:flex; justify-content:space-between; gap:20px; align-items:flex-end;
			}
			.os-eyebrow { font-size:11px; letter-spacing:1.1px; text-transform:uppercase; opacity:.8; font-weight:650; margin-bottom:6px; }
			.os-hero h1 { margin:0 0 6px; font-size:26px; font-weight:650; }
			.os-hero p { margin:0; opacity:.9; max-width:560px; font-size:13px; }
			.os-stats { display:flex; gap:10px; }
			.os-stat {
				background: rgba(255,255,255,.12); border:1px solid rgba(255,255,255,.18);
				border-radius:10px; padding:10px 14px; min-width:110px; text-align:center;
			}
			.os-stat .v { font-size:22px; font-weight:700; }
			.os-stat .l { font-size:11px; opacity:.85; }
			.os-toolbar {
				background:#fff; border-bottom:1px solid #e2e8ee; padding:12px 20px;
				display:flex; justify-content:space-between; gap:12px; flex-wrap:wrap; align-items:center;
				position:sticky; top:0; z-index:5;
			}
			.os-filters, .os-actions { display:flex; gap:8px; flex-wrap:wrap; align-items:center; }
			.os-filters select, .os-filters input { width:210px; }
			.os-body { padding:18px 20px 32px; }
			.os-panel {
				background:#fff; border:1px solid #e2e8ee; border-radius:12px;
				box-shadow:0 1px 2px rgba(31,58,77,.04); overflow:hidden;
			}
			#os-table { margin:0; font-size:12px; }
			#os-table thead th {
				background:#f7f9fb; border-top:none; padding:11px 12px; color:#5b6b7a;
				font-size:10px; text-transform:uppercase; letter-spacing:.5px; cursor:pointer; user-select:none;
			}
			#os-table thead th[data-sort].active { color:#2f5f73; }
			#os-table td { padding:10px 12px; vertical-align:middle; }
			.days-pill {
				display:inline-block; min-width:42px; text-align:center; padding:2px 8px;
				border-radius:999px; font-weight:650; font-size:11px;
			}
			.days-ok { background:#e7f6ef; color:#1f7a55; }
			.days-warn { background:#fff4e5; color:#9a6700; }
			.days-late { background:#fdecea; color:#b42318; }
			.os-empty { text-align:center; padding:48px 16px; color:#8a97a4; }
		</style>
	`);

	page.add_inner_button(__('Refresh'), function () { load(); });

	frappe.call({
		method: 'frappe.client.get_list',
		args: { doctype: 'Department', fields: ['name'], limit_page_length: 200, order_by: 'name asc' },
		callback: function (r) {
			(r.message || []).forEach(function (d) {
				$('#os-dept').append(
					'<option value="' + frappe.utils.escape_html(d.name) + '">' +
					frappe.utils.escape_html(d.name) + '</option>'
				);
			});
		}
	});

	$('#os-refresh, #os-dept, #os-min-days, #os-sort').on('change click', function (e) {
		if (e.type === 'click' && e.currentTarget.id !== 'os-refresh') return;
		load();
	});
	$('#os-dept, #os-min-days, #os-sort').on('change', load);

	$('#os-check-all').on('change', function () {
		var checked = $(this).is(':checked');
		state.selected = {};
		$('#os-table tbody .os-row-check').prop('checked', checked).each(function () {
			if (checked) state.selected[$(this).val()] = true;
		});
		update_selected_btn();
	});

	$('#os-table').on('change', '.os-row-check', function () {
		var name = $(this).val();
		if ($(this).is(':checked')) state.selected[name] = true;
		else delete state.selected[name];
		update_selected_btn();
	});

	$('#os-table').on('click', 'th[data-sort]', function () {
		var key = $(this).data('sort');
		if (state.sort_by === key) {
			state.sort_order = state.sort_order === 'asc' ? 'desc' : 'asc';
		} else {
			state.sort_by = key;
			state.sort_order = key === 'days_pending' ? 'desc' : 'asc';
		}
		$('#os-sort').val(state.sort_by + ':' + state.sort_order);
		load();
	});

	$('#os-remind-selected').on('click', function () {
		var surveys = Object.keys(state.selected);
		if (!surveys.length) return;
		frappe.confirm(__('Send reminders for {0} selected survey(s)?', [surveys.length]), function () {
			send_reminders(surveys, 0);
		});
	});

	$('#os-remind-all').on('click', function () {
		frappe.confirm(__('Send reminders to all people with outstanding surveys?'), function () {
			send_reminders([], 1);
		});
	});

	$('#os-table').on('click', '.os-remind-one', function () {
		var survey = $(this).data('survey');
		frappe.confirm(__('Send a reminder for this survey?'), function () {
			send_reminders([survey], 0);
		});
	});

	function update_selected_btn() {
		var n = Object.keys(state.selected).length;
		$('#os-remind-selected').prop('disabled', !n)
			.text(n ? __('Remind Selected ({0})', [n]) : __('Remind Selected'));
	}

	function load() {
		var sort = ($('#os-sort').val() || 'days_pending:desc').split(':');
		state.sort_by = sort[0];
		state.sort_order = sort[1] || 'desc';
		state.selected = {};
		update_selected_btn();
		$('#os-check-all').prop('checked', false);

		$('#os-table tbody').html(
			'<tr><td colspan="8" class="os-empty"><i class="fa fa-spinner fa-spin"></i> ' +
			__('Loading...') + '</td></tr>'
		);

		frappe.call({
			method: 'survey_app.outstanding.get_outstanding_surveys',
			args: {
				filters: {
					department: $('#os-dept').val() || undefined,
					min_days: $('#os-min-days').val() || undefined
				},
				sort_by: state.sort_by,
				sort_order: state.sort_order
			},
			callback: function (r) {
				if (r.exc || !r.message) {
					$('#os-table tbody').html('<tr><td colspan="8" class="os-empty">' + __('Failed to load') + '</td></tr>');
					return;
				}
				state.rows = r.message.rows || [];
				render_stats(r.message);
				render_rows(state.rows);
			}
		});
	}

	function render_stats(data) {
		$('#os-stats').html(
			'<div class="os-stat"><div class="v">' + (data.total || 0) + '</div><div class="l">' + __('Pending surveys') + '</div></div>' +
			'<div class="os-stat"><div class="v">' + (data.reviewers_pending || 0) + '</div><div class="l">' + __('People to remind') + '</div></div>'
		);
	}

	function days_class(d) {
		if (d >= 7) return 'days-late';
		if (d >= 3) return 'days-warn';
		return 'days-ok';
	}

	function render_rows(rows) {
		var $tb = $('#os-table tbody').empty();
		if (!rows.length) {
			$tb.html('<tr><td colspan="8" class="os-empty">' + __('All caught up — no outstanding surveys.') + '</td></tr>');
			return;
		}

		$('#os-table thead th[data-sort]').removeClass('active');
		$('#os-table thead th[data-sort="' + state.sort_by + '"]').addClass('active');

		rows.forEach(function (row) {
			var sent = (row.sent_on || '').split(' ')[0] || '—';
			$tb.append(`
				<tr>
					<td><input type="checkbox" class="os-row-check" value="${frappe.utils.escape_html(row.survey)}"></td>
					<td>
						<b>${frappe.utils.escape_html(row.reviewer_name || '')}</b><br>
						<small class="text-muted">${frappe.utils.escape_html(row.reviewer_email || '')}</small>
					</td>
					<td>${frappe.utils.escape_html(row.reviewee_name || '')}</td>
					<td>${frappe.utils.escape_html(row.department || '')}</td>
					<td>${frappe.utils.escape_html(sent)}</td>
					<td><span class="days-pill ${days_class(row.days_pending)}">${row.days_pending}</span></td>
					<td>
						<a href="/app/survey/${encodeURIComponent(row.survey)}">${frappe.utils.escape_html(row.survey)}</a><br>
						<small class="text-muted">${frappe.utils.escape_html(row.title || '')}</small>
					</td>
					<td class="text-right">
						<a class="btn btn-xs btn-default" href="${frappe.utils.escape_html(row.survey_url || '#')}" target="_blank">${__('Open')}</a>
						<button class="btn btn-xs btn-primary os-remind-one" data-survey="${frappe.utils.escape_html(row.survey)}">
							<i class="fa fa-bell"></i> ${__('Remind')}
						</button>
					</td>
				</tr>
			`);
		});
	}

	function send_reminders(surveys, remind_all) {
		frappe.call({
			method: 'survey_app.outstanding.send_survey_reminders',
			args: { surveys: surveys, remind_all: remind_all },
			freeze: true,
			freeze_message: __('Sending reminders...'),
			callback: function (r) {
				if (r.exc || !r.message) return;
				var m = r.message;
				frappe.show_alert({
					message: __('Reminders sent: {0}. Skipped: {1}. Failed: {2}.', [m.sent || 0, m.skipped || 0, m.failed || 0]),
					indicator: (m.failed ? 'orange' : 'green')
				});
				load();
			}
		});
	}

	load();
};

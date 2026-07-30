frappe.pages['outstanding-surveys'].on_page_load = function (wrapper) {
	var page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __('Outstanding Surveys'),
		single_column: true
	});
	frappe.breadcrumbs.add('Survey App');

	var state = {
		rows: [],
		groups: [],
		sort_by: 'days_pending',
		sort_order: 'desc',
		selected: {},
		collapsed: {}
	};

	$(page.main).css({ padding: '0', background: '#f3f5f7' }).html(`
		<div class="os-root">
			<div class="os-hero">
				<div>
					<div class="os-eyebrow">${__('Follow-up')}</div>
					<h1>${__('Outstanding Surveys')}</h1>
					<p>${__('Outstanding surveys grouped by Survey Cycle. Sort, select, and send reminders.')}</p>
				</div>
				<div class="os-stats" id="os-stats"></div>
			</div>

			<div class="os-toolbar">
				<div class="os-filters">
					<select class="form-control input-sm" id="os-cycle"><option value="">${__('All Cycles')}</option></select>
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
				<div id="os-groups"></div>
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
			.os-body { padding:18px 20px 32px; display:flex; flex-direction:column; gap:16px; }
			.os-panel {
				background:#fff; border:1px solid #e2e8ee; border-radius:12px;
				box-shadow:0 1px 2px rgba(31,58,77,.04); overflow:hidden;
			}
			.os-cycle-head {
				display:flex; justify-content:space-between; gap:12px; align-items:center;
				padding:14px 16px; background:#f7f9fb; border-bottom:1px solid #e2e8ee; cursor:pointer;
			}
			.os-cycle-head:hover { background:#f0f4f7; }
			.os-cycle-head h2 { margin:0; font-size:15px; font-weight:650; color:#1f3a4d; }
			.os-cycle-meta { font-size:12px; color:#5b6b7a; margin-top:3px; }
			.os-cycle-badges { display:flex; gap:8px; align-items:center; flex-wrap:wrap; }
			.os-badge {
				display:inline-block; padding:3px 9px; border-radius:999px; font-size:11px; font-weight:650;
				background:#e8eef2; color:#2f5f73;
			}
			.os-badge-open { background:#e7f6ef; color:#1f7a55; }
			.os-badge-closed { background:#eef0f2; color:#5b6b7a; }
			.os-badge-count { background:#2f5f73; color:#fff; }
			.os-table { margin:0; font-size:12px; }
			.os-table thead th {
				background:#fafbfc; border-top:none; padding:11px 12px; color:#5b6b7a;
				font-size:10px; text-transform:uppercase; letter-spacing:.5px; cursor:pointer; user-select:none;
			}
			.os-table thead th[data-sort].active { color:#2f5f73; }
			.os-table td { padding:10px 12px; vertical-align:middle; }
			.days-pill {
				display:inline-block; min-width:42px; text-align:center; padding:2px 8px;
				border-radius:999px; font-weight:650; font-size:11px;
			}
			.days-ok { background:#e7f6ef; color:#1f7a55; }
			.days-warn { background:#fff4e5; color:#9a6700; }
			.days-late { background:#fdecea; color:#b42318; }
			.os-empty { text-align:center; padding:48px 16px; color:#8a97a4; }
			.os-cycle-body.collapsed { display:none; }
			.os-chevron { color:#8a97a4; margin-right:8px; }
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

	$('#os-refresh').on('click', load);
	$('#os-cycle, #os-dept, #os-min-days, #os-sort').on('change', load);

	$('#os-groups').on('change', '.os-check-all-group', function () {
		var groupId = $(this).data('group');
		var checked = $(this).is(':checked');
		$('#os-groups .os-row-check[data-group="' + groupId + '"]').prop('checked', checked).each(function () {
			if (checked) state.selected[$(this).val()] = true;
			else delete state.selected[$(this).val()];
		});
		update_selected_btn();
	});

	$('#os-groups').on('change', '.os-row-check', function () {
		var name = $(this).val();
		if ($(this).is(':checked')) state.selected[name] = true;
		else delete state.selected[name];
		update_selected_btn();
	});

	$('#os-groups').on('click', 'th[data-sort]', function () {
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

	$('#os-groups').on('click', '.os-cycle-head', function (e) {
		if ($(e.target).is('input, a, button, label')) return;
		var key = String($(this).data('group'));
		state.collapsed[key] = !state.collapsed[key];
		$(this).closest('.os-panel').find('.os-cycle-body').toggleClass('collapsed', !!state.collapsed[key]);
		$(this).find('.os-chevron')
			.toggleClass('fa-chevron-down', !state.collapsed[key])
			.toggleClass('fa-chevron-right', !!state.collapsed[key]);
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

	$('#os-groups').on('click', '.os-remind-one', function () {
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

		$('#os-groups').html(
			'<div class="os-panel"><div class="os-empty"><i class="fa fa-spinner fa-spin"></i> ' +
			__('Loading...') + '</div></div>'
		);

		frappe.call({
			method: 'survey_app.outstanding.get_outstanding_surveys',
			args: {
				filters: {
					cycle: $('#os-cycle').val() || undefined,
					department: $('#os-dept').val() || undefined,
					min_days: $('#os-min-days').val() || undefined
				},
				sort_by: state.sort_by,
				sort_order: state.sort_order
			},
			callback: function (r) {
				if (r.exc || !r.message) {
					$('#os-groups').html('<div class="os-panel"><div class="os-empty">' + __('Failed to load') + '</div></div>');
					return;
				}
				state.rows = r.message.rows || [];
				state.groups = r.message.groups || [];
				populate_cycle_filter(r.message.cycles || []);
				render_stats(r.message);
				render_groups(state.groups);
			}
		});
	}

	function populate_cycle_filter(cycles) {
		var $sel = $('#os-cycle');
		var current = $sel.val() || '';
		var html = '<option value="">' + __('All Cycles') + '</option>';
		html += '<option value="__none__">' + __('No Cycle') + '</option>';
		(cycles || []).forEach(function (c) {
			var label = (c.title || c.name) +
				(c.period_start && c.period_end ? ' (' + c.period_start + ' → ' + c.period_end + ')' : '') +
				(c.status ? ' · ' + c.status : '');
			html += '<option value="' + frappe.utils.escape_html(c.name) + '">' +
				frappe.utils.escape_html(label) + '</option>';
		});
		$sel.html(html);
		if (current) $sel.val(current);
	}

	function render_stats(data) {
		var cyclesWithPending = (data.groups || []).filter(function (g) { return g.cycle; }).length;
		$('#os-stats').html(
			'<div class="os-stat"><div class="v">' + (data.total || 0) + '</div><div class="l">' + __('Pending surveys') + '</div></div>' +
			'<div class="os-stat"><div class="v">' + (data.reviewers_pending || 0) + '</div><div class="l">' + __('People to remind') + '</div></div>' +
			'<div class="os-stat"><div class="v">' + cyclesWithPending + '</div><div class="l">' + __('Cycles') + '</div></div>'
		);
	}

	function days_class(d) {
		if (d >= 7) return 'days-late';
		if (d >= 3) return 'days-warn';
		return 'days-ok';
	}

	function status_badge(status) {
		if (!status) return '';
		var cls = status === 'Open' ? 'os-badge-open' : 'os-badge-closed';
		return '<span class="os-badge ' + cls + '">' + frappe.utils.escape_html(status) + '</span>';
	}

	function render_groups(groups) {
		var $root = $('#os-groups').empty();
		if (!groups.length) {
			$root.html('<div class="os-panel"><div class="os-empty">' + __('All caught up — no outstanding surveys.') + '</div></div>');
			return;
		}

		groups.forEach(function (group) {
			var groupKey = group.cycle || '__none__';
			var collapsed = !!state.collapsed[groupKey];
			var period = '';
			if (group.cycle_period_start || group.cycle_period_end) {
				period = (group.cycle_period_start || '—') + ' → ' + (group.cycle_period_end || '—');
			}
			var metaParts = [];
			if (group.cycle) metaParts.push(group.cycle);
			if (period) metaParts.push(period);
			if (group.completeness_cycle) metaParts.push(group.completeness_cycle);

			var $panel = $(`
				<div class="os-panel" data-group="${frappe.utils.escape_html(groupKey)}">
					<div class="os-cycle-head" data-group="${frappe.utils.escape_html(groupKey)}">
						<div>
							<h2>
								<i class="fa os-chevron ${collapsed ? 'fa-chevron-right' : 'fa-chevron-down'}"></i>
								${frappe.utils.escape_html(group.cycle_title || __('No Cycle'))}
							</h2>
							<div class="os-cycle-meta">${frappe.utils.escape_html(metaParts.join(' · ') || __('Surveys not linked to a cycle'))}</div>
						</div>
						<div class="os-cycle-badges">
							${status_badge(group.cycle_status)}
							<span class="os-badge os-badge-count">${group.pending_count || 0} ${__('pending')}</span>
							<label class="os-badge" style="cursor:pointer;margin:0;">
								<input type="checkbox" class="os-check-all-group" data-group="${frappe.utils.escape_html(groupKey)}" style="margin-right:4px;">
								${__('Select all')}
							</label>
						</div>
					</div>
					<div class="os-cycle-body ${collapsed ? 'collapsed' : ''}">
						<div class="table-responsive">
							<table class="table table-hover os-table">
								<thead>
									<tr>
										<th style="width:36px;"></th>
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
			`);

			var $tb = $panel.find('tbody');
			(group.rows || []).forEach(function (row) {
				var sent = (row.sent_on || '').split(' ')[0] || '—';
				$tb.append(`
					<tr>
						<td><input type="checkbox" class="os-row-check" data-group="${frappe.utils.escape_html(groupKey)}" value="${frappe.utils.escape_html(row.survey)}"></td>
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

			$panel.find('th[data-sort="' + state.sort_by + '"]').addClass('active');
			$root.append($panel);
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

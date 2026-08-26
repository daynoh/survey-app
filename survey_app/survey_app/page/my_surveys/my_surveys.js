frappe.pages['my-surveys'].on_page_load = function (wrapper) {
	var page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __('My Surveys'),
		single_column: true
	});
	frappe.breadcrumbs.add('Survey App');

	$(wrapper).find('.layout-side-section').hide();
	$(wrapper).find('.layout-main-section-wrapper').removeClass('col-md-10 col-lg-10').addClass('col-md-12');
	var $main = $(page.main).css({ padding: 0, background: '#f5f5f2' });
	var selectedPeriod = null;
	var selectedFromDate = '';
	var selectedToDate = '';

	page.set_primary_action(__('Refresh'), function () {
		load(selectedPeriod, selectedFromDate, selectedToDate);
	}, 'refresh');

	function esc(value) {
		return frappe.utils.escape_html(String(value == null ? '' : value));
	}

	function number(value, fallback) {
		var parsed = parseFloat(value);
		return Number.isFinite(parsed) ? parsed : (fallback || 0);
	}

	function clamp(value) {
		return Math.max(0, Math.min(100, number(value)));
	}

	function ordinal(value) {
		var rounded = Math.round(number(value));
		var remainder100 = rounded % 100;
		var suffix = (remainder100 >= 11 && remainder100 <= 13)
			? 'th'
			: ({ 1: 'st', 2: 'nd', 3: 'rd' }[rounded % 10] || 'th');
		return rounded + suffix;
	}

	function dateOnly(value) {
		if (!value) return '—';
		return esc(String(value).split(' ')[0]);
	}

	function periodLabel(period) {
		if (!period) return '';
		var dates = period.period_start || period.period_end
			? dateOnly(period.period_start) + ' – ' + dateOnly(period.period_end)
			: '';
		return esc(period.label || period.key) + (dates ? ' · ' + dates : '');
	}

	function initials(name) {
		var parts = String(name || '?').trim().split(/\s+/).filter(Boolean);
		return parts.slice(0, 2).map(function (part) {
			return part.charAt(0).toUpperCase();
		}).join('') || '?';
	}

	function shell() {
		$main.html(`
			<div class="ms-root">
				<div class="ms-loading">
					<div class="ms-spinner"></div>
					<div>${__('Loading your survey dashboard...')}</div>
				</div>
			</div>
			${styles()}
		`);
	}

	function render(data) {
		if (!data || data.state === 'no_employee') {
			renderState(
				__('Employee profile not linked'),
				__('Your ERP login is not linked to an Employee record. Ask HR to set your login in Employee → User ID.'),
				'user-times'
			);
			return;
		}
		if (data.state === 'inactive_employee') {
			renderState(
				__('Employee profile is inactive'),
				__('Survey information is available only for active employee profiles. Contact HR if your status should be active.'),
				'pause-circle'
			);
			return;
		}

		var profile = data.profile || {};
		var assignments = data.assignments || {};
		var activityFilter = data.activity_filter || {};
		var active = data.active_cycle;
		selectedFromDate = activityFilter.from_date || '';
		selectedToDate = activityFilter.to_date || '';
		var avatar = profile.image
			? `<img src="${esc(profile.image)}" alt="${esc(profile.employee_name)}">`
			: `<span>${esc(initials(profile.employee_name))}</span>`;
		var cycleStatus = active
			? `<div class="ms-cycle-context">
					<div class="ms-cycle-label"><span class="ms-status-dot"></span>${__('Active assessment cycle')}</div>
					<strong>${esc(active.title)}</strong>
					<span>${dateOnly(active.period_start)} – ${dateOnly(active.period_end)}</span>
			   </div>`
			: `<div class="ms-cycle-context muted">
					<div class="ms-cycle-label">${__('Assessment cycle')}</div>
					<strong>${__('No active cycle')}</strong>
					<span>${__('There is no current collection period')}</span>
			   </div>`;

		$main.html(`
			<div class="ms-root">
				<header class="ms-masthead">
					<div class="ms-accent-rule"><span></span></div>
					<div class="ms-header-inner">
						<div class="ms-document-line">
							<span>${__('Personal & confidential')}</span>
							<span>${__('360° feedback portfolio')}</span>
						</div>
						<div class="ms-identity-row">
							<div class="ms-profile">
								<div class="ms-avatar">${avatar}</div>
								<div>
									<div class="ms-eyebrow">${__('My survey dashboard')}</div>
									<h1>${esc(profile.employee_name)}</h1>
									<p>${esc(profile.designation || __('Employee'))}${profile.department ? '<span></span>' + esc(profile.department) : ''}</p>
								</div>
							</div>
							${cycleStatus}
						</div>
					</div>
				</header>

					<main class="ms-content">
						<div class="ms-control-bar">
							<div class="ms-filter-fields">
								<div class="ms-period-control">
									<label for="ms-period">${__('Results period')}</label>
									<select id="ms-period" class="form-control input-sm" ${data.periods && data.periods.length ? '' : 'disabled'}>
										${periodOptions(data.periods || [], data.selected_period)}
									</select>
									<small>${__('Controls released scores and benchmarks')}</small>
								</div>
								<div class="ms-date-control">
									<label>${__('Survey activity date range')}</label>
									<div class="ms-date-row">
										<div class="ms-date-inputs">
											<input id="ms-from-date" class="form-control input-sm" type="date" value="${esc(selectedFromDate)}" aria-label="${__('Activity from date')}">
											<span>${__('to')}</span>
											<input id="ms-to-date" class="form-control input-sm" type="date" value="${esc(selectedToDate)}" aria-label="${__('Activity to date')}">
										</div>
										<div class="ms-filter-actions">
											<button class="btn btn-primary btn-sm" id="ms-apply-dates">${__('Apply')}</button>
											<button class="btn btn-default btn-sm" id="ms-clear-dates" ${activityFilter.active ? '' : 'disabled'}>${__('Clear')}</button>
										</div>
									</div>
									<small>${__('Filters pending and completed survey activity')}</small>
								</div>
							</div>
							<div class="ms-privacy"><i class="fa fa-lock"></i><span>${__('This view contains aggregate feedback only. Reviewer identities, comments and individual answers remain private.')}</span></div>
						</div>
						${renderResults(data.results || {}, data.selected_period, data.trend || [])}
						${renderAssignments(assignments)}
				</main>
				<footer class="ms-footer"><span>${__('Personal & confidential')}</span><span>${__('My Surveys · 360° feedback')}</span></footer>
			</div>
			${styles()}
		`);

		$main.find('#ms-period').on('change', function () {
			selectedPeriod = $(this).val() || null;
			load(selectedPeriod, selectedFromDate, selectedToDate);
		});
		$main.find('#ms-apply-dates').on('click', applyDateFilter);
		$main.find('#ms-from-date, #ms-to-date').on('keydown', function (event) {
			if (event.key === 'Enter') applyDateFilter();
		});
		$main.find('#ms-clear-dates').on('click', function () {
			selectedFromDate = '';
			selectedToDate = '';
			load(selectedPeriod);
		});
		$main.find('.ms-trend-chip').on('click', function () {
			selectedPeriod = $(this).attr('data-period') || null;
			load(selectedPeriod, selectedFromDate, selectedToDate);
		});
	}

	function applyDateFilter() {
		var fromDate = $main.find('#ms-from-date').val() || '';
		var toDate = $main.find('#ms-to-date').val() || '';
		if (fromDate && toDate && fromDate > toDate) {
			frappe.msgprint({
				title: __('Invalid date range'),
				message: __('The activity start date cannot be after the end date.'),
				indicator: 'red'
			});
			return;
		}
		selectedFromDate = fromDate;
		selectedToDate = toDate;
		load(selectedPeriod, selectedFromDate, selectedToDate);
	}

	function periodOptions(periods, selected) {
		if (!periods.length) return `<option value="">${__('No released results')}</option>`;
		return periods.map(function (period) {
			var isSelected = selected && selected.key === period.key ? 'selected' : '';
			return `<option value="${esc(period.key)}" ${isSelected}>${periodLabel(period)}</option>`;
		}).join('');
	}

	function renderResults(results, period, trend) {
		if (results.state !== 'released') {
			var locked = results.state === 'locked';
			return `
				<section class="ms-section">
					${sectionHeading('01', __('Performance overview'), period ? periodLabel(period) : __('Your released feedback summary'))}
					<div class="ms-empty compact">
						<div class="ms-empty-icon"><i class="fa fa-${locked ? 'lock' : 'line-chart'}"></i></div>
						<h3>${locked ? __('Results not released yet') : __('No results to display')}</h3>
						<p>${esc(results.message || __('No scored feedback is available yet.'))}</p>
					</div>
				</section>`;
		}

		var delta = results.delta;
		var deltaText = delta == null
			? __('No prior-cycle comparison')
			: (number(delta) > 0 ? '+' : '') + number(delta).toFixed(1) + ' ' + __('pts vs prior cycle');
		var percentile = results.overall_percentile == null ? '—' : ordinal(results.overall_percentile);
		var reviewers = number(results.reviewer_count);
		var expected = number(results.expected_reviews);
		var reviewerSub = expected ? __('{0} of {1} expected', [reviewers, expected]) : __('Completed colleague reviews');
		var orgAverage = results.org_overall_avg == null ? '—' : number(results.org_overall_avg).toFixed(1) + '%';

		return `
			<section class="ms-section">
				${sectionHeading('01', __('Performance overview'), periodLabel(period), `<span class="ms-released"><i class="fa fa-check"></i>${__('Released')}</span>`)}
				<div class="ms-scoreboard">
					${kpi(__('Overall score'), number(results.overall_pct).toFixed(1) + '%', deltaText, 'featured')}
					${kpi(__('Organisation percentile'), percentile, results.org_headcount ? __('Across {0} employees', [results.org_headcount]) : __('Awaiting benchmark data'))}
					${kpi(__('Reviews received'), reviewers, reviewerSub)}
					${kpi(__('Organisation average'), orgAverage, __('Same released period'))}
				</div>
				<div class="ms-analytics-row">
					<div class="ms-panel ms-trend-panel">
						<div class="ms-panel-head">
							<div><h3>${__('Performance trend')}</h3><p>${__('Your released results across available survey periods')}</p></div>
							<div class="ms-legend"><span class="you">${__('Your score')}</span><span class="trend-org">${__('Organisation average')}</span></div>
						</div>
						${renderTrendChart(trend, period)}
					</div>
					<div class="ms-panel ms-participation-panel">
						<div class="ms-panel-head"><div><h3>${__('Review coverage')}</h3><p>${__('Received feedback against expected participation')}</p></div></div>
						${renderParticipation(results)}
					</div>
				</div>
			</section>
			<section class="ms-section">
				${sectionHeading('02', __('Competency profile'), __('Where your feedback stands against the organisation benchmark'))}
				<div class="ms-analysis-grid">
					<div class="ms-panel ms-scorecard-panel">
						<div class="ms-panel-head">
							<div><h3>${__('Score by competency')}</h3><p>${__('Released aggregate results on a 0–100 scale')}</p></div>
							<div class="ms-legend"><span class="you">${__('Your score')}</span><span class="benchmark">${__('Organisation average')}</span></div>
						</div>
						<div class="ms-competencies">${renderCategories(results.categories || [])}</div>
					</div>
					<div class="ms-panel ms-insights-panel">
						<div class="ms-panel-head"><div><h3>${__('Executive readout')}</h3><p>${__('A concise interpretation of this period')}</p></div></div>
						${renderInsights(results)}
					</div>
				</div>
			</section>`;
	}

	function sectionHeading(index, title, subtitle, aside) {
		return `<div class="ms-section-heading">
			<div class="ms-section-index">${esc(index)}</div>
			<div class="ms-section-copy"><h2>${title}</h2><p>${subtitle}</p></div>
			${aside ? `<div class="ms-section-aside">${aside}</div>` : ''}
		</div>`;
	}

	function kpi(label, value, sublabel, kind) {
		return `<article class="ms-kpi ${kind || ''}"><div class="ms-kpi-label">${label}</div><div class="ms-kpi-value">${esc(value)}</div><div class="ms-kpi-sub">${esc(sublabel)}</div></article>`;
	}

	function compactPeriod(value, fallback) {
		if (!value) return esc(fallback || '');
		var parts = String(value).split(' ')[0].split('-');
		if (parts.length !== 3) return esc(value);
		var months = [__('Jan'), __('Feb'), __('Mar'), __('Apr'), __('May'), __('Jun'), __('Jul'), __('Aug'), __('Sep'), __('Oct'), __('Nov'), __('Dec')];
		return esc(months[Math.max(0, number(parts[1]) - 1)] + ' ' + parts[0]);
	}

	function renderTrendChart(trend, selected) {
		if (!trend.length) {
			return inlineEmpty('line-chart', __('No trend available yet'), __('Your trend will appear after more released survey periods.'));
		}

		var chartLeft = 50;
		var chartRight = 690;
		var chartTop = 24;
		var chartBottom = 174;
		var span = trend.length > 1 ? (chartRight - chartLeft) / (trend.length - 1) : 0;
		var points = trend.map(function (item, index) {
			var score = clamp(item.overall_pct);
			return {
				item: item,
				x: trend.length > 1 ? chartLeft + span * index : (chartLeft + chartRight) / 2,
				y: chartBottom - (score / 100) * (chartBottom - chartTop),
				score: score
			};
		});
		var scoreLine = points.map(function (point) { return point.x + ',' + point.y; }).join(' ');
		var area = trend.length > 1
			? `${chartLeft},${chartBottom} ${scoreLine} ${chartRight},${chartBottom}`
			: '';
		var orgPoints = points.filter(function (point) {
			return point.item.org_avg != null;
		}).map(function (point) {
			var y = chartBottom - (clamp(point.item.org_avg) / 100) * (chartBottom - chartTop);
			return point.x + ',' + y;
		}).join(' ');
		var orgDots = points.filter(function (point) {
			return point.item.org_avg != null;
		}).map(function (point) {
			var y = chartBottom - (clamp(point.item.org_avg) / 100) * (chartBottom - chartTop);
			return `<circle cx="${point.x}" cy="${y}" r="3" class="ms-chart-org-dot"></circle>`;
		}).join('');
		var grid = [0, 25, 50, 75, 100].map(function (value) {
			var y = chartBottom - (value / 100) * (chartBottom - chartTop);
			return `<line x1="${chartLeft}" y1="${y}" x2="${chartRight}" y2="${y}" class="ms-chart-grid"></line><text x="9" y="${y + 3}" class="ms-chart-axis">${value}</text>`;
		}).join('');
		var dots = points.map(function (point) {
			return `<g><circle cx="${point.x}" cy="${point.y}" r="4" class="ms-chart-dot"></circle><text x="${point.x}" y="${point.y - 10}" text-anchor="middle" class="ms-chart-value">${point.score.toFixed(1)}%</text></g>`;
		}).join('');

		return `<div class="ms-trend-body">
			<svg class="ms-trend-chart" viewBox="0 0 720 205" role="img" aria-label="${__('Released performance trend')}">
				${grid}
				${area ? `<polygon points="${area}" class="ms-chart-area"></polygon>` : ''}
				${orgPoints ? `<polyline points="${orgPoints}" class="ms-chart-org-line"></polyline>` : ''}
				${scoreLine ? `<polyline points="${scoreLine}" class="ms-chart-score-line"></polyline>` : ''}
				${orgDots}
				${dots}
			</svg>
			<div class="ms-trend-periods">
				${trend.map(function (item) {
					var current = selected && selected.key === item.key ? 'current' : '';
					return `<button class="ms-trend-chip ${current}" type="button" data-period="${esc(item.key)}"><span>${compactPeriod(item.period_end, item.label)}</span><strong>${number(item.overall_pct).toFixed(1)}%</strong></button>`;
				}).join('')}
			</div>
		</div>`;
	}

	function renderParticipation(results) {
		var received = number(results.reviewer_count);
		var expected = number(results.expected_reviews);
		var coverage = expected ? clamp(received / expected * 100) : (received ? 100 : 0);
		var radius = 45;
		var circumference = 2 * Math.PI * radius;
		var dash = circumference * coverage / 100;
		var outstanding = expected ? Math.max(0, expected - received) : null;
		return `<div class="ms-participation">
			<div class="ms-donut-wrap">
				<svg class="ms-donut" viewBox="0 0 120 120" role="img" aria-label="${__('Review coverage')} ${coverage.toFixed(0)}%">
					<circle cx="60" cy="60" r="${radius}" class="ms-donut-track"></circle>
					<circle cx="60" cy="60" r="${radius}" class="ms-donut-value" stroke-dasharray="${dash} ${circumference - dash}"></circle>
				</svg>
				<div class="ms-donut-label"><strong>${coverage.toFixed(0)}%</strong><span>${__('coverage')}</span></div>
			</div>
			<div class="ms-coverage-stats">
				<div><span>${__('Received')}</span><strong>${received}</strong></div>
				<div><span>${__('Expected')}</span><strong>${expected || '—'}</strong></div>
				<div><span>${__('Outstanding')}</span><strong>${outstanding == null ? '—' : outstanding}</strong></div>
			</div>
			<p>${expected ? __('Coverage is based on assigned reviewers for this released period.') : __('This period does not include an expected-review target.')}</p>
		</div>`;
	}

	function renderInsights(results) {
		var categories = (results.categories || []).slice().sort(function (a, b) {
			return number(b.score_pct) - number(a.score_pct);
		});
		if (!categories.length) {
			return inlineEmpty('line-chart', __('No readout available'), __('Insights will appear when competency scores are released.'));
		}

		var strongest = categories[0];
		var focus = categories[categories.length - 1];
		var orgAverage = results.org_overall_avg;
		var gap = orgAverage == null ? null : number(results.overall_pct) - number(orgAverage);
		var benchmarkText = gap == null
			? __('An organisation benchmark is not yet available for this period.')
			: (gap >= 0
				? __('Your overall result is {0} points above the organisation average.', [Math.abs(gap).toFixed(1)])
				: __('Your overall result is {0} points below the organisation average.', [Math.abs(gap).toFixed(1)]));

		return `<div class="ms-insights">
			<div class="ms-insight">
				<span class="ms-insight-number">01</span>
				<div><small>${__('Established strength')}</small><p><strong>${esc(strongest.category)}</strong> ${__('is your highest-rated competency at')} <strong>${number(strongest.score_pct).toFixed(1)}%</strong>.</p></div>
			</div>
			<div class="ms-insight">
				<span class="ms-insight-number">02</span>
				<div><small>${__('Development priority')}</small><p><strong>${esc(focus.category)}</strong> ${__('has the greatest opportunity for focused development at')} <strong>${number(focus.score_pct).toFixed(1)}%</strong>.</p></div>
			</div>
			<div class="ms-insight">
				<span class="ms-insight-number">03</span>
				<div><small>${__('Benchmark position')}</small><p>${esc(benchmarkText)}</p></div>
			</div>
		</div>`;
	}

	function renderCategories(categories) {
		if (!categories.length) return `<div class="ms-inline-empty">${__('No competency scores are available for this period.')}</div>`;
		return categories.map(function (category) {
			var yours = clamp(category.score_pct);
			var org = category.org_avg == null ? null : clamp(category.org_avg);
			var percentile = category.percentile == null ? '—' : ordinal(category.percentile) + ' ' + __('percentile');
			var gap = org == null ? null : yours - org;
			var gapLabel = gap == null ? '—' : (gap > 0 ? '+' : '') + gap.toFixed(1);
			return `
				<div class="ms-competency-row">
					<div class="ms-competency-name"><strong>${esc(category.category)}</strong><span>${percentile}</span></div>
					<div class="ms-score-plot" title="${__('Organisation average')}: ${org == null ? '—' : org.toFixed(1) + '%'}">
						<span class="ms-score-fill" style="width:${yours}%"></span>
						${org == null ? '' : `<span class="ms-benchmark-marker" style="left:${org}%"></span>`}
					</div>
					<div class="ms-score-value"><strong>${yours.toFixed(1)}%</strong><span>${__('Your score')}</span></div>
					<div class="ms-gap ${gap != null && gap >= 0 ? 'positive' : ''}"><strong>${gapLabel}</strong><span>${__('vs avg')}</span></div>
				</div>`;
		}).join('');
	}

	function renderAssignments(assignments) {
		var pending = assignments.pending || [];
		var completed = assignments.recent_completed || [];
		var filtered = assignments.filter_active;
		var subtitle = filtered
			? __('Survey activity within the selected date range')
			: __('Feedback you have been asked to provide');
		return `
			<section class="ms-section assignments">
				${sectionHeading('03', __('Action queue'), subtitle, `<div class="ms-task-count"><b>${number(assignments.pending_count)}</b><span>${filtered ? __('pending in range') : __('pending')}</span></div>`)}
				<div class="ms-task-grid">
					<div class="ms-panel">
						<div class="ms-panel-head"><div><h3>${__('Pending surveys')}</h3><p>${__('Complete these items before the assessment cycle closes')}</p></div></div>
						${pending.length ? `<div class="ms-task-list">${pending.map(pendingTask).join('')}</div>` : inlineEmpty('check-circle', filtered ? __('No pending activity in range') : __('You are all caught up'), filtered ? __('Adjust or clear the activity date range to see other surveys.') : __('There are no surveys waiting for your response.'))}
					</div>
					<div class="ms-panel">
						<div class="ms-panel-head"><div><h3>${__('Recently completed')}</h3><p>${__('Your 20 latest submitted surveys')}</p></div><span class="ms-total">${number(assignments.completed_count)} ${__('total')}</span></div>
						${completed.length ? `<div class="ms-task-list completed">${completed.map(completedTask).join('')}</div>` : inlineEmpty('history', filtered ? __('No completed activity in range') : __('No completed surveys yet'), filtered ? __('Adjust or clear the activity date range to see other submissions.') : __('Submitted surveys will appear here.'))}
					</div>
				</div>
			</section>`;
	}

	function pendingTask(item) {
		return `<div class="ms-task">
			<div class="ms-task-status pending">${__('Pending')}</div>
			<div class="ms-task-body"><b>${esc(item.reviewee_name)}</b><span>${esc(item.title)}</span></div>
			<div class="ms-task-date"><small>${__('Assigned')}</small><span>${dateOnly(item.assigned_on)}</span></div>
			<div class="ms-task-age"><small>${__('Age')}</small><span>${number(item.days_pending)} ${__('days')}</span></div>
			<a class="btn btn-primary btn-sm" href="${esc(item.survey_url)}" target="_blank" rel="noopener">${__('Complete survey')}<i class="fa fa-arrow-right"></i></a>
		</div>`;
	}

	function completedTask(item) {
		return `<div class="ms-task completed">
			<div class="ms-task-status done"><i class="fa fa-check"></i>${__('Complete')}</div>
			<div class="ms-task-body"><b>${esc(item.reviewee_name)}</b><span>${esc(item.title)}</span></div>
			<div class="ms-task-date"><small>${__('Submitted')}</small><span>${dateOnly(item.completed_on)}</span></div>
		</div>`;
	}

	function inlineEmpty(icon, title, message) {
		return `<div class="ms-inline-empty"><i class="fa fa-${icon}"></i><b>${title}</b><span>${message}</span></div>`;
	}

	function renderState(title, message, icon) {
		$main.html(`
			<div class="ms-root state-page"><div class="ms-empty"><div class="ms-empty-icon"><i class="fa fa-${icon}"></i></div><h2>${title}</h2><p>${message}</p><button class="btn btn-default" id="ms-retry"><i class="fa fa-refresh"></i> ${__('Try again')}</button></div></div>${styles()}
		`);
		$main.find('#ms-retry').on('click', function () { load(selectedPeriod, selectedFromDate, selectedToDate); });
	}

	function load(period, fromDate, toDate) {
		shell();
		frappe.call({
			method: 'survey_app.my_surveys.get_my_dashboard',
			args: {
				period_key: period || null,
				from_date: fromDate || null,
				to_date: toDate || null
			},
			callback: function (response) {
				if (response.exc || !response.message) {
					renderState(__('Dashboard unavailable'), __('We could not load your survey information. Please try again.'), 'exclamation-triangle');
					return;
				}
				selectedPeriod = response.message.selected_period ? response.message.selected_period.key : null;
				selectedFromDate = response.message.activity_filter ? response.message.activity_filter.from_date : '';
				selectedToDate = response.message.activity_filter ? response.message.activity_filter.to_date : '';
				render(response.message);
			},
			error: function () {
				renderState(__('Dashboard unavailable'), __('We could not load your survey information. Please try again.'), 'exclamation-triangle');
			}
		});
	}

	function styles() {
		return `<style>
			.ms-root{--ms-ink:#191a18;--ms-muted:#666963;--ms-line:#deded8;--ms-soft:#f5f5f2;--ms-green:#86bc25;min-height:calc(100vh - 110px);color:var(--ms-ink);font-family:"Inter","Segoe UI",Arial,sans-serif;background:var(--ms-soft)}
			.ms-masthead{background:#fff;border-bottom:1px solid var(--ms-line)}.ms-accent-rule{height:5px;background:#171817}.ms-accent-rule span{display:block;width:84px;height:5px;background:var(--ms-green)}.ms-header-inner{max-width:1400px;margin:0 auto;padding:17px 38px 30px}.ms-document-line{display:flex;justify-content:space-between;padding-bottom:22px;border-bottom:1px solid #ecece8;color:#6e706b;font-size:9px;font-weight:700;letter-spacing:1.45px;text-transform:uppercase}.ms-identity-row{display:flex;align-items:flex-end;justify-content:space-between;gap:40px;padding-top:25px}.ms-profile{display:flex;align-items:center;gap:16px;min-width:0}.ms-avatar{width:52px;height:52px;flex:0 0 52px;border-radius:2px;background:#20211f;color:#fff;display:flex;align-items:center;justify-content:center;overflow:hidden;font-size:16px;font-weight:700;letter-spacing:1px}.ms-avatar img{width:100%;height:100%;object-fit:cover}.ms-eyebrow{margin-bottom:4px;color:#73766f;font-size:9px;font-weight:700;letter-spacing:1.3px;text-transform:uppercase}.ms-profile h1{margin:0 0 5px;color:var(--ms-ink);font-size:29px;font-weight:600;letter-spacing:-.6px}.ms-profile p{display:flex;align-items:center;gap:9px;margin:0;color:#666963;font-size:12px}.ms-profile p span{width:3px;height:3px;border-radius:50%;background:var(--ms-green)}.ms-cycle-context{min-width:285px;padding-left:22px;border-left:3px solid var(--ms-green);display:flex;flex-direction:column}.ms-cycle-context.muted{border-left-color:#b7b8b2}.ms-cycle-label{display:flex;align-items:center;gap:7px;margin-bottom:5px;color:#74766f;font-size:9px;font-weight:700;letter-spacing:1px;text-transform:uppercase}.ms-status-dot{width:6px;height:6px;border-radius:50%;background:var(--ms-green)}.ms-cycle-context strong{margin-bottom:3px;font-size:13px;font-weight:650}.ms-cycle-context>span{color:#777a74;font-size:10px}
			.ms-content{max-width:1400px;margin:0 auto;padding:24px 38px 52px}.ms-control-bar{display:flex;align-items:center;justify-content:space-between;gap:28px;margin-bottom:35px;padding:17px 19px;background:#fff;border:1px solid var(--ms-line)}.ms-filter-fields{min-width:0;flex:1;display:grid;grid-template-columns:minmax(230px,310px) minmax(430px,1fr);align-items:end;gap:22px}.ms-period-control,.ms-date-control{min-width:0}.ms-period-control label,.ms-date-control label{display:block;margin-bottom:5px;color:#5d6059;font-size:9px;font-weight:750;letter-spacing:1px;text-transform:uppercase}.ms-period-control>small,.ms-date-control>small{display:block;margin-top:5px;color:#898c84;font-size:8px}.ms-period-control select,.ms-date-inputs input{height:32px;border-radius:2px;border-color:#caccc5;font-size:11px}.ms-period-control select{width:100%}.ms-date-row,.ms-date-inputs,.ms-filter-actions{display:flex;align-items:center}.ms-date-row{gap:8px}.ms-date-inputs{min-width:0;flex:1;gap:7px}.ms-date-inputs input{min-width:120px;flex:1}.ms-date-inputs span{color:#8b8e86;font-size:9px;text-transform:uppercase}.ms-filter-actions{gap:5px}.ms-filter-actions .btn{height:32px;border-radius:2px;font-size:9px;font-weight:700}.ms-filter-actions .btn-primary{border-color:#20211f;background:#20211f}.ms-filter-actions .btn-primary:hover,.ms-filter-actions .btn-primary:focus{border-color:#000;background:#000}.ms-filter-actions .btn-default{border-color:#d2d3cd;background:#f7f7f5}.ms-privacy{max-width:330px;padding-left:20px;border-left:1px solid #e2e2dd;display:flex;align-items:flex-start;gap:9px;color:#696c65;font-size:10px;line-height:1.5}.ms-privacy i{margin-top:2px;color:#343532}.ms-section{margin-bottom:43px}.ms-section-heading{display:grid;grid-template-columns:30px minmax(0,1fr) auto;align-items:end;gap:12px;margin-bottom:16px}.ms-section-index{padding-bottom:4px;border-bottom:2px solid var(--ms-green);color:#555750;font-size:10px;font-weight:800;letter-spacing:.7px}.ms-section-copy h2{margin:0 0 3px;color:var(--ms-ink);font-size:18px;font-weight:650;letter-spacing:-.2px}.ms-section-copy p{margin:0;color:#71746d;font-size:11px}.ms-section-aside{align-self:center}.ms-released{display:inline-flex;align-items:center;gap:6px;padding:5px 9px;background:#eef5e3;color:#40541f;font-size:9px;font-weight:800;letter-spacing:.7px;text-transform:uppercase}
			.ms-scoreboard{display:grid;grid-template-columns:1.15fr repeat(3,1fr);background:#fff;border:1px solid var(--ms-line);border-top:3px solid var(--ms-ink)}.ms-kpi{min-height:132px;padding:22px 24px;border-left:1px solid var(--ms-line);display:flex;flex-direction:column;justify-content:space-between}.ms-kpi:first-child{border-left:0}.ms-kpi.featured{background:#1b1c1a;color:#fff}.ms-kpi-label{color:#6e716a;font-size:9px;font-weight:750;letter-spacing:1.05px;text-transform:uppercase}.ms-kpi.featured .ms-kpi-label{color:#c2c4bd}.ms-kpi-value{margin:8px 0 5px;color:var(--ms-ink);font-family:Georgia,"Times New Roman",serif;font-size:35px;line-height:1;letter-spacing:-1px}.ms-kpi.featured .ms-kpi-value{color:#fff}.ms-kpi-sub{color:#74776f;font-size:10px;line-height:1.4}.ms-kpi.featured .ms-kpi-sub{color:#aeb1aa}
			.ms-analytics-row{display:grid;grid-template-columns:minmax(0,1.75fr) minmax(285px,.65fr);gap:16px;margin-top:16px}.ms-trend-body{padding:10px 18px 16px}.ms-trend-chart{display:block;width:100%;height:auto;overflow:visible}.ms-chart-grid{stroke:#e7e8e2;stroke-width:1}.ms-chart-axis{fill:#979a92;font-family:"Inter","Segoe UI",Arial,sans-serif;font-size:8px}.ms-chart-area{fill:rgba(134,188,37,.12);stroke:none}.ms-chart-score-line{fill:none;stroke:var(--ms-green);stroke-width:3}.ms-chart-org-line{fill:none;stroke:#2f302e;stroke-width:1.5;stroke-dasharray:6 5}.ms-chart-org-dot{fill:#2f302e;stroke:#fff;stroke-width:1}.ms-chart-dot{fill:#fff;stroke:#658f1c;stroke-width:3}.ms-chart-value{fill:#292a28;font-family:"Inter","Segoe UI",Arial,sans-serif;font-size:9px;font-weight:700}.ms-legend .trend-org:before{height:1px;background:#30312f}.ms-trend-periods{display:grid;grid-template-columns:repeat(auto-fit,minmax(78px,1fr));gap:6px;margin-top:2px}.ms-trend-chip{padding:8px 9px;border:1px solid #dedfd9;background:#fafaf8;color:#666963;display:flex;align-items:center;justify-content:space-between;gap:8px;font-size:8px;text-align:left}.ms-trend-chip strong{color:#282927;font-size:10px}.ms-trend-chip:hover,.ms-trend-chip:focus{border-color:#a9ab9f;background:#fff;outline:0}.ms-trend-chip.current{border-color:#789f32;background:#f1f6e9;color:#3d4d25}.ms-participation{padding:22px 20px 17px}.ms-donut-wrap{width:142px;height:142px;margin:0 auto 18px;position:relative}.ms-donut{width:100%;height:100%;transform:rotate(-90deg)}.ms-donut-track,.ms-donut-value{fill:none;stroke-width:9}.ms-donut-track{stroke:#e7e8e2}.ms-donut-value{stroke:var(--ms-green);stroke-linecap:butt}.ms-donut-label{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;flex-direction:column}.ms-donut-label strong{color:#232422;font-family:Georgia,"Times New Roman",serif;font-size:25px}.ms-donut-label span{margin-top:2px;color:#7e8179;font-size:8px;font-weight:700;letter-spacing:.6px;text-transform:uppercase}.ms-coverage-stats{display:grid;grid-template-columns:repeat(3,1fr);border-top:1px solid #e4e5df;border-bottom:1px solid #e4e5df}.ms-coverage-stats div{padding:11px 4px;border-left:1px solid #e4e5df;display:flex;align-items:center;flex-direction:column}.ms-coverage-stats div:first-child{border-left:0}.ms-coverage-stats span{color:#858880;font-size:7px;font-weight:700;text-transform:uppercase}.ms-coverage-stats strong{margin-top:3px;color:#292a28;font-family:Georgia,"Times New Roman",serif;font-size:17px}.ms-participation>p{margin:12px 0 0;color:#7a7d75;font-size:9px;line-height:1.5;text-align:center}
			.ms-analysis-grid{display:grid;grid-template-columns:minmax(0,1.75fr) minmax(310px,.75fr);gap:16px}.ms-panel{overflow:hidden;background:#fff;border:1px solid var(--ms-line)}.ms-panel-head{min-height:66px;padding:15px 18px;border-bottom:1px solid #e6e6e1;display:flex;align-items:center;justify-content:space-between;gap:16px}.ms-panel-head h3{margin:0 0 3px;color:var(--ms-ink);font-size:13px;font-weight:650}.ms-panel-head p{margin:0;color:#777a73;font-size:10px}.ms-legend{display:flex;gap:17px;color:#696c65;font-size:9px}.ms-legend span{display:flex;align-items:center;gap:6px;white-space:nowrap}.ms-legend span:before{content:"";display:block;width:13px;height:4px;background:var(--ms-green)}.ms-legend .benchmark:before{width:2px;height:12px;background:#343532}.ms-competencies{padding:2px 18px}.ms-competency-row{display:grid;grid-template-columns:minmax(145px,1fr) minmax(150px,2.2fr) 67px 52px;align-items:center;gap:15px;min-height:71px;border-bottom:1px solid #ecece8}.ms-competency-row:last-child{border-bottom:0}.ms-competency-name{display:flex;flex-direction:column;min-width:0}.ms-competency-name strong{overflow:hidden;color:#282927;font-size:11px;font-weight:650;text-overflow:ellipsis;white-space:nowrap}.ms-competency-name span{margin-top:3px;color:#80827c;font-size:9px}.ms-score-plot{height:8px;position:relative;background:#e9eae5}.ms-score-fill{display:block;height:100%;background:var(--ms-green)}.ms-benchmark-marker{position:absolute;top:-5px;width:2px;height:18px;background:#262725;transform:translateX(-1px)}.ms-score-value,.ms-gap{display:flex;flex-direction:column;text-align:right}.ms-score-value strong,.ms-gap strong{color:#252624;font-family:Georgia,"Times New Roman",serif;font-size:14px}.ms-score-value span,.ms-gap span{color:#888b83;font-size:8px;text-transform:uppercase}.ms-gap strong{font-family:inherit;font-size:11px}.ms-gap.positive strong{color:#547b16}
			.ms-insights{padding:0 18px}.ms-insight{display:grid;grid-template-columns:25px 1fr;gap:11px;padding:17px 0;border-bottom:1px solid #ecece8}.ms-insight:last-child{border-bottom:0}.ms-insight-number{color:#8cbf2e;font-size:10px;font-weight:800}.ms-insight small{display:block;margin-bottom:5px;color:#777a73;font-size:8px;font-weight:750;letter-spacing:.8px;text-transform:uppercase}.ms-insight p{margin:0;color:#585b55;font-size:10px;line-height:1.55}.ms-insight p strong{color:#242523;font-weight:650}
			.ms-task-count{display:flex;align-items:baseline;gap:5px;color:#73766f}.ms-task-count b{color:var(--ms-ink);font-family:Georgia,"Times New Roman",serif;font-size:22px}.ms-task-count span{font-size:9px;font-weight:700;letter-spacing:.6px;text-transform:uppercase}.ms-task-grid{display:grid;grid-template-columns:minmax(0,1.2fr) minmax(0,.8fr);gap:16px}.ms-task-list{max-height:445px;overflow:auto}.ms-task{min-height:72px;padding:12px 15px;border-bottom:1px solid #ecece8;display:grid;grid-template-columns:66px minmax(125px,1fr) 76px 58px auto;align-items:center;gap:13px}.ms-task:last-child{border-bottom:0}.ms-task.completed{grid-template-columns:75px minmax(120px,1fr) 82px}.ms-task-status{font-size:8px;font-weight:800;letter-spacing:.7px;text-transform:uppercase}.ms-task-status.pending{padding-left:8px;border-left:3px solid var(--ms-green);color:#4e5f32}.ms-task-status.done{display:flex;align-items:center;gap:5px;color:#5d6159}.ms-task-status.done i{color:#6d951f}.ms-task-body{display:flex;flex-direction:column;min-width:0}.ms-task-body b,.ms-task-body span{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.ms-task-body b{color:#282927;font-size:11px;font-weight:650}.ms-task-body span{margin-top:3px;color:#777a73;font-size:9px}.ms-task-date,.ms-task-age{display:flex;flex-direction:column}.ms-task-date small,.ms-task-age small{color:#92958e;font-size:7px;font-weight:750;letter-spacing:.7px;text-transform:uppercase}.ms-task-date span,.ms-task-age span{margin-top:3px;color:#50524e;font-size:9px}.ms-task .btn-primary{padding:7px 10px;border:0;border-radius:2px;background:#20211f;color:#fff;font-size:9px;font-weight:700;letter-spacing:.25px}.ms-task .btn-primary:hover,.ms-task .btn-primary:focus{background:#000;color:#fff}.ms-task .btn-primary i{margin-left:7px;color:var(--ms-green)}.ms-total{color:#777a73;font-size:9px;font-weight:700;letter-spacing:.5px;text-transform:uppercase}
			.ms-inline-empty{min-height:155px;padding:24px;display:flex;flex-direction:column;align-items:center;justify-content:center;text-align:center;color:#777a73}.ms-inline-empty i{margin-bottom:9px;color:#82ad36;font-size:19px}.ms-inline-empty b{margin-bottom:4px;color:#3d3f3a;font-size:11px}.ms-inline-empty span{font-size:9px}.ms-empty{max-width:660px;margin:70px auto;padding:48px;background:#fff;border:1px solid var(--ms-line);border-top:4px solid var(--ms-ink);text-align:center}.ms-empty.compact{max-width:none;margin:0;padding:45px}.ms-empty-icon{width:44px;height:44px;margin:0 auto 16px;background:#edf3e5;color:#5f8420;display:flex;align-items:center;justify-content:center;font-size:18px}.ms-empty h2,.ms-empty h3{margin:0 0 8px;color:#292a28}.ms-empty p{max-width:480px;margin:0 auto 18px;color:#71746d;font-size:11px;line-height:1.65}.state-page{padding:1px 25px}.ms-loading{min-height:420px;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:12px;color:#72756e;font-size:11px}.ms-spinner{width:28px;height:28px;border:2px solid #d9dad5;border-top-color:var(--ms-green);border-radius:50%;animation:ms-spin .8s linear infinite}.ms-footer{max-width:1324px;margin:0 auto;padding:16px 0 25px;border-top:1px solid #dadbd5;display:flex;justify-content:space-between;color:#81847d;font-size:8px;font-weight:700;letter-spacing:1px;text-transform:uppercase}@keyframes ms-spin{to{transform:rotate(360deg)}}
			@media(max-width:1100px){.ms-control-bar{align-items:stretch;flex-direction:column}.ms-privacy{max-width:none;padding:13px 0 0;border-top:1px solid #e2e2dd;border-left:0}.ms-scoreboard{grid-template-columns:repeat(2,1fr)}.ms-kpi:nth-child(3){border-left:0;border-top:1px solid var(--ms-line)}.ms-kpi:nth-child(4){border-top:1px solid var(--ms-line)}.ms-analytics-row,.ms-analysis-grid,.ms-task-grid{grid-template-columns:1fr}.ms-footer{margin:0 38px}}
			@media(max-width:800px){.ms-header-inner{padding:16px 22px 26px}.ms-identity-row{align-items:flex-start;flex-direction:column;gap:23px}.ms-cycle-context{width:100%;min-width:0}.ms-content{padding:20px 22px 42px}.ms-control-bar{gap:15px;margin-bottom:29px}.ms-filter-fields{grid-template-columns:1fr}.ms-footer{margin:0 22px}.ms-task{grid-template-columns:63px minmax(100px,1fr) 73px auto}.ms-task-age{display:none}}
			@media(max-width:575px){.ms-document-line span:last-child{display:none}.ms-header-inner{padding:14px 16px 23px}.ms-identity-row{padding-top:20px}.ms-avatar{width:46px;height:46px;flex-basis:46px}.ms-profile{align-items:flex-start;gap:12px}.ms-profile h1{font-size:23px}.ms-profile p{align-items:flex-start;flex-direction:column;gap:2px}.ms-profile p span{display:none}.ms-cycle-context{padding-left:14px}.ms-content{padding:16px 12px 35px}.ms-control-bar{padding:14px;margin-bottom:27px}.ms-date-row{align-items:stretch;flex-direction:column}.ms-date-inputs input{min-width:0}.ms-filter-actions .btn{flex:1}.ms-section{margin-bottom:34px}.ms-section-heading{grid-template-columns:25px 1fr;align-items:start}.ms-section-aside{grid-column:2}.ms-scoreboard{grid-template-columns:1fr}.ms-kpi{min-height:116px;border-top:1px solid var(--ms-line);border-left:0}.ms-kpi:first-child{border-top:0}.ms-panel-head{align-items:flex-start;flex-direction:column}.ms-legend{width:100%;justify-content:space-between}.ms-trend-body{padding:8px 10px 14px}.ms-trend-periods{grid-template-columns:repeat(2,1fr)}.ms-participation{padding-top:17px}.ms-competencies{padding:0 14px}.ms-competency-row{grid-template-columns:1fr 56px 43px;gap:10px;padding:14px 0}.ms-competency-name{grid-column:1/-1}.ms-score-plot{grid-column:1}.ms-task{grid-template-columns:1fr auto;gap:8px 12px;padding:14px}.ms-task.completed{grid-template-columns:1fr auto}.ms-task-status{grid-column:1}.ms-task-body{grid-column:1}.ms-task-date{grid-column:2;grid-row:1/3;text-align:right}.ms-task-age{display:none}.ms-task .btn-primary{grid-column:1/-1;width:100%;margin-top:5px}.ms-footer{margin:0 12px;padding-bottom:20px}.ms-footer span:last-child{display:none}.ms-empty{margin:35px auto;padding:35px 21px}}
		</style>`;
	}

	load();
};

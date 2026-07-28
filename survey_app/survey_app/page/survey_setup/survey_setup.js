window.survey_app = window.survey_app || {};

frappe.pages['survey-setup'].on_page_load = function(wrapper) {
	var page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __('Survey Configuration'),
		single_column: true
	});

	frappe.breadcrumbs.add('Survey App');
	new survey_app.SurveySetup(wrapper, page);
};

survey_app.SurveySetup = class SurveySetup {
	constructor(wrapper, page) {
		this.wrapper = wrapper;
		this.page = page;
		this.current_category = null;
		this.active_tab = 'categories';
		this._countdown_timer = null;
		this._countdown_target_ms = null;

		this.build_ui();
		this.load_data();
	}

	build_ui() {
		this.page.add_inner_button(__('Refresh'), () => this.load_data());

		this.$root = $(`
			<div class="survey-setup-root">
				<ul class="nav nav-tabs" role="tablist">
					<li class="nav-item">
						<button type="button" class="nav-link active" data-tab="categories" role="tab">
							<i class="fa fa-tags"></i> ${__('Categories & Questions')}
						</button>
					</li>
					<li class="nav-item">
						<button type="button" class="nav-link" data-tab="scoring" role="tab">
							<i class="fa fa-sliders"></i> ${__('Scoring & Departments')}
						</button>
					</li>
					<li class="nav-item">
						<button type="button" class="nav-link" data-tab="automation" role="tab">
							<i class="fa fa-clock-o"></i> ${__('Automation')}
						</button>
					</li>
					<li class="nav-item">
						<button type="button" class="nav-link" data-tab="generate" role="tab">
							<i class="fa fa-play"></i> ${__('Generate Surveys')}
						</button>
					</li>
					<li class="nav-item">
						<button type="button" class="nav-link" data-tab="trail" role="tab">
							<i class="fa fa-history"></i> ${__('Generation Trail')}
						</button>
					</li>
				</ul>
				<div class="tab-content">
					<div role="tabpanel" class="tab-pane fade show active" id="tab-categories"></div>
					<div role="tabpanel" class="tab-pane fade" id="tab-scoring"></div>
					<div role="tabpanel" class="tab-pane fade" id="tab-automation"></div>
					<div role="tabpanel" class="tab-pane fade" id="tab-generate"></div>
					<div role="tabpanel" class="tab-pane fade" id="tab-trail"></div>
				</div>
				<style>
					.survey-setup-root {
						padding: 20px 24px 40px;
						background: #f4f5f6;
						min-height: calc(100vh - 120px);
					}
					.survey-setup-root .nav-tabs {
						background: #fff;
						border: 1px solid #e2e6e9;
						border-radius: 8px 8px 0 0;
						padding: 0 8px;
						border-bottom: 1px solid #d1d8dd;
					}
					.survey-setup-root .nav-tabs .nav-link {
						border: none;
						border-bottom: 2px solid transparent;
						border-radius: 0;
						color: #6c7680;
						font-weight: 500;
						padding: 14px 18px;
						margin-bottom: -1px;
						background: transparent;
						cursor: pointer;
					}
					.survey-setup-root .nav-tabs .nav-link:focus {
						outline: none;
						box-shadow: none;
					}
					.survey-setup-root .nav-tabs .nav-link:hover {
						color: #2490ef;
						border-color: transparent;
						background: transparent;
					}
					.survey-setup-root .nav-tabs .nav-link.active {
						color: #2490ef;
						border-bottom-color: #2490ef;
						background: transparent;
					}
					.survey-setup-root .tab-content {
						background: #fff;
						border: 1px solid #e2e6e9;
						border-top: none;
						border-radius: 0 0 8px 8px;
						padding: 24px;
						min-height: 420px;
					}
					.survey-setup-root .panel {
						border: 1px solid #e2e6e9;
						border-radius: 8px;
						box-shadow: 0 1px 3px rgba(0,0,0,0.04);
						margin-bottom: 0;
					}
					.survey-setup-root .panel-heading {
						background: #f9fafb;
						border-bottom: 1px solid #eef0f2;
						padding: 12px 16px;
						border-radius: 8px 8px 0 0;
					}
					.survey-setup-root .panel-body { padding: 16px; }
					.survey-setup-root .category-item {
						padding: 10px 12px;
						border-bottom: 1px solid #f0f0f0;
						cursor: pointer;
						display: flex;
						justify-content: space-between;
						align-items: center;
						transition: background 0.15s;
					}
					.survey-setup-root .category-item:hover { background: #f7f9fb; }
					.survey-setup-root .category-item.active {
						background: #eaf4fe;
						border-left: 3px solid #2490ef;
						padding-left: 9px;
					}
					.survey-setup-root .category-item .badge {
						background: #dfe3e6;
						color: #36414c;
						margin-left: 6px;
					}
					.survey-setup-root .loading-state {
						padding: 48px;
						text-align: center;
						color: #8d99a6;
					}
					.survey-setup-root .table { margin-bottom: 0; }
					.survey-setup-root .form-group label {
						font-weight: 500;
						color: #36414c;
					}
					.survey-setup-root .trail-run {
						border: 1px solid #e2e6e9;
						border-radius: 8px;
						margin-bottom: 14px;
						overflow: hidden;
					}
					.survey-setup-root .trail-run-header {
						background: #f9fafb;
						padding: 12px 14px;
						cursor: pointer;
						display: flex;
						justify-content: space-between;
						align-items: center;
						gap: 12px;
					}
					.survey-setup-root .trail-run-header:hover { background: #f0f4f7; }
					.survey-setup-root .trail-run-body {
						display: none;
						padding: 0 14px 14px;
						border-top: 1px solid #eef0f2;
					}
					.survey-setup-root .trail-run.open .trail-run-body { display: block; }
					.survey-setup-root .status-pill {
						display: inline-block;
						padding: 2px 8px;
						border-radius: 10px;
						font-size: 11px;
						font-weight: 600;
					}
					.survey-setup-root .status-Success { background: #e5f7ee; color: #1e8e3e; }
					.survey-setup-root .status-Partial { background: #fff4e5; color: #b06000; }
					.survey-setup-root .status-Failed { background: #fce8e6; color: #d93025; }
					.survey-setup-root .status-Skipped { background: #eef0f2; color: #5f6368; }
					.survey-setup-root .countdown-panel {
						margin-top: 18px;
						padding: 18px 20px;
						border: 1px solid #d6e4f5;
						border-radius: 8px;
						background: linear-gradient(180deg, #f7fbff 0%, #eef5fc 100%);
						text-align: center;
					}
					.survey-setup-root .countdown-panel.hidden { display: none; }
					.survey-setup-root .countdown-panel.due {
						border-color: #b7e1c1;
						background: linear-gradient(180deg, #f3fbf5 0%, #e8f7ec 100%);
					}
					.survey-setup-root .countdown-panel.off {
						border-color: #e2e6e9;
						background: #f9fafb;
					}
					.survey-setup-root .countdown-label {
						font-size: 12px;
						text-transform: uppercase;
						letter-spacing: 0.6px;
						color: #6c7680;
						margin-bottom: 6px;
					}
					.survey-setup-root .countdown-value {
						font-size: 36px;
						font-weight: 700;
						font-variant-numeric: tabular-nums;
						color: #2490ef;
						line-height: 1.2;
						letter-spacing: 1px;
					}
					.survey-setup-root .countdown-panel.due .countdown-value { color: #1e8e3e; }
					.survey-setup-root .countdown-panel.off .countdown-value { color: #8d99a6; font-size: 22px; }
					.survey-setup-root .countdown-meta {
						margin-top: 8px;
						font-size: 12px;
						color: #6c7680;
					}
				</style>
			</div>
		`).appendTo(this.page.main);

		this.tab_categories = this.$root.find('#tab-categories');
		this.tab_scoring = this.$root.find('#tab-scoring');
		this.tab_automation = this.$root.find('#tab-automation');
		this.tab_generate = this.$root.find('#tab-generate');
		this.tab_trail = this.$root.find('#tab-trail');

		this.$root.find('.nav-link').on('click', (e) => {
			e.preventDefault();
			e.stopPropagation();
			var tab = $(e.currentTarget).data('tab');
			if (tab) this.switch_tab(tab);
		});
	}

	switch_tab(tab) {
		this.active_tab = tab;
		this.$root.find('.nav-link').removeClass('active');
		this.$root.find('.nav-link[data-tab="' + tab + '"]').addClass('active');
		this.$root.find('.tab-pane').removeClass('show active');
		this.$root.find('#tab-' + tab).addClass('show active');
	}

	load_data() {
		this.page.set_title(__('Survey Configuration'));
		this.stop_countdown();
		this.show_loading();

		frappe.call({
			method: 'survey_app.survey_config.get_config_data',
			callback: (r) => {
				if (r.exc) {
					this.show_error(__('Failed to load configuration data.'));
					return;
				}
				this.data = r.message || {};
				this.render_categories_tab();
				this.render_scoring_tab();
				this.render_automation_tab();
				this.render_generate_tab();
				this.render_trail_tab();
				this.switch_tab(this.active_tab || 'categories');
			}
		});
	}

	show_loading() {
		var html = '<div class="loading-state"><i class="fa fa-spinner fa-spin"></i> ' + __('Loading...') + '</div>';
		this.tab_categories.html(html);
		this.tab_scoring.html(html);
		this.tab_automation.html(html);
		this.tab_generate.html(html);
		this.tab_trail.html(html);
	}

	show_error(msg) {
		var html = '<div class="alert alert-danger">' + frappe.utils.escape_html(msg) + '</div>';
		this.tab_categories.html(html);
		this.tab_scoring.html(html);
		this.tab_automation.html(html);
		this.tab_generate.html(html);
		this.tab_trail.html(html);
	}

	// ============================================================
	// TAB 1: Categories & Questions
	// ============================================================
	render_categories_tab() {
		var me = this;
		var categories = this.data.categories || [];

		this.tab_categories.html(`
			<div class="row">
				<div class="col-md-4">
					<div class="panel panel-default">
						<div class="panel-heading">
							<b>${__('Categories')}</b>
							<button class="btn btn-xs btn-primary float-right" id="add-category-btn">
								<i class="fa fa-plus"></i> ${__('Add')}
							</button>
						</div>
						<div class="panel-body" id="category-list" style="max-height: 500px; overflow-y: auto; padding: 0;"></div>
					</div>
				</div>
				<div class="col-md-8">
					<div class="panel panel-default">
						<div class="panel-heading">
							<b>${__('Questions')}</b>
							<span class="text-muted" id="selected-category-label"></span>
							<button class="btn btn-xs btn-primary float-right" id="add-question-btn" style="display:none;">
								<i class="fa fa-plus"></i> ${__('Add Question')}
							</button>
						</div>
						<div class="panel-body" id="question-list" style="max-height: 500px; overflow-y: auto;">
							<p class="text-muted">${__('Select a category to view questions')}</p>
						</div>
					</div>
				</div>
			</div>
		`);

		var $cat_list = this.tab_categories.find('#category-list');

		if (!categories.length) {
			$cat_list.html('<p class="text-muted" style="padding:16px;">' + __('No categories yet.') + '</p>');
		} else {
			categories.forEach(function(cat) {
				$cat_list.append(me.render_category_row(cat));
			});
		}

		this.tab_categories.find('#add-category-btn').on('click', function() {
			frappe.prompt(__('Category Name'), function(values) {
				var name = (values && values.value) || '';
				if (!name) return;
				frappe.call({
					method: 'survey_app.survey_config.save_category',
					args: { name: name },
					callback: function(r) {
						if (r.exc) return;
						if (r.message && r.message.status === 'exists') {
							frappe.show_alert({ message: __('Category already exists'), indicator: 'orange' });
							return;
						}
						frappe.show_alert({ message: __('Category created'), indicator: 'green' });
						me.load_data();
					}
				});
			}, __('New Category'), __('Create'));
		});

		$cat_list.on('click', '.category-item', function() {
			var name = $(this).data('name');
			$cat_list.find('.category-item').removeClass('active');
			$(this).addClass('active');
			me.select_category(name);
		});

		$cat_list.on('click', '.delete-category-btn', function(e) {
			e.stopPropagation();
			var name = $(this).closest('.category-item').data('name');
			frappe.confirm(__('Delete category "{0}" and all its questions?', [name]), function() {
				frappe.call({
					method: 'survey_app.survey_config.delete_category',
					args: { name: name },
					callback: function(r) {
						if (r.exc) return;
						if (me.current_category === name) me.current_category = null;
						frappe.show_alert({ message: __('Category deleted'), indicator: 'green' });
						me.load_data();
					}
				});
			});
		});

		this.tab_categories.find('#add-question-btn').on('click', function() {
			if (!me.current_category) return;
			frappe.prompt({
				label: __('Question Text'),
				fieldname: 'value',
				fieldtype: 'Small Text',
				reqd: 1
			}, function(values) {
				var text = (values && values.value) || '';
				if (!text) return;
				frappe.call({
					method: 'survey_app.survey_config.save_question',
					args: { category: me.current_category, question_text: text },
					callback: function(r) {
						if (r.exc) return;
						frappe.show_alert({ message: __('Question added'), indicator: 'green' });
						me.load_data();
					}
				});
			}, __('New Question'), __('Add'));
		});

		this.tab_categories.find('#question-list').on('click', '.delete-question-btn', function() {
			var name = $(this).data('name');
			var text = $(this).closest('tr').find('td:first').text();
			frappe.confirm(__('Delete question: "{0}"?', [text]), function() {
				frappe.call({
					method: 'survey_app.survey_config.delete_question',
					args: { name: name },
					callback: function(r) {
						if (r.exc) return;
						frappe.show_alert({ message: __('Question deleted'), indicator: 'green' });
						me.load_data();
					}
				});
			});
		});

		if (this.current_category) {
			var current = this.current_category;
			var $item = $cat_list.find('.category-item').filter(function() {
				return $(this).attr('data-name') === current;
			});
			if ($item.length) {
				$item.addClass('active');
				this.select_category(this.current_category);
			} else {
				this.current_category = null;
			}
		}
	}

	render_category_row(cat) {
		var $row = $(`
			<div class="category-item">
				<span></span>
				<button class="btn btn-xs btn-danger delete-category-btn" title="${__('Delete')}">
					<i class="fa fa-trash"></i>
				</button>
			</div>
		`);
		$row.attr('data-name', cat.name);
		$row.find('span').first().text(cat.name + ' ').append(
			$('<span class="badge"></span>').text(cat.question_count || 0)
		);
		return $row;
	}

	select_category(name) {
		this.current_category = name;
		this.tab_categories.find('#selected-category-label').text('— ' + name);
		this.tab_categories.find('#add-question-btn').show();

		var cat = (this.data.categories || []).find(function(c) { return c.name === name; });
		var $qlist = this.tab_categories.find('#question-list');

		if (!cat || !(cat.questions || []).length) {
			$qlist.html('<p class="text-muted">' + __('No questions in this category.') + '</p>');
			return;
		}

		var rows = cat.questions.map(function(q) {
			return `<tr>
				<td style="width:85%">${frappe.utils.escape_html(q.question || '')}</td>
				<td class="text-right">
					<button class="btn btn-xs btn-danger delete-question-btn" data-name="${frappe.utils.escape_html(q.name)}" title="${__('Delete')}">
						<i class="fa fa-trash"></i>
					</button>
				</td>
			</tr>`;
		}).join('');

		$qlist.html(`<table class="table table-condensed"><tbody>${rows}</tbody></table>`);
	}

	// ============================================================
	// TAB 2: Scoring & Departments
	// ============================================================
	render_scoring_tab() {
		var me = this;
		var settings = this.data.settings || {};
		var nearness_factors = this.data.nearness_factors || [];

		this.tab_scoring.html(`
			<div class="row">
				<div class="col-md-6">
					<div class="panel panel-default">
						<div class="panel-heading"><b>${__('Value Scoring Settings')}</b></div>
						<div class="panel-body">
							<div class="form-group">
								<label>${__('Questions per Category')}</label>
								<input type="number" class="form-control" id="setting-questions-per-cat"
									value="${settings.questions_per_category || 3}" min="1" max="20">
							</div>
							<div class="form-group">
								<label>${__('Max Surveys per Employee')}</label>
								<input type="number" class="form-control" id="setting-max-per-employee"
									value="${settings.max_surveys_per_employee || 10}" min="1" max="50">
							</div>
							<div class="form-group">
								<label>${__('Max Surveys per Reviewer')}</label>
								<input type="number" class="form-control" id="setting-max-per-reviewer"
									value="${settings.max_surveys_per_reviewer || 10}" min="1" max="50">
							</div>
							<button class="btn btn-primary" id="save-settings-btn">
								<i class="fa fa-save"></i> ${__('Save Settings')}
							</button>
						</div>
					</div>
				</div>
				<div class="col-md-6">
					<div class="panel panel-default">
						<div class="panel-heading">
							<b>${__('Departmental Nearness Factors')}</b>
							<button class="btn btn-xs btn-primary float-right" id="add-nearness-btn">
								<i class="fa fa-plus"></i> ${__('Add')}
							</button>
						</div>
						<div class="panel-body" style="max-height:480px;overflow-y:auto;">
							<div id="nearness-list"></div>
						</div>
					</div>
				</div>
			</div>
		`);

		this.tab_scoring.find('#save-settings-btn').on('click', function() {
			var existing = me.data.settings || {};
			var data = {
				questions_per_category: parseInt(me.tab_scoring.find('#setting-questions-per-cat').val(), 10) || 3,
				max_surveys_per_employee: parseInt(me.tab_scoring.find('#setting-max-per-employee').val(), 10) || 10,
				max_surveys_per_reviewer: parseInt(me.tab_scoring.find('#setting-max-per-reviewer').val(), 10) || 10,
				enable_scheduled_generation: existing.enable_scheduled_generation || 0,
				generation_frequency: existing.generation_frequency || '',
				exclude_rated: existing.exclude_rated || [],
				exclude_rating: existing.exclude_rating || []
			};

			frappe.call({
				method: 'survey_app.survey_config.save_scoring_settings',
				args: { settings_data: data },
				freeze: true,
				callback: function(r) {
					if (r.exc) return;
					frappe.show_alert({ message: __('Settings saved'), indicator: 'green' });
					me.load_data();
				}
			});
		});

		var $nlist = this.tab_scoring.find('#nearness-list');
		if (!nearness_factors.length) {
			$nlist.html('<p class="text-muted">' + __('No nearness factors defined. Add relationships between departments.') + '</p>');
		} else {
			var nrows = nearness_factors.map(function(nf) {
				return `<tr>
					<td>${frappe.utils.escape_html(nf.department || '')}</td>
					<td class="text-muted">→</td>
					<td>${frappe.utils.escape_html(nf.department2 || '')}</td>
					<td><span class="badge">${frappe.utils.escape_html(String(nf.factor))}</span></td>
					<td class="text-right">
						<button class="btn btn-xs btn-danger delete-nearness-btn" data-name="${frappe.utils.escape_html(nf.name)}">
							<i class="fa fa-trash"></i>
						</button>
					</td>
				</tr>`;
			}).join('');

			$nlist.html(`
				<table class="table table-condensed">
					<thead>
						<tr>
							<th>${__('Department')}</th>
							<th></th>
							<th>${__('Related')}</th>
							<th>${__('Factor')}</th>
							<th></th>
						</tr>
					</thead>
					<tbody>${nrows}</tbody>
				</table>
			`);
		}

		this.tab_scoring.find('#add-nearness-btn').on('click', function() {
			var d = new frappe.ui.Dialog({
				title: __('Add Nearness Factor'),
				fields: [
					{ label: __('Department'), fieldname: 'dept1', fieldtype: 'Link', options: 'Department', reqd: 1 },
					{ label: __('Related Department'), fieldname: 'dept2', fieldtype: 'Link', options: 'Department', reqd: 1 },
					{
						label: __('Factor'),
						fieldname: 'factor',
						fieldtype: 'Float',
						reqd: 1,
						description: __('Weight for cross-department review allocation')
					}
				],
				primary_action_label: __('Add'),
				primary_action: function(values) {
					if (values.dept1 === values.dept2) {
						frappe.msgprint(__('Departments must be different.'));
						return;
					}
					frappe.call({
						method: 'survey_app.survey_config.save_nearness_factor',
						args: {
							department: values.dept1,
							department2: values.dept2,
							factor: values.factor
						},
						callback: function(r) {
							if (r.exc) return;
							d.hide();
							frappe.show_alert({ message: __('Nearness factor saved'), indicator: 'green' });
							me.load_data();
						}
					});
				}
			});
			d.show();
		});

		$nlist.on('click', '.delete-nearness-btn', function() {
			var name = $(this).data('name');
			frappe.confirm(__('Delete this nearness factor?'), function() {
				frappe.call({
					method: 'survey_app.survey_config.delete_nearness_factor',
					args: { name: name },
					callback: function(r) {
						if (r.exc) return;
						frappe.show_alert({ message: __('Nearness factor deleted'), indicator: 'green' });
						me.load_data();
					}
				});
			});
		});
	}

	// ============================================================
	// TAB 3: Automation
	// ============================================================
	render_automation_tab() {
		var me = this;
		var settings = this.data.settings || {};

		this.tab_automation.html(`
			<div class="row">
				<div class="col-md-8 offset-md-2 col-md-offset-2">
					<div class="panel panel-default">
						<div class="panel-heading"><b><i class="fa fa-clock-o"></i> ${__('Automatic Survey Generation')}</b></div>
						<div class="panel-body">
							<p class="text-muted">
								${__('Configure how often 360° surveys are generated automatically. Short intervals are for testing only.')}
							</p>
							<div class="checkbox" style="margin-top:8px;">
								<label>
									<input type="checkbox" id="setting-auto-generate" ${settings.enable_scheduled_generation ? 'checked' : ''}>
									<b>${__('Enable Automatic Survey Generation')}</b>
								</label>
							</div>
							<div class="form-group" style="margin-top:14px;">
								<label>${__('Generate Every')}</label>
								<select class="form-control" id="setting-frequency">
									<option value="">${__('Select frequency...')}</option>
									<option value="Every 10 Minutes">${__('Every 10 Minutes')} (${__('Testing')})</option>
									<option value="Hourly">${__('Hourly')} (${__('Testing')})</option>
									<option value="Daily">${__('Daily')}</option>
									<option value="Weekly">${__('Weekly')}</option>
									<option value="Monthly">${__('Monthly')}</option>
									<option value="Quarterly">${__('Quarterly')}</option>
									<option value="Bi-Annually">${__('Bi-Annually')}</option>
									<option value="Yearly">${__('Yearly')}</option>
								</select>
								<p class="help-box small text-muted" style="margin-top:6px;">
									${__('Scheduler checks every 5 minutes. Use “Every 10 Minutes” or “Hourly” only for testing.')}
								</p>
							</div>
							${settings.last_generation_date
								? '<p class="text-muted small" style="margin-top:8px;">' + __('Last generated') + ': <b>' + frappe.utils.escape_html(settings.last_generation_date) + '</b></p>'
								: '<p class="text-muted small" style="margin-top:8px;">' + __('Not generated yet — next scheduler tick will run if enabled.') + '</p>'}

							<div id="countdown-panel" class="countdown-panel off">
								<div class="countdown-label">${__('Next generation in')}</div>
								<div class="countdown-value" id="countdown-value">—</div>
								<div class="countdown-meta" id="countdown-meta"></div>
							</div>

							<div style="margin-top:16px;">
								<button class="btn btn-primary" id="save-automation-btn">
									<i class="fa fa-save"></i> ${__('Save Automation')}
								</button>
								<button class="btn btn-default" id="run-auto-gen-now-btn">
									<i class="fa fa-bolt"></i> ${__('Run Now')}
								</button>
								<button class="btn btn-default" id="check-auto-gen-status-btn">
									<i class="fa fa-info-circle"></i> ${__('Check Status')}
								</button>
							</div>
							<div id="auto-gen-status" style="margin-top:14px;"></div>
						</div>
					</div>
				</div>
			</div>
		`);

		if (settings.generation_frequency) {
			this.tab_automation.find('#setting-frequency').val(settings.generation_frequency);
		}

		this.tab_automation.find('#setting-auto-generate, #setting-frequency').on('change', function() {
			me.refresh_countdown_from_form();
		});

		this.tab_automation.find('#save-automation-btn').on('click', function() {
			var freq = me.tab_automation.find('#setting-frequency').val() || '';
			var enabled = me.tab_automation.find('#setting-auto-generate').is(':checked') ? 1 : 0;

			if (enabled && !freq) {
				frappe.msgprint(__('Please select a generation frequency when automatic generation is enabled.'));
				return;
			}

			var existing = me.data.settings || {};
			var data = {
				questions_per_category: existing.questions_per_category || 3,
				max_surveys_per_employee: existing.max_surveys_per_employee || 10,
				max_surveys_per_reviewer: existing.max_surveys_per_reviewer || 10,
				enable_scheduled_generation: enabled,
				generation_frequency: freq,
				exclude_rated: existing.exclude_rated || [],
				exclude_rating: existing.exclude_rating || []
			};

			frappe.call({
				method: 'survey_app.survey_config.save_scoring_settings',
				args: { settings_data: data },
				freeze: true,
				callback: function(r) {
					if (r.exc) return;
					frappe.show_alert({ message: __('Automation settings saved'), indicator: 'green' });
					me.active_tab = 'automation';
					me.load_data();
				}
			});
		});

		this.tab_automation.find('#run-auto-gen-now-btn').on('click', function() {
			frappe.confirm(
				__('Run automatic survey generation now? This bypasses the interval check.'),
				function() {
					frappe.call({
						method: 'survey_app.surveys.auto_generate_if_due',
						args: { force: 1 },
						freeze: true,
						freeze_message: __('Generating surveys...'),
						callback: function(r) {
							if (r.exc) return;
							me.show_auto_gen_status(r.message);
							me.load_data();
							if (r.message && r.message.status === 'generated') {
								me.switch_tab('trail');
							} else {
								me.active_tab = 'automation';
							}
						}
					});
				}
			);
		});

		this.tab_automation.find('#check-auto-gen-status-btn').on('click', function() {
			frappe.call({
				method: 'survey_app.surveys.get_auto_generation_status',
				callback: function(r) {
					if (r.exc) return;
					me.show_auto_gen_status(r.message);
					me.apply_countdown_status(r.message);
				}
			});
		});

		this.refresh_countdown_from_server();
	}

	refresh_countdown_from_form() {
		var enabled = this.tab_automation.find('#setting-auto-generate').is(':checked');
		var freq = this.tab_automation.find('#setting-frequency').val() || '';

		if (!enabled) {
			this.show_countdown_idle(__('Automation disabled'));
			return;
		}
		if (!freq) {
			this.show_countdown_idle(__('Select a frequency'));
			return;
		}

		// Prefer live saved status if form matches saved settings
		var settings = (this.data && this.data.settings) || {};
		if (settings.enable_scheduled_generation && settings.generation_frequency === freq) {
			this.refresh_countdown_from_server();
			return;
		}

		this.show_countdown_idle(__('Save automation to start countdown'));
	}

	refresh_countdown_from_server() {
		var me = this;
		var enabled = this.tab_automation.find('#setting-auto-generate').is(':checked');
		if (!enabled) {
			this.show_countdown_idle(__('Automation disabled'));
			return;
		}

		frappe.call({
			method: 'survey_app.surveys.get_auto_generation_status',
			callback: function(r) {
				if (r.exc) return;
				me.apply_countdown_status(r.message);
			}
		});
	}

	apply_countdown_status(info) {
		if (!info) return;

		if (!info.enabled) {
			this.show_countdown_idle(__('Automation disabled'));
			return;
		}
		if (info.status === 'no_frequency' || !info.frequency) {
			this.show_countdown_idle(__('Select a frequency'));
			return;
		}
		if (info.status === 'unknown_frequency') {
			this.show_countdown_idle(__('Unknown frequency'));
			return;
		}

		var seconds = parseInt(info.seconds_remaining, 10);
		if (isNaN(seconds)) seconds = 0;

		if (info.status === 'due' || seconds <= 0) {
			this.stop_countdown();
			this.show_countdown_due(info);
			return;
		}

		this._countdown_target_ms = Date.now() + (seconds * 1000);
		this._countdown_next_run = info.next_run || '';
		this._countdown_frequency = info.frequency || '';
		this.start_countdown();
	}

	show_countdown_idle(message) {
		this.stop_countdown();
		var $panel = this.tab_automation.find('#countdown-panel');
		if (!$panel.length) return;
		$panel.removeClass('due').addClass('off');
		$panel.find('#countdown-value').text('—');
		$panel.find('#countdown-meta').text(message || '');
	}

	show_countdown_due(info) {
		var $panel = this.tab_automation.find('#countdown-panel');
		if (!$panel.length) return;
		$panel.removeClass('off').addClass('due');
		$panel.find('#countdown-value').text(__('Due now'));
		var meta = [];
		if (info && info.frequency) meta.push(__('Frequency') + ': ' + info.frequency);
		meta.push(__('Waiting for next scheduler check (up to 5 minutes)'));
		$panel.find('#countdown-meta').text(meta.join(' · '));
	}

	start_countdown() {
		var me = this;
		this.stop_countdown();
		this.tick_countdown();
		this._countdown_timer = setInterval(function() {
			me.tick_countdown();
		}, 1000);
	}

	stop_countdown() {
		if (this._countdown_timer) {
			clearInterval(this._countdown_timer);
			this._countdown_timer = null;
		}
	}

	tick_countdown() {
		var $panel = this.tab_automation.find('#countdown-panel');
		if (!$panel.length || !this._countdown_target_ms) return;

		var remaining_ms = this._countdown_target_ms - Date.now();
		if (remaining_ms <= 0) {
			this.stop_countdown();
			this.show_countdown_due({
				frequency: this._countdown_frequency,
				next_run: this._countdown_next_run
			});
			// Re-check server status shortly after due
			var me = this;
			setTimeout(function() { me.refresh_countdown_from_server(); }, 5000);
			return;
		}

		$panel.removeClass('off due');
		$panel.find('#countdown-value').text(this.format_countdown(remaining_ms));
		var meta = [];
		if (this._countdown_frequency) meta.push(__('Every') + ' ' + this._countdown_frequency);
		if (this._countdown_next_run) meta.push(__('Due at') + ' ' + this._countdown_next_run);
		$panel.find('#countdown-meta').text(meta.join(' · '));
	}

	format_countdown(ms) {
		var total = Math.max(0, Math.floor(ms / 1000));
		var days = Math.floor(total / 86400);
		var hours = Math.floor((total % 86400) / 3600);
		var minutes = Math.floor((total % 3600) / 60);
		var seconds = total % 60;
		var pad = function(n) { return String(n).padStart(2, '0'); };

		if (days > 0) {
			return days + 'd ' + pad(hours) + ':' + pad(minutes) + ':' + pad(seconds);
		}
		return pad(hours) + ':' + pad(minutes) + ':' + pad(seconds);
	}

	show_auto_gen_status(info) {
		if (!info) return;
		var $box = this.tab_automation.find('#auto-gen-status');
		if (!$box.length) return;

		var status = info.status || '';
		var cls = 'alert-info';
		var title = __('Status');

		if (status === 'generated' || status === 'due') {
			cls = 'alert-success';
			title = status === 'generated' ? __('Generated') : __('Due now');
		} else if (status === 'not_due') {
			cls = 'alert-warning';
			title = __('Not due yet');
		} else if (status === 'disabled' || status === 'no_frequency' || status === 'error' || status === 'unknown_frequency') {
			cls = 'alert-danger';
			title = __(status.replace(/_/g, ' '));
		}

		var lines = [
			'<b>' + frappe.utils.escape_html(title) + '</b>',
			info.frequency ? (__('Frequency') + ': ' + frappe.utils.escape_html(info.frequency)) : '',
			info.last_generation ? (__('Last') + ': ' + frappe.utils.escape_html(info.last_generation)) : '',
			info.next_run ? (__('Next') + ': ' + frappe.utils.escape_html(info.next_run)) : '',
			info.seconds_remaining != null && info.status === 'not_due'
				? (__('Countdown') + ': ' + this.format_countdown((info.seconds_remaining || 0) * 1000))
				: '',
			info.created != null ? (__('Created') + ': ' + info.created) : '',
			info.log ? (__('Log') + ': <a href="/app/survey-generation-log/' + encodeURIComponent(info.log) + '">' + frappe.utils.escape_html(info.log) + '</a>') : '',
			info.message ? frappe.utils.escape_html(info.message) : ''
		].filter(Boolean);

		$box.html('<div class="alert ' + cls + '" style="margin:0;">' + lines.join('<br>') + '</div>');
	}

	// ============================================================
	// TAB 4: Generate Surveys
	// ============================================================
	render_generate_tab() {
		var me = this;

		this.tab_generate.html(`
			<div class="row">
				<div class="col-md-8 col-md-offset-2 offset-md-2">
					<div class="panel panel-default">
						<div class="panel-heading"><b>${__('Generate 360° Surveys')}</b></div>
						<div class="panel-body">
							<p class="text-muted">
								${__('Preview the allocation based on current scoring settings, then generate surveys for all active employees.')}
							</p>
							<div id="preview-section"></div>
							<div style="text-align:center;margin-top:20px;">
								<button class="btn btn-default" id="preview-surveys-btn">
									<i class="fa fa-eye"></i> ${__('Preview')}
								</button>
								<button class="btn btn-primary" id="generate-surveys-btn">
									<i class="fa fa-play"></i> ${__('Generate Surveys')}
								</button>
							</div>
							<div id="generate-result" style="margin-top:20px;"></div>
						</div>
					</div>
				</div>
			</div>
		`);

		this.tab_generate.find('#preview-surveys-btn').on('click', function() {
			frappe.call({
				method: 'survey_app.survey_config.preview_surveys',
				freeze: true,
				freeze_message: __('Loading preview...'),
				callback: function(r) {
					if (r.exc || !r.message) {
						me.tab_generate.find('#preview-section').html(
							'<div class="alert alert-danger">' + __('Preview failed. Check error logs.') + '</div>'
						);
						return;
					}

					var p = r.message;
					var by_dept = p.by_department || {};
					var dept_list = Object.keys(by_dept).map(function(d) {
						return `<tr>
							<td>${frappe.utils.escape_html(d)}</td>
							<td>${by_dept[d].count}</td>
						</tr>`;
					}).join('');

					me.tab_generate.find('#preview-section').html(`
						<div class="alert alert-info" style="margin-bottom:16px;">
							<p><b>${p.total_employees || 0}</b> ${__('active employees')}</p>
							<p><b>~${p.estimated_surveys || 0}</b> ${__('estimated surveys')}</p>
							<p>${__('Caps')}: ${(p.caps && p.caps.per_reviewer) || 0} ${__('per reviewer')},
								${(p.caps && p.caps.per_employee) || 0} ${__('per employee')}</p>
							<p>${__('Nearness factors')}: ${p.nearness_factors_count || 0}</p>
						</div>
						<p><b>${__('Employees by Department')}:</b></p>
						<table class="table table-condensed">
							<thead><tr><th>${__('Department')}</th><th>${__('Count')}</th></tr></thead>
							<tbody>${dept_list || '<tr><td colspan="2" class="text-muted">' + __('No active employees') + '</td></tr>'}</tbody>
						</table>
					`);
				}
			});
		});

		this.tab_generate.find('#generate-surveys-btn').on('click', function() {
			frappe.confirm(
				__('This will generate 360-degree surveys for all active employees based on current settings. Continue?'),
				function() {
					frappe.call({
						method: 'survey_app.surveys.generate_capped_surveys',
						args: { trigger_source: 'Manual' },
						freeze: true,
						freeze_message: __('Generating surveys...'),
						callback: function(r) {
							if (!r.exc) {
								var msg = __('Surveys generated successfully!');
								var log_link = '';
								if (r.message && typeof r.message === 'object') {
									if (r.message.created != null) {
										msg = __('Created {0} surveys.', [r.message.created]);
									} else if (r.message.count != null) {
										msg = __('Created {0} surveys.', [r.message.count]);
									}
									if (r.message.log) {
										log_link = ' <a href="/app/survey-generation-log/' + encodeURIComponent(r.message.log) + '">' +
											__('View Generation Log') + '</a>';
									}
								}
								me.tab_generate.find('#generate-result').html(
									'<div class="alert alert-success">' + msg +
									' <a href="/app/survey">' + __('View Survey List') + '</a>' +
									log_link + '</div>'
								);
								me.load_data();
								me.switch_tab('trail');
							} else {
								me.tab_generate.find('#generate-result').html(
									'<div class="alert alert-danger">' + __('Generation failed. Check error logs.') + '</div>'
								);
							}
						}
					});
				}
			);
		});
	}

	// ============================================================
	// TAB 5: Generation Trail
	// ============================================================
	render_trail_tab() {
		var me = this;
		var logs = (this.data && this.data.generation_trail) || [];

		this.tab_trail.html(`
			<div class="panel panel-default">
				<div class="panel-heading" style="display:flex;justify-content:space-between;align-items:center;">
					<b><i class="fa fa-history"></i> ${__('Automatic Generation Trail')}</b>
					<span>
						<button class="btn btn-xs btn-default" id="refresh-trail-btn">
							<i class="fa fa-refresh"></i> ${__('Refresh')}
						</button>
						<a class="btn btn-xs btn-primary" href="/app/survey-generation-log">
							${__('Open Full Log')}
						</a>
					</span>
				</div>
				<div class="panel-body" id="trail-list"></div>
			</div>
		`);

		var $list = this.tab_trail.find('#trail-list');

		if (!logs.length) {
			$list.html('<p class="text-muted">' + __('No generation runs yet. Use Generate Surveys or enable automatic generation.') + '</p>');
		} else {
			logs.forEach(function(log) {
				$list.append(me.render_trail_run(log));
			});
		}

		this.tab_trail.find('#refresh-trail-btn').on('click', function() {
			frappe.call({
				method: 'survey_app.survey_config.get_generation_trail',
				args: { limit: 20 },
				callback: function(r) {
					if (r.exc) return;
					me.data.generation_trail = (r.message && r.message.logs) || [];
					me.render_trail_tab();
				}
			});
		});

		$list.on('click', '.trail-run-header', function() {
			$(this).closest('.trail-run').toggleClass('open');
		});
	}

	render_trail_run(log) {
		var status = log.status || 'Success';
		var details = log.details || [];
		var detail_rows = details.map(function(d) {
			return `<tr>
				<td><a href="/app/survey/${encodeURIComponent(d.survey || '')}">${frappe.utils.escape_html(d.survey || '')}</a></td>
				<td>${frappe.utils.escape_html(d.reviewer_name || d.reviewer || '')}<br>
					<small class="text-muted">${frappe.utils.escape_html(d.reviewer_email || '')}</small></td>
				<td>${frappe.utils.escape_html(d.reviewee_name || d.reviewee || '')}</td>
				<td>${d.email_sent ? '<span class="text-success">' + __('Yes') + '</span>' : '<span class="text-muted">' + __('No') + '</span>'}</td>
				<td>${d.task ? '<a href="/app/task/' + encodeURIComponent(d.task) + '">' + frappe.utils.escape_html(d.task) + '</a>' : '—'}</td>
			</tr>`;
		}).join('');

		var $run = $(`
			<div class="trail-run">
				<div class="trail-run-header">
					<div>
						<span class="status-pill status-${frappe.utils.escape_html(status)}">${frappe.utils.escape_html(status)}</span>
						<b style="margin-left:8px;">${frappe.utils.escape_html(log.triggered_at || '')}</b>
						<span class="text-muted" style="margin-left:8px;">${frappe.utils.escape_html(log.trigger_source || '')}</span>
						${log.frequency ? '<span class="text-muted"> · ' + frappe.utils.escape_html(log.frequency) + '</span>' : ''}
					</div>
					<div class="text-muted small">
						${__('Surveys')}: <b>${log.surveys_created || 0}</b>
						&nbsp;·&nbsp; ${__('Emails')}: <b>${log.emails_sent || 0}</b>
						&nbsp;·&nbsp; <a href="/app/survey-generation-log/${encodeURIComponent(log.name || '')}">${frappe.utils.escape_html(log.name || '')}</a>
					</div>
				</div>
				<div class="trail-run-body">
					${log.summary ? '<p class="text-muted">' + frappe.utils.escape_html(log.summary) + '</p>' : ''}
					${log.error_message ? '<div class="alert alert-danger">' + frappe.utils.escape_html(log.error_message) + '</div>' : ''}
					${details.length ? `
						<table class="table table-condensed">
							<thead>
								<tr>
									<th>${__('Survey')}</th>
									<th>${__('Sent To (Reviewer)')}</th>
									<th>${__('Reviewee')}</th>
									<th>${__('Email')}</th>
									<th>${__('Task')}</th>
								</tr>
							</thead>
							<tbody>${detail_rows}</tbody>
						</table>
					` : '<p class="text-muted">' + __('No recipient details for this run.') + '</p>'}
				</div>
			</div>
		`);
		return $run;
	}
};

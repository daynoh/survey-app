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
						<button type="button" class="nav-link" data-tab="roles" role="tab">
							<i class="fa fa-users"></i> ${__('Roles & Org')}
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
					<div role="tabpanel" class="tab-pane fade" id="tab-roles"></div>
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
		this.tab_roles = this.$root.find('#tab-roles');
		this.tab_automation = this.$root.find('#tab-automation');
		this.tab_generate = this.$root.find('#tab-generate');
		this.tab_trail = this.$root.find('#tab-trail');
		this._team_leader_rows = [];

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
				this.render_roles_tab();
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
								<label>${__('Balanced Reviews Received per Employee')}</label>
								<input type="number" class="form-control" id="setting-balanced-reviews-per-employee"
									value="${settings.balanced_reviews_per_employee || 6}" min="1" max="50">
								<p class="help-block text-muted" style="margin-top:6px;font-size:12px;">
									${__('Normal recurring cycles aim for this many aggregate reviews per employee. Leadership assignments count toward the target.')}
								</p>
							</div>
							<div class="form-group">
								<label>${__('Balanced Maximum Surveys per Reviewer (per cycle)')}</label>
								<input type="number" class="form-control" id="setting-balanced-max-per-reviewer"
									value="${settings.balanced_max_surveys_per_reviewer || 10}" min="1" max="100">
							</div>
							<div class="form-group">
								<label>${__('Legacy / Baseline Review Target')}</label>
								<input type="number" class="form-control" id="setting-max-per-employee"
									value="${settings.max_surveys_per_employee || 10}" min="1" max="50">
								<p class="help-block text-muted" style="margin-top:6px;font-size:12px;">
									${__('Used by Legacy Capped generation and as the external-coverage basis for Full Baseline Matrix cycles.')}
								</p>
							</div>
							<div class="form-group">
								<label>${__('Min Surveys per Reviewer (per batch)')}</label>
								<input type="number" class="form-control" id="setting-min-per-batch"
									value="${settings.min_surveys_per_batch || 3}" min="1" max="50">
								<p class="help-block text-muted" style="margin-top:6px;font-size:12px;">
									${__('Required reviews are split evenly across survey sends in the reporting period (completeness cycle). Min floors each send; max caps each send.')}
								</p>
							</div>
							<div class="form-group">
								<label>${__('Max Surveys per Reviewer (per batch)')}</label>
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
			var data = Object.assign({}, existing, {
				questions_per_category: parseInt(me.tab_scoring.find('#setting-questions-per-cat').val(), 10) || 3,
				balanced_reviews_per_employee: parseInt(me.tab_scoring.find('#setting-balanced-reviews-per-employee').val(), 10) || 6,
				balanced_max_surveys_per_reviewer: parseInt(me.tab_scoring.find('#setting-balanced-max-per-reviewer').val(), 10) || 10,
				max_surveys_per_employee: parseInt(me.tab_scoring.find('#setting-max-per-employee').val(), 10) || 10,
				min_surveys_per_batch: parseInt(me.tab_scoring.find('#setting-min-per-batch').val(), 10) || 3,
				max_surveys_per_reviewer: parseInt(me.tab_scoring.find('#setting-max-per-reviewer').val(), 10) || 10,
				exclude_rated: existing.exclude_rated || [],
				exclude_rating: existing.exclude_rating || []
			});

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
	// TAB 3: Roles & Org
	// ============================================================
	render_roles_tab() {
		var me = this;
		var settings = this.data.settings || {};
		var departments = this.data.departments || [];
		this._team_leader_rows = (settings.team_leaders || []).map(function (r) {
			return { department: r.department, employee: r.employee, employee_name: r.employee_name || '' };
		});
		if (!this._team_leader_rows.length) {
			this._team_leader_rows.push({ department: '', employee: '', employee_name: '' });
		}

		var dept_opts = departments.map(function (d) {
			return '<option value="' + frappe.utils.escape_html(d.name) + '">' +
				frappe.utils.escape_html(d.name) + '</option>';
		}).join('');

		this.tab_roles.html(`
			<div class="row">
				<div class="col-md-10 offset-md-1 col-md-offset-1">
					<div class="panel panel-default">
						<div class="panel-heading"><b><i class="fa fa-users"></i> ${__('Roles & Organisation')}</b></div>
						<div class="panel-body">
							<p class="text-muted">
								${__('Assign the Managing Director and Team Leaders. Hybrid mode uses your manual picks first, then Employee org data, then Frappe roles.')}
							</p>
							<div class="form-group">
								<label>${__('Role Resolution Mode')}</label>
								<select class="form-control" id="role-mode">
									<option value="Hybrid">${__('Hybrid (Manual → Org → Role)')}</option>
									<option value="Manual">${__('Manual only')}</option>
									<option value="Org">${__('Employee org data')}</option>
									<option value="Role">${__('Frappe roles')}</option>
								</select>
							</div>
							<div class="form-group">
								<label>${__('Managing Director')}</label>
								<div id="md-employee-link"></div>
							</div>
							<div class="form-group">
								<label>${__('Team Leader Designations')} <span class="text-muted">(${__('optional, comma-separated')})</span></label>
								<input type="text" class="form-control" id="tl-designations"
									placeholder="${__('Team Lead, Team Leader')}"
									value="${frappe.utils.escape_html(settings.team_leader_designations || '')}">
							</div>
							<label>${__('Team Leaders by Department')}</label>
							<div id="tl-rows"></div>
							<button class="btn btn-xs btn-default" id="add-tl-row" style="margin-top:8px;">
								<i class="fa fa-plus"></i> ${__('Add Team Leader')}
							</button>
							<div style="margin-top:16px;">
								<button class="btn btn-primary" id="save-roles-btn">
									<i class="fa fa-save"></i> ${__('Save Roles')}
								</button>
								<button class="btn btn-default" id="preview-roles-btn">
									<i class="fa fa-eye"></i> ${__('Preview Resolved Roster')}
								</button>
								<button class="btn btn-default" id="preview-load-btn">
									<i class="fa fa-calculator"></i> ${__('Preview Cycle Load')}
								</button>
								<button class="btn btn-default" id="preview-assignments-btn">
									<i class="fa fa-random"></i> ${__('Who Reviews Who')}
								</button>
							</div>
							<div id="roles-preview" style="margin-top:16px;"></div>
						</div>
					</div>
				</div>
			</div>
		`);

		this.tab_roles.find('#role-mode').val(settings.role_resolution_mode || 'Hybrid');
		this._md_control = frappe.ui.form.make_control({
			parent: this.tab_roles.find('#md-employee-link'),
			df: {
				fieldtype: 'Link',
				options: 'Employee',
				fieldname: 'md_employee',
				label: __('Managing Director'),
				default: settings.md_employee || ''
			},
			render_input: true
		});
		this._md_control.set_value(settings.md_employee || '');

		this._render_tl_rows(dept_opts);

		this.tab_roles.find('#add-tl-row').on('click', function () {
			me._team_leader_rows.push({ department: '', employee: '', employee_name: '' });
			me._render_tl_rows(dept_opts);
		});

		this.tab_roles.find('#save-roles-btn').on('click', function () {
			me._save_team_leaders();
		});

		this.tab_roles.find('#preview-roles-btn').on('click', function () {
			frappe.call({
				method: 'survey_app.survey_cycle.resolve_org_roles',
				freeze: true,
				callback: function (r) {
					if (r.exc || !r.message) return;
					me._show_roles_preview(r.message);
				}
			});
		});

		this.tab_roles.find('#preview-load-btn').on('click', function () {
			frappe.call({
				method: 'survey_app.survey_cycle.preview_cycle_load',
				freeze: true,
				callback: function (r) {
					if (r.exc || !r.message) return;
					me._show_load_preview(r.message);
				}
			});
		});

		this.tab_roles.find('#preview-assignments-btn').on('click', function () {
			frappe.call({
				method: 'survey_app.survey_cycle.preview_cycle_assignments',
				freeze: true,
				freeze_message: __('Preparing assignment preview...'),
				callback: function (r) {
					if (r.exc || !r.message) return;
					me._show_assignment_preview(r.message);
				}
			});
		});
	}

	_render_tl_rows(dept_opts) {
		var me = this;
		var $box = this.tab_roles.find('#tl-rows').empty();
		this._team_leader_rows.forEach(function (row, idx) {
			var $row = $(`
				<div class="row tl-row" data-idx="${idx}" style="margin-bottom:8px;align-items:center;">
					<div class="col-sm-5">
						<select class="form-control tl-dept">${dept_opts}</select>
					</div>
					<div class="col-sm-5 tl-emp"></div>
					<div class="col-sm-2">
						<button class="btn btn-xs btn-default tl-remove" type="button"><i class="fa fa-trash"></i></button>
					</div>
				</div>
			`);
			$row.find('.tl-dept').val(row.department || '');
			var ctrl = frappe.ui.form.make_control({
				parent: $row.find('.tl-emp'),
				df: {
					fieldtype: 'Link',
					options: 'Employee',
					fieldname: 'tl_employee_' + idx,
					default: row.employee || ''
				},
				render_input: true
			});
			ctrl.set_value(row.employee || '');
			row._ctrl = ctrl;
			$row.find('.tl-remove').on('click', function () {
				me._collect_tl_rows();
				me._team_leader_rows.splice(idx, 1);
				if (!me._team_leader_rows.length) {
					me._team_leader_rows.push({ department: '', employee: '', employee_name: '' });
				}
				me._render_tl_rows(dept_opts);
			});
			$box.append($row);
		});
	}

	_collect_tl_rows() {
		var me = this;
		this.tab_roles.find('.tl-row').each(function () {
			var idx = cint($(this).data('idx'));
			if (!me._team_leader_rows[idx]) return;
			me._team_leader_rows[idx].department = $(this).find('.tl-dept').val() || '';
			me._team_leader_rows[idx].employee = (me._team_leader_rows[idx]._ctrl && me._team_leader_rows[idx]._ctrl.get_value()) || '';
		});
	}

	_save_team_leaders(on_done) {
		var me = this;
		this._collect_tl_rows();
		var existing = this.data.settings || {};
		var data = Object.assign({}, existing, {
			role_resolution_mode: this.tab_roles.find('#role-mode').val() || 'Hybrid',
			md_employee: (this._md_control && this._md_control.get_value()) || '',
			team_leader_designations: this.tab_roles.find('#tl-designations').val() || '',
			team_leaders: this._team_leader_rows.filter(function (r) { return r.department && r.employee; })
		});
		frappe.call({
			method: 'survey_app.survey_config.save_scoring_settings',
			args: { settings_data: data },
			freeze: true,
			callback: function (r) {
				if (r.exc) return;
				frappe.show_alert({ message: __('Roles saved'), indicator: 'green' });
				me.active_tab = 'roles';
				if (on_done) {
					on_done();
				} else {
					me.load_data();
				}
			}
		});
	}

	_show_roles_preview(data) {
		var me = this;
		var md = data.md;
		var html = '<div class="panel panel-default"><div class="panel-heading"><b>' + __('Resolved Roster') + '</b></div><div class="panel-body">';
		html += '<p><b>' + __('MD') + ':</b> ' +
			(md ? frappe.utils.escape_html(md.employee_name + ' (' + md.source + ')') : '<span class="text-danger">' + __('Not set') + '</span>') +
			'</p>';
		if ((data.warnings || []).length) {
			html += '<div class="alert alert-warning">' + data.warnings.map(frappe.utils.escape_html).join('<br>') + '</div>';
		}
		html += '<table class="table table-bordered table-condensed"><thead><tr><th>' + __('Department') +
			'</th><th>' + __('Team Leader') + '</th><th>' + __('Source') + '</th><th>' + __('Team Size') +
			'</th><th>' + __('Actions') + '</th></tr></thead><tbody>';
		(data.roster || []).forEach(function (r) {
			var actions = '';
			if (r.team_leader) {
				actions += '<button class="btn btn-xs btn-default roster-tl-change" data-dept="' +
					frappe.utils.escape_html(r.department || '') + '" data-employee="' +
					frappe.utils.escape_html(r.team_leader || '') + '" data-name="' +
					frappe.utils.escape_html(r.team_leader_name || '') + '" title="' +
					frappe.utils.escape_html(__('Change Team Leader')) + '"><i class="fa fa-pencil"></i></button> ';
				if (r.source === 'Manual') {
					actions += '<button class="btn btn-xs btn-default roster-tl-remove" data-dept="' +
						frappe.utils.escape_html(r.department || '') + '" data-name="' +
						frappe.utils.escape_html(r.team_leader_name || '') + '" title="' +
						frappe.utils.escape_html(__('Remove manual Team Leader')) + '"><i class="fa fa-trash"></i></button>';
				}
			}
			html += '<tr><td>' + frappe.utils.escape_html(r.department || '') + '</td><td>' +
				frappe.utils.escape_html(r.team_leader_name || '—') + '</td><td>' +
				frappe.utils.escape_html(r.source || '—') + '</td><td>' + (r.team_size || 0) +
				'</td><td>' + actions + '</td></tr>';
		});
		html += '</tbody></table>';
		html += '<p class="text-muted small">' +
			__('Change sets a manual override for that department; removing a manual pick falls back to automatic (org/role) resolution.') +
			'</p>';
		html += '</div></div>';
		this.tab_roles.find('#roles-preview').html(html);

		this.tab_roles.find('.roster-tl-change').on('click', function () {
			var dept = $(this).data('dept');
			var current = $(this).data('employee') || '';
			var current_name = $(this).data('name') || '';
			var change_dialog = new frappe.ui.Dialog({
				title: __('Change Team Leader — {0}', [dept]),
				fields: [
					{ fieldtype: 'Link', fieldname: 'employee', options: 'Employee', label: __('Team Leader'), reqd: 1, default: current },
					{ fieldtype: 'HTML', fieldname: 'tl_hint',
						options: '<p class="text-muted small">' + __('Current: {0}', [current_name || '—']) + '</p>' }
				],
				primary_action_label: __('Save'),
				primary_action: function () {
					var employee = change_dialog.get_value('employee');
					if (!employee) return;
					me._collect_tl_rows();
					me._team_leader_rows = me._team_leader_rows.filter(function (r) { return r.department !== dept; });
					me._team_leader_rows.push({ department: dept, employee: employee, employee_name: '' });
					change_dialog.hide();
					me._save_team_leaders(function () {
						me.tab_roles.find('#preview-roles-btn').trigger('click');
					});
				}
			});
			change_dialog.show();
		});

		this.tab_roles.find('.roster-tl-remove').on('click', function () {
			var dept = $(this).data('dept');
			var name = $(this).data('name') || '';
			frappe.confirm(
				__('Remove {0} as manual Team Leader for {1}? Automatic resolution will apply again.', [name, dept]),
				function () {
					me._collect_tl_rows();
					me._team_leader_rows = me._team_leader_rows.filter(function (r) { return r.department !== dept; });
					if (!me._team_leader_rows.length) {
						me._team_leader_rows.push({ department: '', employee: '', employee_name: '' });
					}
					me._save_team_leaders(function () {
						me.tab_roles.find('#preview-roles-btn').trigger('click');
					});
				}
			);
		});
	}

	_show_load_preview(data) {
		var html = '<div class="panel panel-default"><div class="panel-heading"><b>' + __('Cycle Load Preview') + '</b></div><div class="panel-body">';
		html += '<p>' + __('Strategy') + ': <b>' + frappe.utils.escape_html(data.generation_strategy || 'Balanced Coverage') + '</b> · ' +
			__('Total required pairs') + ': <b>' + (data.total_pairs || 0) + '</b> · ' +
			__('Batches in cycle') + ': <b>' + (data.batches_in_cycle || 0) + '</b> · ' +
			__('Survey frequency') + ': <b>' + frappe.utils.escape_html(data.survey_frequency || '') + '</b> · ' +
			__('Min / batch') + ': <b>' + (data.min_surveys_per_batch || 3) + '</b> · ' +
			__('Max / batch') + ': <b>' + (data.max_surveys_per_reviewer || 10) + '</b></p>';
		html += '<p class="text-muted small">' + __('Reviewer load — average: {0}, minimum: {1}, maximum: {2}. Reviews received — minimum: {3}, maximum: {4}.', [
			data.average_reviewer_load || 0,
			data.minimum_reviewer_load || 0,
			data.maximum_reviewer_load || 0,
			data.minimum_reviews_received || 0,
			data.maximum_reviews_received || 0
		]) + '</p>';
		if ((data.warnings || []).length) {
			html += '<div class="alert alert-warning">' + data.warnings.map(frappe.utils.escape_html).join('<br>') + '</div>';
		}
		html += '<table class="table table-bordered table-condensed"><thead><tr><th>' + __('Reviewer') +
			'</th><th>' + __('Required / cycle') + '</th><th>' + __('Even split') +
			'</th><th>' + __('Per batch (applied)') + '</th><th>' + __('Reviews received') + '</th></tr></thead><tbody>';
		(data.load || []).slice(0, 60).forEach(function (r) {
			var flags = '';
			if (r.review_only) {
				html += '<tr><td>' + frappe.utils.escape_html(r.reviewer_name || '') +
					' <span class="label label-default">' + __('Review only') + '</span></td><td>0</td><td>—</td><td>—</td><td>' +
					(r.reviews_received || 0) + '</td></tr>';
				return;
			}
			if (r.over_cap) flags += ' ⚠';
			else if (r.under_min) flags += ' ↑';
			html += '<tr' + (r.over_cap ? ' class="danger"' : (r.under_min ? ' class="warning"' : '')) + '><td>' +
				frappe.utils.escape_html(r.reviewer_name || '') + '</td><td>' + r.required_surveys +
				'</td><td>' + (r.even_split != null ? r.even_split : r.per_batch) +
				'</td><td>' + r.per_batch + flags + '</td><td>' + (r.reviews_received || 0) + '</td></tr>';
		});
		html += '</tbody></table></div></div>';
		this.tab_roles.find('#roles-preview').html(html);
	}

	_show_assignment_preview(data) {
		var me = this;
		var rows = data.rows || [];
		var summary = data.summary || {};
		var esc = frappe.utils.escape_html;
		var rule_labels = {
			TeamLeader: __('Team Leader → Team Member'),
			Peer: __('Department Peer'),
			TL_to_MD: __('Team Leader → Managing Director'),
			Nearness: __('Departmental Nearness'),
			Other: __('Other')
		};
		var option = function (value, label) {
			return '<option value="' + esc(value || '') + '">' + esc(label || value || '') + '</option>';
		};
		var department_options = '<option value="">' + __('All departments') + '</option>' +
			(data.departments || []).map(function (department) { return option(department, department); }).join('');
		var rule_options = '<option value="">' + __('All assignment reasons') + '</option>' +
			(data.rules || []).map(function (rule) { return option(rule, rule_labels[rule] || rule); }).join('');
		var status_options = '<option value="">' + __('All statuses') + '</option>' +
			(data.statuses || []).map(function (status) { return option(status, status); }).join('');
		var cycle = data.cycle || {};
		var strategy = data.generation_strategy || cycle.generation_strategy || 'Balanced Coverage';
		var source_message = data.is_cycle_plan
			? __('This is the exact {0} plan stored for {1}. Survey batches use these reviewer–reviewee pairs.', [strategy, cycle.title || cycle.name || __('the open cycle')])
			: __('No open cycle exists. This preview uses {0}; use Build / Refresh Cycle to store the exact plan.', [strategy]);

		var dialog = new frappe.ui.Dialog({
			title: __('Who Reviews Who'),
			size: 'large',
			fields: [{ fieldtype: 'HTML', fieldname: 'assignment_preview_shell' }],
			primary_action_label: __('Close'),
			primary_action: function () { dialog.hide(); }
		});
		dialog.show();
		dialog.$wrapper.find('.modal-dialog').css({ width: '1180px', 'max-width': '96vw' });
		dialog.$wrapper.find('.modal-body').css({ 'max-height': '82vh', overflow: 'auto' });

		var warning_html = (data.warnings || []).length
			? '<div class="alert alert-warning" style="margin-bottom:12px;">' +
				(data.warnings || []).map(esc).join('<br>') + '</div>'
			: '';
		var exclusion = data.exclusion_conflicts || null;
		var exclusion_html = '';
		if (exclusion && exclusion.total) {
			var exclusion_note = __('The stored plan still contains {0} pair(s) involving {1} employee(s) now excluded from rating or being rated ({2} planned, {3} already assigned).', [
				exclusion.total,
				(exclusion.employees || []).length,
				exclusion.planned || 0,
				exclusion.assigned || 0
			]);
			exclusion_html = '<div class="alert alert-danger" style="margin-bottom:12px;"><b>' +
				__('Excluded employees are still in the plan.') + '</b> ' + esc(exclusion_note) +
				'<div class="text-muted small" style="margin-top:4px;">' +
				esc((exclusion.employees || []).join(', ')) + '</div>' +
				(exclusion.planned ?
					'<button class="btn btn-sm btn-danger purge-excluded-btn" style="margin-top:8px;">' +
					'<i class="fa fa-eraser"></i> ' + __('Remove Excluded from Plan') + '</button>' : '') +
				'</div>';
		}
		var $mount = $(`
			<div class="assignment-preview">
				<div class="alert ${data.is_cycle_plan ? 'alert-info' : 'alert-warning'}" style="margin-bottom:12px;">${esc(source_message)}</div>
				${exclusion_html}
				${warning_html}
				<div class="row" style="margin-bottom:14px;">
					<div class="col-sm-2"><div class="well well-sm"><div class="text-muted small">${__('Required pairs')}</div><div style="font-size:22px;font-weight:600;">${summary.total_pairs || 0}</div></div></div>
					<div class="col-sm-2"><div class="well well-sm"><div class="text-muted small">${__('Reviewers')}</div><div style="font-size:22px;font-weight:600;">${summary.reviewers || 0}</div></div></div>
					<div class="col-sm-2"><div class="well well-sm"><div class="text-muted small">${__('Reviewees')}</div><div style="font-size:22px;font-weight:600;">${summary.reviewees || 0}</div></div></div>
					<div class="col-sm-2"><div class="well well-sm"><div class="text-muted small">${__('Average load')}</div><div style="font-size:22px;font-weight:600;">${summary.average_load || 0}</div></div></div>
					<div class="col-sm-2"><div class="well well-sm"><div class="text-muted small">${__('Minimum load')}</div><div style="font-size:22px;font-weight:600;">${summary.minimum_load || 0}</div></div></div>
					<div class="col-sm-2"><div class="well well-sm"><div class="text-muted small">${__('Maximum load')}</div><div style="font-size:22px;font-weight:600;color:#c92a2a;">${summary.maximum_load || 0}</div></div></div>
				</div>
				<div class="row" style="margin-bottom:12px;">
					<div class="col-sm-3"><input class="form-control assignment-search" type="search" placeholder="${esc(__('Search employee name or ID'))}"></div>
					<div class="col-sm-2"><select class="form-control assignment-reviewer-dept">${department_options}</select></div>
					<div class="col-sm-2"><select class="form-control assignment-reviewee-dept">${department_options}</select></div>
					<div class="col-sm-2"><select class="form-control assignment-rule">${rule_options}</select></div>
					<div class="col-sm-2"><select class="form-control assignment-status">${status_options}</select></div>
					<div class="col-sm-1"><select class="form-control assignment-load-filter" title="${esc(__('Workload filter'))}">
						<option value="">${__('All loads')}</option>
						<option value="above_average">${__('Above average')}</option>
						<option value="maximum">${__('Maximum')}</option>
					</select></div>
				</div>
				<div class="text-muted small assignment-result-count" style="margin-bottom:8px;"></div>
				<div class="table-responsive" style="max-height:52vh;overflow:auto;border:1px solid #d1d8dd;">
					<table class="table table-bordered table-hover table-condensed" style="margin:0;">
						<thead style="position:sticky;top:0;background:#f8f9fa;z-index:1;"><tr>
							<th>${__('Reviewer')}</th><th>${__('Reviewer department')}</th><th>${__('Cycle load')}</th>
							<th>${__('Reviewee')}</th><th>${__('Reviewee department')}</th><th>${__('Reviews received')}</th>
							<th>${__('Reason')}</th><th>${__('Status / batch')}</th>
						</tr></thead>
						<tbody class="assignment-preview-rows"></tbody>
					</table>
				</div>
			</div>
		`);
		dialog.$wrapper.find('.modal-body').append($mount);

		$mount.find('.purge-excluded-btn').on('click', function () {
			frappe.confirm(
				__('Remove all planned pairs that involve employees excluded from rating or being rated? Assigned surveys are never touched.'),
				function () {
					frappe.call({
						method: 'survey_app.survey_cycle.purge_excluded_pairs',
						freeze: true,
						freeze_message: __('Removing excluded pairs...'),
						callback: function (r) {
							if (r.exc || !r.message) return;
							frappe.show_alert({
								message: __('Removed {0} pair(s); {1} remain in the plan.', [r.message.removed, r.message.remaining_pairs]),
								indicator: 'green'
							});
							dialog.hide();
							me.tab_roles.find('#preview-assignments-btn').trigger('click');
						}
					});
				}
			);
		});

		var render_rows = function () {
			var query = ($mount.find('.assignment-search').val() || '').trim().toLowerCase();
			var reviewer_department = $mount.find('.assignment-reviewer-dept').val() || '';
			var reviewee_department = $mount.find('.assignment-reviewee-dept').val() || '';
			var rule = $mount.find('.assignment-rule').val() || '';
			var status = $mount.find('.assignment-status').val() || '';
			var load_filter = $mount.find('.assignment-load-filter').val() || '';
			var filtered = rows.filter(function (row) {
				var searchable = [row.reviewer, row.reviewer_name, row.reviewee, row.reviewee_name].join(' ').toLowerCase();
				if (query && searchable.indexOf(query) === -1) return false;
				if (reviewer_department && row.reviewer_department !== reviewer_department) return false;
				if (reviewee_department && row.reviewee_department !== reviewee_department) return false;
				if (rule && row.rule_type !== rule) return false;
				if (status && row.status !== status) return false;
				if (load_filter === 'above_average' && Number(row.reviewer_cycle_load || 0) <= Number(summary.average_load || 0)) return false;
				if (load_filter === 'maximum' && Number(row.reviewer_cycle_load || 0) !== Number(summary.maximum_load || 0)) return false;
				return true;
			});
			var body = filtered.map(function (row) {
				var status_text = row.status || __('Planned');
				if (row.batch_no) status_text += ' · ' + __('Batch {0}', [row.batch_no]);
				return '<tr><td><b>' + esc(row.reviewer_name || row.reviewer || '') + '</b><div class="text-muted small">' + esc(row.reviewer || '') + '</div></td>' +
					'<td>' + esc(row.reviewer_department || '—') + '</td><td><b>' + Number(row.reviewer_cycle_load || 0) + '</b></td>' +
					'<td><b>' + esc(row.reviewee_name || row.reviewee || '') + '</b><div class="text-muted small">' + esc(row.reviewee || '') + '</div></td>' +
					'<td>' + esc(row.reviewee_department || '—') + '</td><td>' + Number(row.reviewee_coverage || 0) + '</td>' +
					'<td>' + esc(rule_labels[row.rule_type] || row.rule_type || '') + '</td><td>' + esc(status_text) + '</td></tr>';
			}).join('');
			$mount.find('.assignment-preview-rows').html(body || '<tr><td colspan="8" class="text-center text-muted">' + __('No assignments match these filters.') + '</td></tr>');
			$mount.find('.assignment-result-count').text(__('Showing {0} of {1} assignments', [filtered.length, rows.length]));
		};
		$mount.find('select').on('change', render_rows);
		$mount.find('.assignment-search').on('input', render_rows);
		render_rows();
	}

	// TAB 4: Automation & Cycle
	// ============================================================
	render_automation_tab() {
		var me = this;
		var settings = this.data.settings || {};

		this.tab_automation.html(`
			<div class="row">
				<div class="col-md-10 offset-md-1 col-md-offset-1">
					<div class="panel panel-default">
						<div class="panel-heading"><b><i class="fa fa-clock-o"></i> ${__('Automation & Cycle')}</b></div>
						<div class="panel-body">
							<div class="form-group">
								<label>${__('Generation Mode')}</label>
								<select class="form-control" id="setting-gen-mode">
									<option value="Cycle Matrix">${__('Cycle Matrix')} (${__('recommended')})</option>
									<option value="Legacy Capped">${__('Legacy Capped')}</option>
								</select>
							</div>
							<div id="cycle-strategy-panel" style="border:1px solid #d1d8dd;border-radius:8px;padding:14px 16px;margin:12px 0 18px;background:#f8fafc;">
								<div class="row">
									<div class="col-sm-8">
										<label>${__('Cycle Coverage Strategy')}</label>
										<select class="form-control" id="cycle-strategy-select">
											<option value="Balanced Coverage">${__('Balanced Coverage')} — ${__('recommended default')}</option>
											<option value="Full Baseline Matrix">${__('Full Baseline Matrix')} — ${__('first-cycle baseline only')}</option>
										</select>
										<p id="cycle-strategy-help" class="help-box small text-muted" style="margin:7px 0 0;">
											${__('Balanced Coverage spreads a representative set of reviews across the organisation while respecting leadership and departmental-nearness rules.')}
										</p>
									</div>
									<div class="col-sm-4" style="padding-top:25px;">
										<button class="btn btn-default btn-block" id="apply-cycle-strategy-btn">
											<i class="fa fa-check-circle"></i> ${__('Apply to This Cycle')}
										</button>
										<div id="cycle-strategy-lock" class="small text-muted" style="margin-top:7px;text-align:center;"></div>
									</div>
								</div>
							</div>
							<div class="checkbox">
								<label>
									<input type="checkbox" id="setting-auto-generate" ${settings.enable_scheduled_generation ? 'checked' : ''}>
									<b>${__('Enable Automatic Survey Generation')}</b>
								</label>
							</div>
							<div class="row">
								<div class="col-sm-6">
									<div class="form-group">
										<label>${__('Survey Frequency')}</label>
										<select class="form-control" id="setting-frequency">
											<option value="">${__('Select...')}</option>
											<option value="Every 10 Minutes">${__('Every 10 Minutes')} (${__('Testing')})</option>
											<option value="Hourly">${__('Hourly')}</option>
											<option value="Daily">${__('Daily')}</option>
											<option value="Weekly">${__('Weekly')}</option>
											<option value="Monthly">${__('Monthly')}</option>
											<option value="Quarterly">${__('Quarterly')}</option>
											<option value="Bi-Annually">${__('Bi-Annually')}</option>
											<option value="Yearly">${__('Yearly')}</option>
										</select>
									</div>
								</div>
								<div class="col-sm-6">
									<div class="form-group">
										<label>${__('Completeness Cycle')}</label>
										<select class="form-control" id="setting-completeness">
											<option value="Monthly">${__('Monthly')}</option>
											<option value="Quarterly">${__('Quarterly')}</option>
											<option value="Bi-Annually">${__('Bi-Annually')}</option>
											<option value="Yearly">${__('Yearly')}</option>
										</select>
									</div>
								</div>
							</div>
							<hr>
							<div class="checkbox">
								<label>
									<input type="checkbox" id="setting-auto-reports" ${settings.enable_scheduled_reports ? 'checked' : ''}>
									<b>${__('Enable Automatic Individual Reports')}</b>
								</label>
							</div>
							<div class="row">
								<div class="col-sm-6">
									<div class="form-group">
										<label>${__('Report Frequency')}</label>
										<select class="form-control" id="setting-report-frequency">
											<option value="">${__('Select...')}</option>
											<option value="Weekly">${__('Weekly')}</option>
											<option value="Monthly">${__('Monthly')}</option>
											<option value="Quarterly">${__('Quarterly')}</option>
											<option value="Bi-Annually">${__('Bi-Annually')}</option>
											<option value="Yearly">${__('Yearly')}</option>
										</select>
									</div>
								</div>
								<div class="col-sm-6">
									<div class="form-group">
										<label>${__('Min Completion % for Final Report')}</label>
										<input type="number" class="form-control" id="setting-min-completion"
											value="${cint(settings.min_completion_pct_for_final_report) || 90}">
									</div>
								</div>
							</div>
							<div class="checkbox">
								<label><input type="checkbox" id="setting-cc-tl" ${settings.cc_team_leader_on_report ? 'checked' : ''}> ${__('Send Digests to Team Leaders / MD')}</label>
								<p class="help-box small text-muted" style="margin:4px 0 0 20px;">${__('Team Leaders get a team-member digest; the MD gets a leadership digest ranking managers by individual and team performance.')}</p>
							</div>
							<div class="checkbox">
								<label><input type="checkbox" id="setting-cc-hr" ${settings.cc_hr_on_report ? 'checked' : ''}> ${__('Send Organisation Digest to HR')}</label>
								<p class="help-box small text-muted" style="margin:4px 0 0 20px;">${__('HR receives all teams ranked plus individual breakdowns for every employee.')}</p>
							</div>

							<hr>
							<div class="form-section-heading" style="margin-bottom:10px;">${__('Preview Reports')}</div>
							<p class="text-muted small">${__('Three digest formats: Team Leader (members), MD (managers), HR (teams + individuals).')}</p>
							<div class="row">
								<div class="col-sm-3">
									<div class="form-group">
										<label>${__('Employee (Individual)')}</label>
										<div class="frappe-control" id="preview-employee-link"></div>
									</div>
									<button class="btn btn-default btn-sm" id="preview-individual-btn">
										<i class="fa fa-eye"></i> ${__('Preview Individual')}
									</button>
								</div>
								<div class="col-sm-3">
									<div class="form-group">
										<label>${__('Team Leader')}</label>
										<div class="frappe-control" id="preview-manager-link"></div>
									</div>
									<button class="btn btn-default btn-sm" id="preview-manager-btn">
										<i class="fa fa-eye"></i> ${__('Preview Team Digest')}
									</button>
								</div>
								<div class="col-sm-3">
									<div class="form-group">
										<label>${__('MD Leadership Digest')}</label>
										<p class="text-muted small" style="min-height:28px;margin:0 0 8px;">${__('Managers ranked by individual + team')}</p>
									</div>
									<button class="btn btn-default btn-sm" id="preview-md-btn">
										<i class="fa fa-eye"></i> ${__('Preview MD Digest')}
									</button>
								</div>
								<div class="col-sm-3">
									<div class="form-group">
										<label>${__('HR Digest')}</label>
										<p class="text-muted small" style="min-height:28px;margin:0 0 8px;">${__('All teams ranked + individuals')}</p>
									</div>
									<button class="btn btn-default btn-sm" id="preview-hr-btn">
										<i class="fa fa-eye"></i> ${__('Preview HR Digest')}
									</button>
								</div>
							</div>
							<div id="report-preview-meta" class="text-muted small" style="margin-top:10px;"></div>
							<div id="report-preview-panel" style="display:none;margin-top:14px;border:1px solid #d1d8dd;background:#f5f5f5;max-height:70vh;overflow:auto;"></div>

							<div id="countdown-panel" class="countdown-panel off" style="margin-top:12px;">
								<div class="countdown-label">${__('Next survey batch in')}</div>
								<div class="countdown-value" id="countdown-value">—</div>
								<div class="countdown-meta" id="countdown-meta"></div>
							</div>
							<div id="cycle-status-box" style="margin-top:12px;"></div>

							<div style="margin-top:16px;">
								<button class="btn btn-primary" id="save-automation-btn">
									<i class="fa fa-save"></i> ${__('Save Automation')}
								</button>
								<button class="btn btn-default" id="run-auto-gen-now-btn">
									<i class="fa fa-bolt"></i> ${__('Run Survey Batch Now')}
								</button>
								<button class="btn btn-default" id="ensure-cycle-btn">
									<i class="fa fa-refresh"></i> ${__('Build / Refresh Cycle')}
								</button>
								<button class="btn btn-default" id="run-reports-now-btn">
									<i class="fa fa-envelope"></i> ${__('Send Reports Now')}
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

		this.tab_automation.find('#setting-gen-mode').val(settings.generation_mode || 'Cycle Matrix');
		this.tab_automation.find('#cycle-strategy-select').val('Balanced Coverage');
		if (settings.generation_frequency) {
			this.tab_automation.find('#setting-frequency').val(settings.generation_frequency);
		}
		this.tab_automation.find('#setting-completeness').val(settings.completeness_cycle || 'Quarterly');
		if (settings.report_frequency) {
			this.tab_automation.find('#setting-report-frequency').val(settings.report_frequency);
		}

		this._init_report_preview_controls();

		this.tab_automation.find('#setting-auto-generate, #setting-frequency').on('change', function() {
			me.refresh_countdown_from_form();
		});

		this.tab_automation.find('#cycle-strategy-select').on('change', function () {
			var is_baseline = $(this).val() === 'Full Baseline Matrix';
			me.tab_automation.find('#cycle-strategy-help').text(is_baseline
				? __('Full Baseline Matrix creates every eligible assignment allowed by the nearness matrix and leadership rules. It is intended for a deliberate first-cycle baseline and can create a much heavier workload.')
				: __('Balanced Coverage spreads a representative set of reviews across the organisation while respecting leadership and departmental-nearness rules.'));
		});

		this.tab_automation.find('#apply-cycle-strategy-btn').on('click', function () {
			me.apply_cycle_strategy();
		});

		this.tab_automation.find('#save-automation-btn').on('click', function() {
			var freq = me.tab_automation.find('#setting-frequency').val() || '';
			var enabled = me.tab_automation.find('#setting-auto-generate').is(':checked') ? 1 : 0;
			var reports_enabled = me.tab_automation.find('#setting-auto-reports').is(':checked') ? 1 : 0;
			var report_freq = me.tab_automation.find('#setting-report-frequency').val() || '';

			if (enabled && !freq) {
				frappe.msgprint(__('Please select a survey frequency when automatic generation is enabled.'));
				return;
			}
			if (reports_enabled && !report_freq) {
				frappe.msgprint(__('Please select a report frequency when automatic reports are enabled.'));
				return;
			}

			var existing = me.data.settings || {};
			var data = Object.assign({}, existing, {
				enable_scheduled_generation: enabled,
				generation_frequency: freq,
				generation_mode: me.tab_automation.find('#setting-gen-mode').val() || 'Cycle Matrix',
				completeness_cycle: me.tab_automation.find('#setting-completeness').val() || 'Quarterly',
				enable_scheduled_reports: reports_enabled,
				report_frequency: report_freq,
				min_completion_pct_for_final_report: cint(me.tab_automation.find('#setting-min-completion').val()) || 90,
				cc_team_leader_on_report: me.tab_automation.find('#setting-cc-tl').is(':checked') ? 1 : 0,
				cc_hr_on_report: me.tab_automation.find('#setting-cc-hr').is(':checked') ? 1 : 0,
				exclude_rated: existing.exclude_rated || [],
				exclude_rating: existing.exclude_rating || []
			});

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
				__('Run the next survey batch now? This bypasses the interval check.'),
				function() {
					frappe.call({
						method: 'survey_app.surveys.auto_generate_if_due',
						args: { force: 1 },
						freeze: true,
						freeze_message: __('Generating surveys...'),
						callback: function(r) {
							if (r.exc) return;
							me.show_auto_gen_status(r.message);
							me.load_cycle_status();
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

		this.tab_automation.find('#ensure-cycle-btn').on('click', function () {
			frappe.call({
				method: 'survey_app.survey_cycle.ensure_cycle',
				args: { force_rebuild: 0 },
				freeze: true,
				callback: function (r) {
					if (r.exc) return;
					frappe.show_alert({ message: __('Cycle ready'), indicator: 'green' });
					me.load_cycle_status();
				}
			});
		});

		this.tab_automation.find('#run-reports-now-btn').on('click', function () {
			frappe.confirm(
				__('Send individual reports, manager team digests, and HR organisation digest now?'),
				function () {
					frappe.call({
						method: 'survey_app.individual_report.auto_send_reports_if_due',
						args: { force: 1 },
						freeze: true,
						freeze_message: __('Sending reports...'),
						callback: function (r) {
							if (r.exc) return;
							me.show_auto_gen_status(r.message);
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
			me.load_cycle_status();
		});

		this.refresh_countdown_from_server();
		this.load_cycle_status();
	}

	_init_report_preview_controls() {
		var me = this;
		if (!this.tab_automation || !this.tab_automation.length) return;

		this.preview_employee_control = frappe.ui.form.make_control({
			parent: this.tab_automation.find('#preview-employee-link'),
			df: {
				fieldtype: 'Link',
				options: 'Employee',
				fieldname: 'preview_employee',
				placeholder: __('Select employee'),
				only_select: 1,
				get_query: function () {
					return { filters: { status: 'Active' } };
				}
			},
			render_input: true
		});
		this.preview_employee_control.refresh();

		this.preview_manager_control = frappe.ui.form.make_control({
			parent: this.tab_automation.find('#preview-manager-link'),
			df: {
				fieldtype: 'Link',
				options: 'Employee',
				fieldname: 'preview_manager',
				placeholder: __('Select team leader / manager'),
				only_select: 1,
				get_query: function () {
					return { filters: { status: 'Active' } };
				}
			},
			render_input: true
		});
		this.preview_manager_control.refresh();

		this.tab_automation.find('#preview-individual-btn').on('click', function () {
			var emp = me.preview_employee_control.get_value();
			frappe.call({
				method: 'survey_app.individual_report.preview_employee_report',
				args: { employee: emp || null },
				freeze: true,
				freeze_message: __('Building individual report preview...'),
				callback: function (r) {
					if (r.exc) return;
					if (!r.message) {
						frappe.msgprint(__('Preview returned no data.'));
						return;
					}
					me._show_report_preview_dialog(r.message, __('Individual Performance Report'));
				}
			});
		});

		this.tab_automation.find('#preview-manager-btn').on('click', function () {
			var mgr = me.preview_manager_control.get_value();
			frappe.call({
				method: 'survey_app.individual_report.preview_manager_report',
				args: { manager: mgr || null },
				freeze: true,
				freeze_message: __('Building team digest preview...'),
				callback: function (r) {
					if (r.exc) return;
					if (!r.message) {
						frappe.msgprint(__('Preview returned no data.'));
						return;
					}
					me._show_report_preview_dialog(r.message, __('Team Performance Digest'));
				}
			});
		});

		this.tab_automation.find('#preview-md-btn').on('click', function () {
			frappe.call({
				method: 'survey_app.individual_report.preview_md_report',
				freeze: true,
				freeze_message: __('Building MD leadership digest...'),
				callback: function (r) {
					if (r.exc) return;
					if (!r.message) {
						frappe.msgprint(__('Preview returned no data.'));
						return;
					}
					me._show_report_preview_dialog(r.message, __('MD Leadership Digest'));
				}
			});
		});

		this.tab_automation.find('#preview-hr-btn').on('click', function () {
			frappe.call({
				method: 'survey_app.individual_report.preview_hr_report',
				freeze: true,
				freeze_message: __('Building HR organisation digest...'),
				callback: function (r) {
					if (r.exc) return;
					if (!r.message) {
						frappe.msgprint(__('Preview returned no data.'));
						return;
					}
					me._show_report_preview_dialog(r.message, __('HR Organisation Digest'));
				}
			});
		});
	}

	_resolve_preview_html(payload) {
		if (!payload) return '';
		// Prefer base64 — desk XSS filters often strip/empty raw HTML string fields.
		if (payload.html_b64) {
			try {
				return decodeURIComponent(escape(atob(payload.html_b64)));
			} catch (e) {
				try {
					return atob(payload.html_b64);
				} catch (e2) {
					/* fall through */
				}
			}
		}
		return payload.report_html || payload.html || '';
	}

	_extract_report_body(html) {
		if (!html) return '';
		var match = String(html).match(/<body[^>]*>([\s\S]*)<\/body>/i);
		return match ? match[1] : html;
	}

	_mount_report_html($host, html) {
		if (!$host || !$host.length) return false;
		var body_html = this._extract_report_body(html);
		if (!body_html) return false;
		var shell = document.createElement('div');
		shell.setAttribute('style', 'background:#F5F5F5;padding:16px;min-height:360px;');
		shell.innerHTML = body_html;
		$host.empty().append(shell);
		return !!(shell.childNodes && shell.childNodes.length);
	}

	_show_report_preview_dialog(payload, title) {
		var me = this;
		var html = this._resolve_preview_html(payload);
		if (!html) {
			frappe.msgprint({
				title: __('Empty Preview'),
				message: __(
					'No report HTML was returned (keys: {0}). Try again after a hard refresh, or confirm Roles & Org / report period data.',
					[Object.keys(payload || {}).join(', ')]
				),
				indicator: 'orange'
			});
			return;
		}

		var meta = [];
		if (payload.employee_name) {
			meta.push(__('Employee') + ': <b>' + frappe.utils.escape_html(payload.employee_name) + '</b>');
		}
		if (payload.manager_name) {
			meta.push(__('Manager') + ': <b>' + frappe.utils.escape_html(payload.manager_name) + '</b>');
		}
		if (payload.report_kind === 'hr' || payload.report_kind === 'manager' || payload.report_kind === 'md') {
			var n = (payload.team && payload.team.length) || payload.people_count || 0;
			if (payload.report_kind === 'md') {
				meta.push(__('Managers ranked') + ': <b>' + (payload.managers_count || n) + '</b>');
			} else if (payload.report_kind === 'hr') {
				meta.push(__('Teams') + ': <b>' + (payload.teams_count || 0) + '</b>');
				meta.push(__('People') + ': <b>' + n + '</b>');
			} else {
				meta.push(__('People in digest') + ': <b>' + n + '</b>');
			}
		}
		if (payload.period_label) {
			meta.push(__('Period') + ': ' + frappe.utils.escape_html(payload.period_label));
		}
		if (payload.overall_pct != null && payload.report_kind === 'individual') {
			meta.push(__('Overall') + ': <b>' + payload.overall_pct + '%</b>');
		}
		if (payload.team_avg != null) {
			meta.push(__('Team avg') + ': <b>' + payload.team_avg + '%</b>');
		}
		var meta_html = meta.join(' · ') || '';
		this.tab_automation.find('#report-preview-meta').html(meta_html);

		var $panel = this.tab_automation.find('#report-preview-panel');
		$panel.show();
		this._mount_report_html($panel, html);

		var d = new frappe.ui.Dialog({
			title: title || __('Report Preview'),
			size: 'large',
			fields: [
				{
					fieldtype: 'HTML',
					fieldname: 'preview_meta',
					options: meta_html
						? '<div class="text-muted small" style="margin-bottom:8px;">' + meta_html + '</div>'
						: ''
				}
			],
			primary_action_label: __('Open in New Window'),
			primary_action: function () {
				var w = window.open('', '_blank');
				if (!w) {
					frappe.msgprint(__('Pop-up blocked. Use the inline preview on the Automation tab instead.'));
					return;
				}
				w.document.open();
				w.document.write(html);
				w.document.close();
			}
		});

		d.show();
		d.$wrapper.find('.modal-dialog').css({ width: '920px', 'max-width': '96vw' });
		var $body = d.$wrapper.find('.modal-body');
		$body.css({
			'max-height': '78vh',
			overflow: 'auto',
			'min-height': '420px'
		});

		// Mount on modal body directly — HTML fields can be cleared by Dialog refresh.
		var $mount = $('<div class="survey-report-preview-mount" style="margin-top:8px;"></div>');
		$body.append($mount);
		var ok = me._mount_report_html($mount, html);
		if (!ok) {
			$mount.html(
				'<div class="alert alert-warning">' +
				__('Dialog preview failed. Scroll the Automation tab for the inline preview, or use Open in New Window.') +
				'</div>'
			);
		}
	}

	apply_cycle_strategy() {
		var me = this;
		var strategy = this.tab_automation.find('#cycle-strategy-select').val() || 'Balanced Coverage';
		frappe.call({
			method: 'survey_app.survey_cycle.preview_cycle_load',
			args: { strategy: strategy },
			freeze: true,
			freeze_message: __('Calculating cycle workload...'),
			callback: function (r) {
				if (r.exc || !r.message) return;
				var preview = r.message;
				var is_baseline = strategy === 'Full Baseline Matrix';
				var message = '<div style="line-height:1.55;">' +
					'<p><b>' + frappe.utils.escape_html(strategy) + '</b></p>' +
					'<p>' + __('This plan will create {0} reviewer–reviewee assignments across approximately {1} batches.', [
						preview.total_pairs || 0,
						preview.batches_in_cycle || 0
					]) + '</p>' +
					'<p>' + __('Reviewer load: average {0}, minimum {1}, maximum {2} assignments for the cycle.', [
						preview.average_reviewer_load || 0,
						preview.minimum_reviewer_load || 0,
						preview.maximum_reviewer_load || 0
					]) + '</p>' +
					(is_baseline
						? '<div class="alert alert-warning" style="margin-bottom:0;">' + __('Use this only when you intentionally want the comprehensive first-cycle baseline. Later cycles should normally use Balanced Coverage.') + '</div>'
						: '<div class="alert alert-info" style="margin-bottom:0;">' + __('Balanced Coverage is the recommended approach for recurring cycles.') + '</div>') +
					'</div>';

				frappe.confirm(message, function () {
					frappe.call({
						method: 'survey_app.survey_cycle.set_cycle_strategy',
						args: { strategy: strategy },
						freeze: true,
						freeze_message: __('Building cycle plan...'),
						callback: function (response) {
							if (response.exc) return;
							frappe.show_alert({
								message: __('Cycle strategy set to {0}', [strategy]),
								indicator: 'green'
							});
							me.load_cycle_status();
						}
					});
				});
			}
		});
	}

	load_cycle_status() {
		var me = this;
		if (!this.tab_automation || !this.tab_automation.length) return;
		frappe.call({
			method: 'survey_app.survey_cycle.get_cycle_status',
			callback: function (r) {
				if (r.exc || !r.message) return;
				var box = me.tab_automation.find('#cycle-status-box');
				var select = me.tab_automation.find('#cycle-strategy-select');
				var apply_button = me.tab_automation.find('#apply-cycle-strategy-btn');
				var lock_message = me.tab_automation.find('#cycle-strategy-lock');
				if (r.message.status === 'ok' && r.message.cycle) {
					var c = r.message.cycle;
					var strategy = c.generation_strategy || 'Balanced Coverage';
					var is_locked = !!c.strategy_locked;
					select.val(strategy).prop('disabled', is_locked).trigger('change');
					apply_button.prop('disabled', is_locked);
					lock_message.html(is_locked
						? '<i class="fa fa-lock"></i> ' + __('Locked after generation started')
						: '<i class="fa fa-unlock"></i> ' + __('Editable before generation starts'));
					box.html(
						'<div class="alert alert-info" style="margin:0;">' +
						'<b>' + __('Open Cycle') + ':</b> ' + frappe.utils.escape_html(c.title || c.name) +
						' · ' + __('Strategy') + ': <b>' + frappe.utils.escape_html(strategy) + '</b>' +
						' · ' + __('Completion') + ': <b>' + (c.completion_pct || 0) + '%</b>' +
						' (' + (c.completed_pairs || 0) + '/' + (c.total_pairs || 0) + ')' +
						' · ' + __('Batch') + ': ' + (c.current_batch || 0) +
						'</div>'
					);
				} else {
					select.val('Balanced Coverage').prop('disabled', false).trigger('change');
					apply_button.prop('disabled', false);
					lock_message.html('<i class="fa fa-info-circle"></i> ' + __('Balanced Coverage is the default'));
					box.html('<p class="text-muted small">' + __('No open cycle yet — click Build / Refresh Cycle.') + '</p>');
				}
			}
		});
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
							<div class="row" style="margin:14px 0 18px;padding:14px 0;border-top:1px solid #e8ebed;border-bottom:1px solid #e8ebed;">
								<div class="col-sm-8">
									<label>${__('Preview survey for employee')}</label>
									<div id="reviewer-preview-reviewee"></div>
									<p class="text-muted small" style="margin:6px 0 0;">${__('Questions are sampled from the current 360° question pool, just as they are during generation.')}</p>
								</div>
								<div class="col-sm-4" style="padding-top:25px;">
									<button class="btn btn-default btn-block" id="preview-reviewer-experience-btn">
										<i class="fa fa-external-link"></i> ${__('Preview Reviewer Experience')}
									</button>
								</div>
							</div>
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

		this.reviewer_preview_reviewee_control = frappe.ui.form.make_control({
			parent: this.tab_generate.find('#reviewer-preview-reviewee'),
			df: {
				fieldtype: 'Link',
				options: 'Employee',
				fieldname: 'reviewer_preview_reviewee',
				placeholder: __('Select an active employee'),
				only_select: 1,
				get_query: function () {
					return { filters: { status: 'Active' } };
				}
			},
			render_input: true
		});
		this.reviewer_preview_reviewee_control.refresh();

		this.tab_generate.find('#preview-reviewer-experience-btn').on('click', function () {
			var reviewee = me.reviewer_preview_reviewee_control.get_value();
			if (!reviewee) {
				frappe.msgprint(__('Select the employee who should appear as the person being reviewed.'));
				return;
			}
			var preview_url = '/survey-preview?reviewee=' + encodeURIComponent(reviewee);
			var preview_window = window.open(preview_url, '_blank');
			if (!preview_window) {
				frappe.msgprint(__('The preview window was blocked. Allow pop-ups for this site and try again.'));
				return;
			}
			preview_window.opener = null;
		});

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

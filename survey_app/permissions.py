"""Shared authorization helpers for the Survey Administration APIs."""

from functools import wraps

import frappe
from frappe import _


SURVEY_ADMIN_ROLES = {"System Manager", "HR Manager"}


def require_survey_admin():
	"""Allow Survey Administration operations only to the configured admin roles."""
	if frappe.session.user == "Administrator":
		return

	if not SURVEY_ADMIN_ROLES.intersection(frappe.get_roles()):
		frappe.throw(
			_("You are not permitted to access Survey Administration."),
			frappe.PermissionError,
		)


def survey_admin_required(method):
	"""Decorator for whitelisted methods that back administration-only screens."""
	@wraps(method)
	def guarded(*args, **kwargs):
		require_survey_admin()
		return method(*args, **kwargs)

	return guarded

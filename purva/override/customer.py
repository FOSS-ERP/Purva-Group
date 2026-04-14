import frappe
from erpnext.selling.doctype.customer.customer import (
	get_credit_limit,
	get_customer_outstanding,
)
from frappe import _
from frappe.utils import flt


def get_customer_group_credit_limit(customers, company, customer_group):
	credit_limits = {
		flt(get_credit_limit(customer, company))
		for customer in customers
		if flt(get_credit_limit(customer, company)) > 0
	}

	if not credit_limits:
		return 0

	if len(credit_limits) > 1:
		frappe.throw(
			_(
				"Multiple credit limits are configured for Customer Group {0}. Please keep one shared limit across the group."
			).format(customer_group),
			title=_("Invalid Credit Limit Setup"),
		)

	return credit_limits.pop()


def check_credit_limit(customer, company, ignore_outstanding_sales_order=False, extra_amount=0):
	parent_company = frappe.db.get_value("Company", company, "parent_company")
	group_company = parent_company or company
	customer_group = frappe.db.get_value("Customer", customer, "customer_group")
	customers = frappe.get_all("Customer", filters={"customer_group": customer_group}, pluck="name")

	credit_limit = get_customer_group_credit_limit(customers, group_company, customer_group)

	if not credit_limit:
		return

	if parent_company:
		companies = frappe.get_all("Company", filters={"parent_company": group_company}, pluck="name")
		companies.append(group_company)
	else:
		companies = [company]

	customer_outstanding = 0

	for cust in customers:
		for comp in companies:
			customer_outstanding += flt(get_customer_outstanding(cust, comp, ignore_outstanding_sales_order))

	# Add current transaction value
	if extra_amount > 0:
		customer_outstanding += flt(extra_amount)

	if credit_limit > 0 and flt(customer_outstanding) > credit_limit:
		message = _("Credit limit has been crossed for Customer Group {0} ({1}/{2})").format(
			customer_group, customer_outstanding, credit_limit
		)

		message += "<br><br>"

		message += _(
			"Please contact your Accounts Team to extend the credit limit for Customer Group {0}."
		).format(customer_group)

		frappe.throw(message, title=_("Credit Limit Crossed"))

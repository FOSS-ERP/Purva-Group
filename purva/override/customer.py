import frappe
from frappe import _
from frappe.utils import flt, nowdate

OVERRIDE_ROLES = ("Credit Controller",)
BLOCK_ON_EQUAL = False


def check_credit_limit(customer, company, ignore_outstanding_sales_order=False, extra_amount=0):
    if not customer or not company:
        return

    customer_group = frappe.db.get_value("Customer", customer, "customer_group")
    if not customer_group:
        return

    parent_company = frappe.db.get_value("Company", company, "parent_company")
    group_company = parent_company or company

    credit_data = frappe.db.get_value(
        "Customer Credit Limit",
        {"parent": customer_group, "parenttype": "Customer Group", "company": group_company},
        ["credit_limit", "bypass_credit_limit_check"],
        as_dict=True,
    )

    if not credit_data:
        return

    if credit_data.bypass_credit_limit_check:
        return

    credit_limit = flt(credit_data.credit_limit)
    if credit_limit <= 0:
        return

    customers = frappe.get_all(
        "Customer",
        filters={"customer_group": customer_group, "disabled": 0},
        pluck="name",
    )
    if not customers:
        return

    if parent_company:
        companies = frappe.get_all(
            "Company", filters={"parent_company": group_company}, pluck="name"
        )
        companies.append(group_company)
    else:
        companies = [company]

    can_override = any(role in frappe.get_roles() for role in OVERRIDE_ROLES)
    outstanding = _group_outstanding(customers, companies, ignore_outstanding_sales_order)
    new_total = outstanding + flt(extra_amount)

    crossed = new_total >= credit_limit if BLOCK_ON_EQUAL else new_total > credit_limit
    if crossed:
        message = _("Credit limit has been crossed for Customer Group {0} ({1}/{2})").format(
            customer_group, _money(new_total), _money(credit_limit)
        )
        message += "<br><br>"
        message += _(
            "Please contact your Accounts Team to extend the credit limit for Customer Group {0}."
        ).format(customer_group)
        _block(message, can_override)


@frappe.whitelist()
def get_group_credit_status(customer, company):
    result = {
        "has_limit": False,
        "customer_group": None,
        "currency": None,
        "limit": 0.0,
        "used": 0.0,
        "available": 0.0,
    }
    if not customer or not company:
        return result

    customer_group = frappe.db.get_value("Customer", customer, "customer_group")
    if not customer_group:
        return result

    parent_company = frappe.db.get_value("Company", company, "parent_company")
    group_company = parent_company or company

    result["customer_group"] = customer_group
    result["currency"] = frappe.get_cached_value("Company", group_company, "default_currency")

    credit_limit = flt(
        frappe.db.get_value(
            "Customer Credit Limit",
            {"parent": customer_group, "parenttype": "Customer Group", "company": group_company},
            "credit_limit",
        )
    )
    if credit_limit <= 0:
        return result

    customers = frappe.get_all(
        "Customer",
        filters={"customer_group": customer_group, "disabled": 0},
        pluck="name",
    )
    if parent_company:
        companies = frappe.get_all(
            "Company", filters={"parent_company": group_company}, pluck="name"
        )
        companies.append(group_company)
    else:
        companies = [company]

    used = _group_outstanding(customers, companies)
    result.update({"has_limit": True, "limit": credit_limit, "used": used, "available": credit_limit - used})
    return result


def _group_outstanding(customers, companies, ignore_outstanding_sales_order=False):
    params = {"customers": tuple(customers), "companies": tuple(companies)}

    gle = frappe.db.sql(
        """
        select sum(debit) - sum(credit)
        from `tabGL Entry`
        where party_type = 'Customer'
          and is_cancelled = 0
          and party in %(customers)s
          and company in %(companies)s
        """,
        params,
    )
    outstanding = flt(gle[0][0]) if gle and gle[0][0] else 0.0

    if not ignore_outstanding_sales_order:
        so = frappe.db.sql(
            """
            select sum(base_grand_total * (100 - per_billed) / 100)
            from `tabSales Order`
            where customer in %(customers)s
              and company in %(companies)s
              and docstatus = 1
              and per_billed < 100
              and status != 'Closed'
            """,
            params,
        )
        outstanding += flt(so[0][0]) if so and so[0][0] else 0.0

    return outstanding


def _group_overdue_amount(customers, companies):
    params = {
        "customers": tuple(customers),
        "companies": tuple(companies),
        "today": nowdate(),
    }

    scheduled = frappe.db.sql(
        """
        select sum(ps.outstanding)
        from `tabPayment Schedule` ps
        inner join `tabSales Invoice` si on si.name = ps.parent
        where si.docstatus = 1
          and si.customer in %(customers)s
          and si.company in %(companies)s
          and ps.outstanding > 0
          and ps.due_date < %(today)s
        """,
        params,
    )
    total = flt(scheduled[0][0]) if scheduled and scheduled[0][0] else 0.0

    unscheduled = frappe.db.sql(
        """
        select sum(si.outstanding_amount)
        from `tabSales Invoice` si
        where si.docstatus = 1
          and si.customer in %(customers)s
          and si.company in %(companies)s
          and si.outstanding_amount > 0
          and si.due_date < %(today)s
          and not exists (
            select 1 from `tabPayment Schedule` ps where ps.parent = si.name
          )
        """,
        params,
    )
    total += flt(unscheduled[0][0]) if unscheduled and unscheduled[0][0] else 0.0

    return total


def _block(message, can_override):
    if can_override:
        frappe.msgprint(message, title=_("Credit Warning (override allowed)"), indicator="orange")
    else:
        frappe.throw(message, title=_("Credit Limit Crossed"))


def _money(amount):
    return frappe.format_value(flt(amount), {"fieldtype": "Currency"})
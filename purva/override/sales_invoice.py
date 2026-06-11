import frappe
from erpnext.accounts.doctype.sales_invoice.sales_invoice import SalesInvoice
from purva.override.customer import check_credit_limit


class CustomSalesInvoice(SalesInvoice):
    def check_credit_limit(self):
        validate_against_credit_limit = False
        for d in self.get("items"):
            if not (d.sales_order or d.delivery_note):
                validate_against_credit_limit = True
                break
        if validate_against_credit_limit:
            # Always pass True so bypass_credit_limit_check is NOT applied at Sales Invoice
            check_credit_limit(self.customer, self.company, ignore_outstanding_sales_order=True)
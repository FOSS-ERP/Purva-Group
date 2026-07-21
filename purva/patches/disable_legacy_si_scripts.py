import frappe


def execute():
	# SI-Fix client script and old server scripts replaced by purva.sales_invoice
	frappe.db.sql("UPDATE `tabClient Script` SET enabled=0 WHERE name='SI-Fix'")
	frappe.db.sql(
		"""
		UPDATE `tabServer Script` SET disabled=1
		WHERE name IN ('create_inventory_adjustment_api', 'create_inventory_adjustment_api-2', 'fetch_actual_qty')
		"""
	)

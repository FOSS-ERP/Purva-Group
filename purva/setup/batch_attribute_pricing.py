import frappe
from frappe import _
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

from purva.batch_attribute_pricing import ATTRIBUTE_FIELDS, find_batch_attribute_fields

SALES_ITEM_DOCTYPES = (
	"Quotation Item",
	"Sales Order Item",
	"Delivery Note Item",
	"Sales Invoice Item",
)


def setup_custom_fields():
	"""Create the pricing fields while preserving each Batch field's data type."""
	source_fields = find_batch_attribute_fields()
	if len(source_fields) != len(ATTRIBUTE_FIELDS):
		_create_missing_batch_fields(source_fields)
		source_fields = find_batch_attribute_fields(throw=True)

	custom_fields = {
		"Item Price": _item_price_fields(source_fields),
		"Quotation Item": [_batch_no_field(), *_sales_item_fields(source_fields, "batch_no")],
		"Sales Order Item": [_batch_no_field(), *_sales_item_fields(source_fields, "batch_no")],
		"Delivery Note Item": _sales_item_fields(source_fields, "batch_no"),
		"Sales Invoice Item": _sales_item_fields(source_fields, "batch_no"),
	}
	create_custom_fields(custom_fields, ignore_validate=frappe.flags.in_patch, update=True)


def _create_missing_batch_fields(source_fields):
	defaults = {
		"make": {"label": "Batch Make", "fieldtype": "Data"},
		# Existing sites can contain descriptive values such as "6 MTR" in this column.
		"length": {"label": "Batch Length", "fieldtype": "Data"},
		"grade": {"label": "Batch Grade", "fieldtype": "Data"},
	}
	fields = []
	insert_after = "batch_qty"
	for attribute, fieldname in ATTRIBUTE_FIELDS.items():
		if attribute not in source_fields:
			fields.append(
				{
					"fieldname": fieldname,
					"label": defaults[attribute]["label"],
					"fieldtype": defaults[attribute]["fieldtype"],
					"insert_after": insert_after,
					"reqd": 1,
					"in_list_view": 1,
				}
			)
			insert_after = fieldname

	if fields:
		create_custom_fields({"Batch": fields}, ignore_validate=frappe.flags.in_patch, update=False)


def _batch_no_field():
	return {
		"fieldname": "batch_no",
		"label": "Batch No",
		"fieldtype": "Link",
		"options": "Batch",
		"insert_after": "item_code",
		"in_list_view": 1,
		"print_hide": 1,
	}


def _item_price_fields(source_fields):
	fields = [
		{
			"fieldname": "custom_batch_attribute_pricing_section",
			"label": "Batch Attribute Pricing",
			"fieldtype": "Section Break",
			"insert_after": "batch_no",
		},
	]
	insert_after = "custom_batch_attribute_pricing_section"
	for attribute, target_fieldname in ATTRIBUTE_FIELDS.items():
		source = source_fields[attribute]
		fields.append(
			{
				"fieldname": target_fieldname,
				"label": source.label,
				"fieldtype": source.fieldtype,
				"options": source.options,
				"insert_after": insert_after,
				"reqd": 1,
				"in_list_view": 1,
				"in_standard_filter": 1,
			}
		)
		insert_after = target_fieldname
	return fields


def _sales_item_fields(source_fields, insert_after):
	fields = []
	for attribute, target_fieldname in ATTRIBUTE_FIELDS.items():
		source = source_fields[attribute]
		fields.append(
			{
				"fieldname": target_fieldname,
				"label": source.label,
				"fieldtype": source.fieldtype,
				"options": source.options,
				"insert_after": insert_after,
				"read_only": 1,
				"fetch_from": f"batch_no.{source.fieldname}",
				"fetch_if_empty": 0,
				"in_list_view": 1,
			}
		)
		insert_after = target_fieldname
	return fields

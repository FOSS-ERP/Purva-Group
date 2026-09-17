import frappe
from frappe import _
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

from purva.batch_attribute_pricing import (
	ATTRIBUTE_FIELDS,
	SALES_ITEM_ATTRIBUTE_FIELDS,
	find_batch_attribute_fields,
)

SALES_ITEM_DOCTYPES = (
	"Quotation Item",
	"Sales Order Item",
	"Sales Invoice Item",
)

OBSOLETE_FIELDS = (
	"custom_batch_make",
	"custom_batch_length",
	"custom_batch_grade",
)

CUSTOMIZED_DOCTYPES = ("Batch", "Item Price", *SALES_ITEM_DOCTYPES)

DELIVERY_NOTE_FIELDS = (
	"custom_batch_name",
	"custom_batch_length_in_mm",
	"custom_sub_grade",
)


def setup_custom_fields():
	"""Create the pricing fields while preserving each Batch field's data type."""
	_remove_obsolete_custom_fields()
	_remove_delivery_note_custom_fields()
	_remove_duplicate_sales_grade_field()
	source_fields = find_batch_attribute_fields(throw=True)

	custom_fields = {
		"Item Price": _item_price_fields(source_fields),
		"Quotation Item": [_batch_no_field(), *_sales_item_fields(source_fields, "batch_no")],
		"Sales Order Item": [_batch_no_field(), *_sales_item_fields(source_fields, "batch_no")],
		"Sales Invoice Item": _sales_item_fields(source_fields, "batch_no"),
	}
	create_custom_fields(custom_fields, ignore_validate=frappe.flags.in_patch, update=True)


def _remove_obsolete_custom_fields():
	for doctype in CUSTOMIZED_DOCTYPES:
		for fieldname in OBSOLETE_FIELDS:
			custom_field = frappe.db.get_value(
				"Custom Field", {"dt": doctype, "fieldname": fieldname}, "name"
			)
			if custom_field:
				frappe.delete_doc("Custom Field", custom_field, ignore_permissions=True, force=True)


def _remove_delivery_note_custom_fields():
	for fieldname in DELIVERY_NOTE_FIELDS:
		_delete_custom_field("Delivery Note Item", fieldname)


def _remove_duplicate_sales_grade_field():
	for doctype in SALES_ITEM_DOCTYPES:
		_delete_custom_field(doctype, "custom_sub_grade")


def _delete_custom_field(doctype, fieldname):
	custom_field = frappe.db.get_value("Custom Field", {"dt": doctype, "fieldname": fieldname}, "name")
	if custom_field:
		frappe.delete_doc("Custom Field", custom_field, ignore_permissions=True, force=True)


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
	for attribute in ATTRIBUTE_FIELDS:
		source = source_fields[attribute]
		target_fieldname = SALES_ITEM_ATTRIBUTE_FIELDS[attribute]
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

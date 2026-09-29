import re
from functools import reduce

import frappe
from frappe import _
from frappe.query_builder import Case
from frappe.query_builder.functions import IfNull
from frappe.utils import flt, parse_json

ATTRIBUTE_FIELDS = {
	"make": "custom_batch_name",
	"length": "custom_batch_length_in_mm",
	"grade": "custom_sub_grade",
}

SALES_ITEM_ATTRIBUTE_FIELDS = {
	"make": "custom_batch_name",
	"length": "custom_batch_length_in_mm",
	"grade": "custom_batch_sub_grade",
}

SOURCE_FIELD_CANDIDATES = {
	"make": ("custom_batch_name",),
	"length": ("custom_batch_length_in_mm",),
	"grade": ("custom_sub_grade",),
}

SOURCE_LABELS = {
	"make": {"batch name"},
	"length": {"batch length in mm"},
	"grade": {"sub grade"},
}

MANUAL_ATTRIBUTE_DOCTYPES = {"Quotation", "Sales Order"}

# Only the make is required. A blank length / sub grade on an Item Price means "any value".
REQUIRED_ATTRIBUTES = ("make",)


def find_batch_attribute_fields(throw=False):
	meta = frappe.get_meta("Batch")
	fields = {}
	for attribute, candidates in SOURCE_FIELD_CANDIDATES.items():
		field = next(
			(meta.get_field(fieldname) for fieldname in candidates if meta.get_field(fieldname)), None
		)
		if not field:
			field = next(
				(df for df in meta.fields if _normalise_label(df.label) in SOURCE_LABELS[attribute]),
				None,
			)
		if field:
			fields[attribute] = field

	missing = [attribute.title() for attribute in ATTRIBUTE_FIELDS if attribute not in fields]
	if missing and throw:
		frappe.throw(
			_("Batch is missing the fields required for attribute pricing: {0}").format(", ".join(missing))
		)
	return fields


def _normalise_label(label):
	return re.sub(r"\s+", " ", (label or "").replace("_", " ").strip().lower())


def get_batch_attributes(batch_no, throw=False):
	source_fields = find_batch_attribute_fields(throw=throw)
	if len(source_fields) != len(ATTRIBUTE_FIELDS):
		return None

	values = frappe.db.get_value(
		"Batch",
		batch_no,
		[field.fieldname for field in source_fields.values()],
		as_dict=True,
	)
	if not values:
		if throw:
			frappe.throw(_("Batch {0} does not exist").format(frappe.bold(batch_no)))
		return None

	attributes = {
		ATTRIBUTE_FIELDS[attribute]: values.get(source_fields[attribute].fieldname)
		for attribute in ATTRIBUTE_FIELDS
	}
	missing = [
		ATTRIBUTE_FIELDS[key]
		for key in REQUIRED_ATTRIBUTES
		if attributes[ATTRIBUTE_FIELDS[key]] in (None, "")
	]
	if missing and throw:
		labels = [
			frappe.get_meta("Batch").get_label(source_fields[key].fieldname)
			for key in ATTRIBUTE_FIELDS
			if ATTRIBUTE_FIELDS[key] in missing
		]
		frappe.throw(
			_("Batch {0} is missing pricing attributes: {1}").format(frappe.bold(batch_no), ", ".join(labels))
		)
	return None if missing else attributes


def sync_batch_attributes(doc, method=None):
	"""Resolve pricing attributes from a batch or manual sales-row selections."""
	for row in doc.get("items") or []:
		if not row.get("batch_no"):
			attributes = _get_manual_row_attributes(row, throw=doc.doctype in MANUAL_ATTRIBUTE_DOCTYPES)
			if not attributes:
				continue
		else:
			attributes = get_batch_attributes(row.batch_no, throw=True)
			batch_item = frappe.db.get_value("Batch", row.batch_no, "item")
			if row.item_code and batch_item != row.item_code:
				frappe.throw(
					_("Row {0}: Batch {1} belongs to Item {2}, not {3}").format(
						row.idx,
						frappe.bold(row.batch_no),
						frappe.bold(batch_item),
						frappe.bold(row.item_code),
					)
				)
			for attribute, item_price_fieldname in ATTRIBUTE_FIELDS.items():
				row.set(SALES_ITEM_ATTRIBUTE_FIELDS[attribute], attributes[item_price_fieldname])

		if _is_copied_from_previous_document(doc, row):
			# Keep the rate agreed on the source document (Quotation / Sales Order / Delivery Note).
			continue

		_set_and_validate_item_price(doc, row, attributes)


def _is_copied_from_previous_document(doc, row):
	if doc.doctype == "Sales Invoice":
		return bool(row.get("so_detail") or row.get("dn_detail"))
	if doc.doctype == "Sales Order":
		return bool(row.get("prevdoc_docname"))
	return False


def _get_manual_row_attributes(row, throw=False):
	attributes = {
		item_price_fieldname: row.get(SALES_ITEM_ATTRIBUTE_FIELDS[attribute])
		for attribute, item_price_fieldname in ATTRIBUTE_FIELDS.items()
	}
	missing = [
		ATTRIBUTE_FIELDS[key]
		for key in REQUIRED_ATTRIBUTES
		if attributes[ATTRIBUTE_FIELDS[key]] in (None, "")
	]
	if missing and throw:
		labels = [frappe.get_meta("Item Price").get_label(fieldname) for fieldname in missing]
		frappe.throw(_("Row {0}: Select {1} to determine the Item Price").format(row.idx, ", ".join(labels)))
	return None if missing else attributes


def _set_and_validate_item_price(doc, row, attributes):
	price_list = doc.get("selling_price_list")
	if not price_list or row.get("is_free_item"):
		return

	pctx = frappe._dict(
		price_list=price_list,
		customer=doc.get("customer") or doc.get("party_name"),
		uom=row.get("uom"),
		transaction_date=(
			doc.get("transaction_date") or doc.get("posting_date") or doc.get("posting_datetime")
		),
		batch_no=row.get("batch_no"),
	)
	item_price = _find_item_price(pctx, row.item_code, attributes)
	if not item_price:
		_throw_missing_item_price(row, price_list, attributes)

	price_list_rate = flt(item_price.price_list_rate)
	row.price_list_rate = price_list_rate
	if not any(
		flt(row.get(fieldname))
		for fieldname in ("discount_percentage", "discount_amount", "margin_rate_or_amount")
	) and not row.get("pricing_rules"):
		row.rate = price_list_rate


@frappe.whitelist()
def get_batch_attribute_item_price(pctx, item_code):
	"""Return the Item Price matching the batch name, length in mm, and sub grade."""
	pctx = frappe._dict(parse_json(pctx))
	if not pctx.get("batch_no"):
		return 0.0

	attributes = get_batch_attributes(pctx.batch_no, throw=True)
	item_price = _find_item_price(pctx, item_code, attributes)
	if not item_price:
		_throw_missing_item_price(frappe._dict(item_code=item_code), pctx.price_list, attributes)

	is_free_item = (pctx.get("items") or [{}])[0].get("is_free_item")
	if item_price and item_price.uom == pctx.get("uom") and not is_free_item:
		return flt(item_price.price_list_rate)
	return 0.0


@frappe.whitelist()
def get_manual_attribute_item_price(
	item_code,
	price_list,
	uom,
	transaction_date=None,
	customer=None,
	batch_name=None,
	batch_length_in_mm=None,
	sub_grade=None,
):
	attributes = {
		ATTRIBUTE_FIELDS["make"]: batch_name,
		ATTRIBUTE_FIELDS["length"]: batch_length_in_mm,
		ATTRIBUTE_FIELDS["grade"]: sub_grade,
	}
	if attributes[ATTRIBUTE_FIELDS["make"]] in (None, ""):
		return None

	pctx = frappe._dict(
		price_list=price_list,
		customer=customer,
		uom=uom,
		transaction_date=transaction_date,
	)
	item_price = _find_item_price(pctx, item_code, attributes)
	if not item_price:
		_throw_missing_item_price(frappe._dict(item_code=item_code), price_list, attributes)
	return flt(item_price.price_list_rate)


def _throw_missing_item_price(row, price_list, attributes):
	details = ", ".join(
		f"{frappe.get_meta('Item Price').get_label(fieldname)}: {value or '-'}"
		for fieldname, value in attributes.items()
	)
	frappe.throw(
		_("No Item Price found for Item {0} in Price List {1} with {2}").format(
			frappe.bold(row.item_code), frappe.bold(price_list), details
		)
	)


def _find_item_price(pctx, item_code, attributes):
	"""Best Item Price for the item and attributes.

	A blank attribute on the Item Price matches any value. When several prices match:
	1. customer-specific beats general
	2. newest valid_from wins
	3. most attributes filled wins (e.g. TATA + Sub Grade C beats TATA + blank)
	4. exact UOM beats blank UOM
	"""
	item_price = frappe.qb.DocType("Item Price")
	query = (
		frappe.qb.from_(item_price)
		.select(item_price.name, item_price.price_list_rate, item_price.uom)
		.where(
			(item_price.item_code == item_code)
			& (item_price.price_list == pctx.price_list)
			& (IfNull(item_price.uom, "").isin(["", pctx.uom]))
			& (IfNull(item_price.batch_no, "") == "")
		)
	)

	if pctx.get("customer"):
		query = query.where(
			(item_price.customer == pctx.customer)
			| ((IfNull(item_price.customer, "") == "") & (IfNull(item_price.supplier, "") == ""))
		)
	else:
		query = query.where((IfNull(item_price.customer, "") == "") & (IfNull(item_price.supplier, "") == ""))

	if pctx.get("transaction_date"):
		query = query.where(
			(IfNull(item_price.valid_from, "2000-01-01") <= pctx.transaction_date)
			& (IfNull(item_price.valid_upto, "2500-12-31") >= pctx.transaction_date)
		)

	for fieldname, value in attributes.items():
		blank_on_price = IfNull(item_price[fieldname], "") == ""
		if value in (None, ""):
			query = query.where(blank_on_price)
		else:
			query = query.where((item_price[fieldname] == value) | blank_on_price)

	specificity = reduce(
		lambda a, b: a + b,
		[Case().when(IfNull(item_price[fieldname], "") != "", 1).else_(0) for fieldname in attributes],
	)

	query = (
		query.orderby(IfNull(item_price.customer, ""), order=frappe.qb.desc)
		.orderby(item_price.valid_from, order=frappe.qb.desc)
		.orderby(specificity, order=frappe.qb.desc)
		.orderby(item_price.uom, order=frappe.qb.desc)
	)

	rows = query.limit(1).run(as_dict=True)
	return rows[0] if rows else None

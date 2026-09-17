import re

import frappe
from frappe import _
from frappe.query_builder.functions import IfNull
from frappe.utils import flt, parse_json

ATTRIBUTE_FIELDS = {
	"make": "custom_batch_name",
	"length": "custom_batch_length_in_mm",
	"grade": "custom_sub_grade",
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
	missing = [fieldname for fieldname, value in attributes.items() if value in (None, "")]
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
	"""Keep copied attributes authoritative to the selected physical batch."""
	for row in doc.get("items") or []:
		if not row.get("batch_no"):
			for fieldname in ATTRIBUTE_FIELDS.values():
				row.set(fieldname, None)
			continue

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
		for fieldname, value in attributes.items():
			row.set(fieldname, value)

		_set_and_validate_item_price(doc, row, attributes)


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


def _throw_missing_item_price(row, price_list, attributes):
	details = ", ".join(
		f"{frappe.get_meta('Item Price').get_label(fieldname)}: {value}"
		for fieldname, value in attributes.items()
	)
	frappe.throw(
		_("No Item Price found for Item {0} in Price List {1} with {2}").format(
			frappe.bold(row.item_code), frappe.bold(price_list), details
		)
	)


def _find_item_price(pctx, item_code, attributes):
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
		.orderby(item_price.valid_from, order=frappe.qb.desc)
		.orderby(item_price.uom, order=frappe.qb.desc)
	)

	if pctx.get("customer"):
		query = query.where(
			(item_price.customer == pctx.customer)
			| ((IfNull(item_price.customer, "") == "") & (IfNull(item_price.supplier, "") == ""))
		).orderby(IfNull(item_price.customer, ""), order=frappe.qb.desc)
	else:
		query = query.where((IfNull(item_price.customer, "") == "") & (IfNull(item_price.supplier, "") == ""))

	if pctx.get("transaction_date"):
		query = query.where(
			(IfNull(item_price.valid_from, "2000-01-01") <= pctx.transaction_date)
			& (IfNull(item_price.valid_upto, "2500-12-31") >= pctx.transaction_date)
		)

	for fieldname, value in attributes.items():
		query = query.where(item_price[fieldname] == value)

	rows = query.limit(1).run(as_dict=True)
	return rows[0] if rows else None

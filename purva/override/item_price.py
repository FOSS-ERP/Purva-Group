import frappe
from erpnext.stock.doctype.item_price.item_price import ItemPrice, ItemPriceDuplicateItem
from frappe import _
from frappe.query_builder import Criterion
from frappe.query_builder.functions import Cast_

from purva.batch_attribute_pricing import ATTRIBUTE_FIELDS


class CustomItemPrice(ItemPrice):
	def validate(self):
		if self.batch_no:
			frappe.throw(
				_("Set Batch Name, Batch Length in mm, and Sub Grade instead of one physical Batch."),
			)
		super().validate()

	def check_duplicates(self):
		item_price = frappe.qb.DocType("Item Price")
		query = (
			frappe.qb.from_(item_price)
			.select(item_price.price_list_rate)
			.where(
				(item_price.item_code == self.item_code)
				& (item_price.price_list == self.price_list)
				& (item_price.name != self.name)
			)
		)

		data_fields = (
			"uom",
			"valid_from",
			"valid_upto",
			"customer",
			"supplier",
			*ATTRIBUTE_FIELDS.values(),
		)
		for fieldname in data_fields:
			if self.get(fieldname):
				query = query.where(item_price[fieldname] == self.get(fieldname))
			else:
				query = query.where(
					Criterion.any(
						[item_price[fieldname].isnull(), Cast_(item_price[fieldname], "varchar") == ""]
					)
				)

		if self.packing_unit:
			query = query.where(item_price.packing_unit == self.packing_unit)
		else:
			query = query.where(
				Criterion.any([item_price.packing_unit.isnull(), item_price.packing_unit == 0])
			)

		if query.run(as_dict=True):
			frappe.throw(
				_(
					"Item Price already exists for this Price List, party, UOM, date range, "
					"Batch Name, Batch Length in mm, and Sub Grade."
				),
				ItemPriceDuplicateItem,
			)

from erpnext.stock.doctype.stock_entry.stock_entry import StockEntry
from erpnext.stock.utils import get_incoming_rate
from frappe.utils import flt


class CustomStockEntry(StockEntry):

    def is_material_transfer_type(self):
        return self.stock_entry_type == "Material Transfer"

    def set_rate_for_outgoing_items(
        self, reset_outgoing_rate=True, raise_error_if_no_rate=True
    ):
        # 🔒 STRICT: Do not touch other Stock Entry types
        if not self.is_material_transfer_type():
            return super().set_rate_for_outgoing_items(
                reset_outgoing_rate, raise_error_if_no_rate
            )

        outgoing_items_cost = 0.0

        for d in self.get("items"):
            if d.s_warehouse:
                # ✅ Apply custom rate only for Material Transfer
                if d.get("custom_updated_rate"):
                    d.basic_rate = d.custom_updated_rate
                elif reset_outgoing_rate:
                    args = self.get_args_for_incoming_rate(d)
                    rate = get_incoming_rate(args, raise_error_if_no_rate)
                    if rate >= 0:
                        d.basic_rate = rate

                # ✅ Always set amount
                d.basic_amount = flt(
                    flt(d.transfer_qty) * flt(d.basic_rate),
                    d.precision("basic_amount"),
                )

                if not d.t_warehouse:
                    outgoing_items_cost += flt(d.basic_amount)

        return outgoing_items_cost

    def update_valuation_rate(self):
        # 🔒 Let core logic run first
        super().update_valuation_rate()

        # 🔒 Do not interfere with other types (like Repack)
        if not self.is_material_transfer_type():
            return

        for d in self.get("items"):
            if d.get("custom_updated_rate"):
                d.additional_cost = 0.0
                d.amount = flt(d.basic_amount, d.precision("amount"))
                d.valuation_rate = d.basic_rate
import frappe
from erpnext.stock.serial_batch_bundle import BatchNoValuation
from erpnext.stock.utils import get_valuation_method


# nosemgrep: frappe-semgrep-rules.rules.frappe-monkey-patching-not-allowed
# BatchNoValuation is a plain utility class (not a DocType controller), so
# ERPNext offers no override_doctype_class / doc_events / extend_doctype_class
# hook for it. Monkey-patching prepare_batches is the only way to change
# FIFO batch valuation behavior without forking ERPNext core.
def _patched_prepare_batches(self):
	self.batches = self.batch_nos
	if isinstance(self.batch_nos, dict):
		self.batches = list(self.batch_nos.keys())

	self.batchwise_valuation_batches = []
	self.non_batchwise_valuation_batches = []

	val_method = get_valuation_method(self.sle.item_code)

	# For FIFO items: treat all batches as non-batchwise so the
	# warehouse-level FIFO queue drives outgoing rate instead of
	# each batch's own moving average.
	if val_method == "FIFO":
		self.non_batchwise_valuation_batches = list(self.batches)
		return

	# Original Moving Average path — preserved unchanged
	if val_method == "Moving Average" and frappe.db.get_single_value(
		"Stock Settings", "do_not_use_batchwise_valuation"
	):
		self.non_batchwise_valuation_batches = self.batches
		return

	batches = frappe.get_all(
		"Batch",
		filters={"name": ("in", self.batches), "use_batchwise_valuation": 1},
		fields=["name"],
	)
	for batch in batches:
		self.batchwise_valuation_batches.append(batch.name)

	self.non_batchwise_valuation_batches = list(set(self.batches) - set(self.batchwise_valuation_batches))


def apply_patch():
	# nosemgrep: frappe-monkey-patching-not-allowed
	# BatchNoValuation is a plain utility class (not a DocType controller), so
	# ERPNext offers no override_doctype_class / doc_events / extend_doctype_class
	# hook for it. Monkey-patching prepare_batches is the only way to change
	# FIFO batch valuation behavior without forking ERPNext core.
	BatchNoValuation.prepare_batches = _patched_prepare_batches

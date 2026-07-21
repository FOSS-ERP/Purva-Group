import frappe


@frappe.whitelist()
def fetch_actual_qty(
	warehouse: str,
	item_code: str | None = None,
	batch_no: str | None = None,
	serial_and_batch_bundle: str | None = None,
) -> float:
	# @frappe.whitelist()
	# def fetch_actual_qty(
	# warehouse: str, item_code: str = None, batch_no: str = None, serial_and_batch_bundle: str = None
	# ) -> float:
	"""Return available qty for a batch/bundle scoped to the given warehouse only."""
	total = 0.0

	if batch_no and item_code:
		total = _get_batch_qty_in_warehouse(item_code, warehouse, batch_no)
	elif serial_and_batch_bundle:
		bundle_batches = frappe.get_all(
			"Serial and Batch Entry",
			filters={"parent": serial_and_batch_bundle},
			fields=["batch_no", "item_code"],
		)
		for b in bundle_batches:
			if not b.batch_no:
				continue
			ic = b.item_code or item_code
			if ic:
				total += _get_batch_qty_in_warehouse(ic, warehouse, b.batch_no)

	return total


def _get_batch_qty_in_warehouse(item_code: str, warehouse: str, batch_no: str) -> float:
	"""Return actual available qty for a batch in a specific warehouse via SLE.

	ERPNext stores batch_no directly on the SLE only when use_serial_batch_fields=1.
	When a Serial and Batch Bundle is used, the SLE has batch_no=NULL and links via
	serial_and_batch_bundle. We cover both cases with a UNION.
	"""
	result = frappe.db.sql(
		"""
		SELECT SUM(actual_qty) FROM (

			-- direct batch_no on SLE (use_serial_batch_fields = 1)
			SELECT actual_qty
			FROM `tabStock Ledger Entry`
			WHERE item_code = %s
			  AND warehouse = %s
			  AND batch_no = %s
			  AND is_cancelled = 0

			UNION ALL

			-- bundle-based: use sbe.qty (per-batch qty) not sle.actual_qty (total for all batches)
			SELECT sbe.qty AS actual_qty
			FROM `tabStock Ledger Entry` sle
			JOIN `tabSerial and Batch Entry` sbe ON sbe.parent = sle.serial_and_batch_bundle
			WHERE sle.item_code = %s
			  AND sle.warehouse = %s
			  AND sle.is_cancelled = 0
			  AND sbe.batch_no = %s
			  AND (sbe.item_code = %s OR sbe.item_code IS NULL OR sbe.item_code = '')

		) combined
		""",
		(item_code, warehouse, batch_no, item_code, warehouse, batch_no, item_code),
	)
	return result[0][0] or 0

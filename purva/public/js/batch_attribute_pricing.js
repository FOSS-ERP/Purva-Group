function batch_attribute_key(row) {
	return [
		row.item_code,
		row.uom,
		row.custom_batch_name,
		row.custom_batch_length_in_mm,
		row.custom_batch_sub_grade,
	].join("|");
}

async function update_batch_attribute_price(frm, cdt, cdn) {
	const row = locals[cdt][cdn];
	const price_list = frm.doc.selling_price_list;

	// Only the make is required; blank length / sub grade match "any" Item Price.
	if (!row || !row.item_code || !row.uom || !price_list || !row.custom_batch_name) return;

	const request_key = batch_attribute_key(row);
	row.__batch_attribute_price_request = request_key;

	const response = await frappe.call({
		method: "purva.batch_attribute_pricing.get_manual_attribute_item_price",
		args: {
			item_code: row.item_code,
			price_list,
			uom: row.uom,
			transaction_date: frm.doc.transaction_date,
			customer: frm.doc.customer || frm.doc.party_name,
			batch_name: row.custom_batch_name,
			batch_length_in_mm: row.custom_batch_length_in_mm || null,
			sub_grade: row.custom_batch_sub_grade || null,
		},
	});

	const now = locals[cdt] && locals[cdt][cdn];
	if (!now || batch_attribute_key(now) !== request_key || response.message == null) return;

	await frappe.model.set_value(cdt, cdn, "price_list_rate", response.message);
	await frappe.model.set_value(cdt, cdn, "rate", response.message);
}

function update_after_item_details(frm, cdt, cdn) {
	// Let ERPNext finish its own item-details call first, then apply the attribute price.
	frappe.after_ajax(() => update_batch_attribute_price(frm, cdt, cdn));
}

const batch_attribute_events = {
	item_code: update_after_item_details,
	uom: update_after_item_details,
	custom_batch_name: update_batch_attribute_price,
	custom_batch_length_in_mm: update_batch_attribute_price,
	custom_batch_sub_grade: update_batch_attribute_price,
};

frappe.ui.form.on("Quotation Item", batch_attribute_events);
frappe.ui.form.on("Sales Order Item", batch_attribute_events);

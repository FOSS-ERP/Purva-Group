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
	const has_all_attributes =
		row.custom_batch_name && row.custom_batch_length_in_mm && row.custom_batch_sub_grade;

	if (!row.item_code || !row.uom || !price_list || !has_all_attributes) return;

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
			batch_length_in_mm: row.custom_batch_length_in_mm,
			sub_grade: row.custom_batch_sub_grade,
		},
	});

	if (row.__batch_attribute_price_request !== request_key || response.message == null) return;

	await frappe.model.set_value(cdt, cdn, "price_list_rate", response.message);
	await frappe.model.set_value(cdt, cdn, "rate", response.message);
}

const batch_attribute_events = {
	custom_batch_name: update_batch_attribute_price,
	custom_batch_length_in_mm: update_batch_attribute_price,
	custom_batch_sub_grade: update_batch_attribute_price,
};

frappe.ui.form.on("Quotation Item", batch_attribute_events);
frappe.ui.form.on("Sales Order Item", batch_attribute_events);

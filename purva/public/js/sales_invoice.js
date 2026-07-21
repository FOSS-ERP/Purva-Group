// GET WAREHOUSE FROM COST CENTER
function get_warehouse_from_cc(frm) {
	if (!frm.doc.cost_center) return Promise.resolve("");

	return frappe.db
		.get_value("Cost Center", frm.doc.cost_center, "custom_warehouse")
		.then((r) => (r.message ? r.message.custom_warehouse : ""));
}

// APPLY DIMENSIONS (ITEMS + TAXES)
function apply_all(frm) {
	if (!frm.doc.cost_center) return;

	// APPLY TO ITEMS
	(frm.doc.items || []).forEach((row) => {
		if (row.cost_center !== frm.doc.cost_center) {
			frappe.model.set_value(row.doctype, row.name, "cost_center", frm.doc.cost_center);
		}

		if (frm.doc.project && row.project !== frm.doc.project) {
			frappe.model.set_value(row.doctype, row.name, "project", frm.doc.project);
		}
	});

	// APPLY TO TAXES
	(frm.doc.taxes || []).forEach((row) => {
		if (row.cost_center !== frm.doc.cost_center) {
			frappe.model.set_value(row.doctype, row.name, "cost_center", frm.doc.cost_center);
		}

		if (frm.doc.project && row.project !== frm.doc.project) {
			frappe.model.set_value(row.doctype, row.name, "project", frm.doc.project);
		}
	});
}

// APPLY WAREHOUSE TO ITEMS
function apply_warehouse(frm, warehouse, cdt = null, cdn = null) {
	if (cdt && cdn) {
		let row = locals[cdt][cdn];

		if (!row.warehouse) {
			frappe.model.set_value(cdt, cdn, "warehouse", warehouse);
		}
	} else {
		(frm.doc.items || []).forEach((row) => {
			if (!row.warehouse) {
				frappe.model.set_value(row.doctype, row.name, "warehouse", warehouse);
			}
		});
	}
}

// MASTER EXECUTION
function run_full_sync(frm, cdt = null, cdn = null) {
	if (!frm.doc.cost_center) return;

	get_warehouse_from_cc(frm).then((warehouse) => {
		apply_all(frm);
		apply_warehouse(frm, warehouse, cdt, cdn);
	});
}

// TAX GRID OVERRIDE
function override_tax_grid(frm) {
	if (!frm.fields_dict.taxes || !frm.fields_dict.taxes.grid) return;

	let grid = frm.fields_dict.taxes.grid;

	if (grid.__override_done) return;

	let original_refresh = grid.refresh;

	grid.refresh = function () {
		original_refresh.apply(this, arguments);
		apply_all(frm);
	};

	grid.__override_done = true;
}

// MAIN EVENTS
frappe.ui.form.on("Sales Invoice", {
	setup(frm) {
		override_tax_grid(frm);
	},

	cost_center(frm) {
		run_full_sync(frm);
	},

	validate(frm) {
		for (let row of frm.doc.items || []) {
			if (!row.warehouse) {
				frappe.throw(`Row ${row.idx}: Warehouse missing for stock validation`);
				return;
			}
		}
	},
});

// ITEM EVENTS
frappe.ui.form.on("Sales Invoice Item", {
	items_add(frm, cdt, cdn) {
		run_full_sync(frm, cdt, cdn);
	},

	item_code(frm, cdt, cdn) {
		run_full_sync(frm, cdt, cdn);
	},

	qty(frm, cdt, cdn) {
		let row = locals[cdt][cdn];
		row.adjustment_done = 0;
		row.adjusted_qty = 0;
	},

	batch_no(frm, cdt, cdn) {
		let row = locals[cdt][cdn];

		row.adjustment_done = 0;
		row.adjusted_qty = 0;

		if (!row.batch_no) {
			frappe.model.set_value(cdt, cdn, "actual_batch_qty", 0);
			return;
		}

		frappe.call({
			method: "purva.sales_invoice.fetch_actual_qty",
			args: {
				item_code: row.item_code,
				batch_no: row.batch_no,
				warehouse: row.warehouse || frm.doc.set_warehouse || "",
			},
			callback: function (r) {
				if (r.message != null) {
					frappe.model.set_value(cdt, cdn, "actual_batch_qty", r.message);
				}
			},
		});
	},

	serial_and_batch_bundle(frm, cdt, cdn) {
		let row = locals[cdt][cdn];

		row.adjustment_done = 0;
		row.adjusted_qty = 0;

		if (!row.serial_and_batch_bundle) {
			frappe.model.set_value(cdt, cdn, "actual_batch_qty", 0);
			return;
		}

		frappe.call({
			method: "purva.sales_invoice.fetch_actual_qty",
			args: {
				item_code: row.item_code,
				serial_and_batch_bundle: row.serial_and_batch_bundle,
				warehouse: row.warehouse || frm.doc.set_warehouse || "",
			},
			callback: function (r) {
				if (r.message != null) {
					frappe.model.set_value(cdt, cdn, "actual_batch_qty", r.message);
				}
			},
		});
	},
});

frappe.ui.form.on("Sales Invoice", {
	refresh: function (frm) {
		/*
        frm.add_custom_button('Inventory Adjustment', function () {

            frappe.call({
                method: "purva.sales_invoice.create_inventory_adjustment",
                args: {
                    invoice_name: frm.doc.name
                },
                freeze: true,

                callback: function(r) {

                    if (!r.message || !r.message.items) {
                        frappe.msgprint("No data returned from API");
                        return;
                    }

                    let data = r.message;

                    frappe.model.with_doctype("Stock Entry", function () {

                        let se = frappe.model.get_new_doc("Stock Entry");

                        se.company = data.company;
                        se.cost_center = data.cost_center;
                        se.stock_entry_type = "Inventory Adjustment";

                        let has_items = false;

                        (data.items || []).forEach(row => {

                            // row.qty is already the shortage computed server-side
                            let shortage = Number(row.qty || 0);

                            if (shortage > 0 && row.item_code) {

                                has_items = true;

                                let child = frappe.model.add_child(se, "items");

                                child.item_code = row.item_code;
                                child.item_name = row.item_name || "";
                                child.description = row.description || "";
                                child.qty = shortage;
                                child.uom = row.uom || "Nos";
                                child.t_warehouse = row.warehouse || "";
                                child.batch_no = row.batch_no || "";
                                child.serial_and_batch_bundle = "";
                                child.custom_batch_make = row.custom_batch_make || "";
                                child.custom_batch_length = row.custom_batch_length || "";
                            }

                        });

                        if (!has_items) {
                            frappe.msgprint("No stock shortage found (all items are sufficiently available in warehouse)");
                            return;
                        }

                        frappe.model.sync(se);
                        frappe.set_route("Form", "Stock Entry", se.name);

                    });

                }
            });

        });
        frm.add_custom_button('Print Batch TC', function() {
            const url = `/printview?doctype=Sales Invoice&name=${frm.doc.name}&format=${encodeURIComponent("Batch TC Print Format")}&no_letterhead=0`;
            window.open(url, '_blank');
        });
        */
	},
});

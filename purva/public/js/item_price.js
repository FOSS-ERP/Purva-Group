frappe.ui.form.on("Item Price", {
	refresh(frm) {
		frm.toggle_display("batch_no", false);
	},
});

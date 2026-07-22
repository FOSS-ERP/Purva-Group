__version__ = "0.0.1"


def _apply_stock_patches():
	try:
		from purva.override.fifo_batch_patch import apply_patch

		apply_patch()
	except Exception:
		pass  # safe if erpnext is not installed


_apply_stock_patches()

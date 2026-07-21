import os
import subprocess
import tempfile
import frappe

IMAGE_EXTS = ("jpg", "jpeg", "png", "gif", "bmp", "webp", "tiff", "svg")


def _cached_image_url(file_doc):
    """Check if we've already converted this file before, return cached URL if so."""
    cached_name = os.path.splitext(file_doc.file_name)[0] + ".png"
    return frappe.db.get_value(
        "File",
        {
            "file_name": cached_name,
            "attached_to_doctype": file_doc.attached_to_doctype,
            "attached_to_name": file_doc.attached_to_name,
        },
        "file_url",
    )


def _save_png(file_doc, img_bytes):
    from frappe.utils.file_manager import save_file

    new_filename = os.path.splitext(file_doc.file_name)[0] + ".png"
    new_file = save_file(
        fname=new_filename,
        content=img_bytes,
        dt=file_doc.attached_to_doctype,
        dn=file_doc.attached_to_name,
        is_private=file_doc.is_private,
    )
    return new_file.file_url


def _pdf_first_page_to_png(pdf_path):
    import fitz  # PyMuPDF

    pdf = fitz.open(pdf_path)
    page = pdf[0]
    pix = page.get_pixmap(dpi=150)
    img_bytes = pix.tobytes("png")
    pdf.close()
    return img_bytes


def convert_any_to_image(file_doc):
    """Universal converter: any non-image file -> PDF (via LibreOffice) -> PNG (via PyMuPDF)."""
    file_path = file_doc.get_full_path()
    ext = file_doc.file_name.split(".")[-1].lower()

    with tempfile.TemporaryDirectory() as tmpdir:
        if ext == "pdf":
            pdf_path = file_path
        else:
            result = subprocess.run(
                [
                    "libreoffice", "--headless", "--norestore",
                    "--convert-to", "pdf",
                    "--outdir", tmpdir, file_path,
                ],
                check=True,
                timeout=90,
                capture_output=True,
            )
            pdf_name = os.path.splitext(os.path.basename(file_path))[0] + ".pdf"
            pdf_path = os.path.join(tmpdir, pdf_name)

            if not os.path.exists(pdf_path):
                frappe.throw(
                    f"Could not convert {file_doc.file_name} to PDF for printing. "
                    f"LibreOffice output: {result.stderr.decode(errors='ignore')}"
                )

        img_bytes = _pdf_first_page_to_png(pdf_path)

    return _save_png(file_doc, img_bytes)


def get_tc_display_url(file_url):
    """Given any TC file URL, return an image URL suitable for printing.
    Images pass through as-is. Everything else is converted (and cached)."""
    if not file_url:
        return None

    file_doc = frappe.get_doc("File", {"file_url": file_url})
    ext = file_doc.file_name.split(".")[-1].lower()

    if ext in IMAGE_EXTS:
        return file_url

    cached = _cached_image_url(file_doc)
    if cached:
        return cached

    return convert_any_to_image(file_doc)
# yourapp/tools/convert/routes.py
import os, tempfile, shutil
from pathlib import Path
from flask import Blueprint, render_template, request, send_file, abort
from werkzeug.utils import secure_filename
from pdf2docx import Converter

bp = Blueprint("convert", __name__, url_prefix="/convert-pdf")

def is_pdf(name: str) -> bool:
    return Path(name).suffix.lower() == ".pdf"

@bp.get("/")
def convert_get():
    return render_template("convert.html")

@bp.post("/")
def convert_post():
    f = request.files.get("pdf")
    if not f or not f.filename:
        abort(400, "Please upload a PDF file.")
    name = secure_filename(f.filename)
    if not is_pdf(name):
        abort(400, "Only PDF files are accepted.")

    workdir = tempfile.mkdtemp(prefix="convert_")
    try:
        pdf_path = os.path.join(workdir, name)
        f.save(pdf_path)

        docx_name = Path(name).with_suffix(".docx").name
        docx_path = os.path.join(workdir, docx_name)

        cv = Converter(pdf_path)
        cv.convert(docx_path, start=0, end=None)
        cv.close()

        return send_file(
            docx_path,
            as_attachment=True,
            download_name=docx_name,
            mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
    finally:
        shutil.rmtree(workdir, ignore_errors=True)

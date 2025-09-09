# yourapp/tools/merge/routes.py
import os, tempfile, shutil
from pathlib import Path
from flask import Blueprint, render_template, request, send_file, abort
from werkzeug.utils import secure_filename
from pdf2docx import Converter
from docx import Document
from docxcompose.composer import Composer

bp = Blueprint("merge", __name__, url_prefix="/merge")

def is_pdf(name: str) -> bool:
    return Path(name).suffix.lower() == ".pdf"

@bp.get("/")
def merge_get():
    return render_template("merge.html")

@bp.post("/")
def merge_post():
    f1 = request.files.get("pdf1")
    f2 = request.files.get("pdf2")
    if not f1 or not f2:
        abort(400, "Please upload two PDF files.")
    n1, n2 = secure_filename(f1.filename), secure_filename(f2.filename)
    if not is_pdf(n1) or not is_pdf(n2):
        abort(400, "Both files must be PDFs (.pdf).")

    workdir = tempfile.mkdtemp(prefix="merge_")
    try:
        p1, p2 = os.path.join(workdir, n1), os.path.join(workdir, n2)
        f1.save(p1); f2.save(p2)

        d1, d2 = Path(p1).with_suffix(".docx"), Path(p2).with_suffix(".docx")
        cv1 = Converter(p1); cv1.convert(str(d1), start=0, end=None); cv1.close()
        cv2 = Converter(p2); cv2.convert(str(d2), start=0, end=None); cv2.close()

        merged_path = os.path.join(workdir, "merged.docx")
        master = Document(str(d1))
        composer = Composer(master)
        composer.append(Document(str(d2)))
        composer.save(merged_path)

        return send_file(
            merged_path,
            as_attachment=True,
            download_name="merged.docx",
            mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
    finally:
        shutil.rmtree(workdir, ignore_errors=True)

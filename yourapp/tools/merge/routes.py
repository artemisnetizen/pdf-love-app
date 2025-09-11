from flask import Blueprint, render_template, request, send_file, abort
from werkzeug.utils import secure_filename
from pathlib import Path
import os, tempfile, shutil
from pdf2docx import Converter
from docx import Document
from docxcompose.composer import Composer

bp = Blueprint("merge", __name__, url_prefix="/merge-pdf")

def is_pdf(name: str) -> bool:
    return name.lower().endswith(".pdf")

# GET: respond to both /merge and /merge/
@bp.route("", methods=["GET"])
@bp.route("/", methods=["GET"])
def merge_get():
    return render_template("merge.html")

# POST: respond to both /merge and /merge/
@bp.route("", methods=["POST"])
@bp.route("/", methods=["POST"])
def merge_post():
    f1 = request.files.get("pdf1")
    f2 = request.files.get("pdf2")
    if not f1 or not f2:
        abort(400, "Please upload two PDF files.")
    n1 = secure_filename(f1.filename or "")
    n2 = secure_filename(f2.filename or "")
    if not is_pdf(n1) or not is_pdf(n2):
        abort(400, "Both files must be PDFs (.pdf).")

    workdir = tempfile.mkdtemp(prefix="merge_")
    try:
        p1 = os.path.join(workdir, n1); f1.save(p1)
        p2 = os.path.join(workdir, n2); f2.save(p2)

        d1 = Path(p1).with_suffix(".docx")
        d2 = Path(p2).with_suffix(".docx")

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

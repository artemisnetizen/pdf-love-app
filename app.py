import os, tempfile, shutil
from pathlib import Path
from flask import Flask, render_template, request, send_file, abort
from werkzeug.utils import secure_filename
from pdf2docx import Converter
from docx import Document
from docxcompose.composer import Composer

app = Flask(__name__)

def allowed_pdf(filename: str) -> bool:
    return Path(filename).suffix.lower() == ".pdf"

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/merge", methods=["POST"])
def merge():
    f1, f2 = request.files.get("pdf1"), request.files.get("pdf2")
    if not f1 or not f2:
        abort(400, "Please upload two PDF files.")

    n1, n2 = secure_filename(f1.filename), secure_filename(f2.filename)
    if not allowed_pdf(n1) or not allowed_pdf(n2):
        abort(400, "Both files must be PDFs.")

    workdir = tempfile.mkdtemp(prefix="pdfmerge_")
    try:
        p1, p2 = os.path.join(workdir, n1), os.path.join(workdir, n2)
        f1.save(p1); f2.save(p2)

        d1, d2 = os.path.splitext(p1)[0] + ".docx", os.path.splitext(p2)[0] + ".docx"
        cv1 = Converter(p1); cv1.convert(d1); cv1.close()
        cv2 = Converter(p2); cv2.convert(d2); cv2.close()

        merged_path = os.path.join(workdir, "merged.docx")
        master = Document(d1)
        composer = Composer(master)
        composer.append(Document(d2))
        composer.save(merged_path)

        return send_file(merged_path, as_attachment=True, download_name="merged.docx")
    finally:
        shutil.rmtree(workdir, ignore_errors=True)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)

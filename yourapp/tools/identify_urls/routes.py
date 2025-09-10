import os, re, io, shutil, tempfile, traceback
from pathlib import Path
from typing import List, Set

from flask import Blueprint, render_template, request, send_file, abort
from werkzeug.utils import secure_filename

from pypdf import PdfReader
from docx import Document

bp = Blueprint("identify_urls", __name__, url_prefix="/identify-urls")

def is_pdf(name: str) -> bool:
    return name.lower().endswith(".pdf")

# A pragmatic URL regex; we also trim trailing punctuation after matching.
URL_PATTERN = re.compile(
    r"""(?ix)
    \b(
      (?:https?://|www\.)               # scheme or www
      [^\s<>()\[\]{}"']+               # body (no spaces or obvious breakers)
      (?:/[^\s<>()\[\]{}"']*)?         # optional path/query
    )
    """
)

TRIM_TRAILING = ".,);:!?'\"”’"  # punctuation we commonly strip from the end

def extract_urls_from_text(text: str) -> List[str]:
    if not text:
        return []
    found = []
    for m in URL_PATTERN.finditer(text):
        u = m.group(1).strip()
        # strip common trailing punctuation
        while u and u[-1] in TRIM_TRAILING:
            u = u[:-1]
        found.append(u)
    return found

@bp.route("", methods=["GET"])
@bp.route("/", methods=["GET"])
def urls_get():
    return render_template("identify_urls.html")

@bp.route("", methods=["POST"])
@bp.route("/", methods=["POST"])
def urls_post():
    try:
        f = request.files.get("file")
        if not f or not f.filename:
            abort(400, "Please upload a PDF file.")
        name = secure_filename(f.filename)
        if not is_pdf(name):
            abort(400, "Only PDF files are accepted.")

        workdir = tempfile.mkdtemp(prefix="urls_")
        try:
            pdf_path = os.path.join(workdir, name)
            f.save(pdf_path)

            # Extract text from each page (no OCR; text layer only)
            reader = PdfReader(pdf_path, strict=False)
            total_pages = len(reader.pages)
            if total_pages < 1:
                abort(400, "The uploaded PDF appears to be empty.")

            urls: Set[str] = set()
            for i in range(total_pages):
                try:
                    page = reader.pages[i]
                    text = page.extract_text() or ""
                    for u in extract_urls_from_text(text):
                        urls.add(u)
                except Exception as ex:
                    # Continue past a bad page; log for server diagnostics
                    print(f"[IDENTIFY_URLS] page {i+1} error: {ex}")

            # Build the DOCX in-memory
            doc = Document()
            stem = Path(name).stem
            doc.add_heading(f'URLs found in "{stem}.pdf"', level=1)
            if urls:
                doc.add_paragraph(f"Total unique URLs: {len(urls)}")
                for u in sorted(urls, key=str.lower):
                    # Plaintext; python-docx hyperlinks require XML fiddling—plaintext is robust & clickable in Word
                    p = doc.add_paragraph(u)
            else:
                doc.add_paragraph("No URLs were found in the text of this PDF.")
                doc.add_paragraph("(Note: scanned PDFs/images need OCR; text-only extraction was used.)")

            out_name = f"{stem}_URLs.docx"
            buffer = io.BytesIO()
            doc.save(buffer)
            buffer.seek(0)

            # Return the DOCX; temp directory (including uploaded PDF) is removed below
            return send_file(
                buffer,
                as_attachment=True,
                download_name=out_name,
                mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        finally:
            shutil.rmtree(workdir, ignore_errors=True)
    except Exception as e:
        print("[/identify-urls ERROR]", repr(e))
        traceback.print_exc()
        abort(500, "An error occurred while identifying URLs. Please try another file.")

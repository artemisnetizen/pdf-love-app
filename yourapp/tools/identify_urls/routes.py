import os, re, io, shutil, tempfile, traceback
from pathlib import Path
from typing import List, Set

from flask import Blueprint, render_template, request, send_file, abort
from werkzeug.utils import secure_filename

from pypdf import PdfReader
from docx import Document

from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.colors import blue, black

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
    import io, shutil, tempfile, traceback
    try:
        f = request.files.get("file")
        if not f or not f.filename:
            abort(400, "Please upload a PDF file.")
        name = secure_filename(f.filename)
        if not is_pdf(name):
            abort(400, "Only PDF files are accepted.")

        workdir = tempfile.mkdtemp(prefix="urls_")
        try:
            # 1) Save upload
            pdf_path = os.path.join(workdir, name)
            f.save(pdf_path)

            # 2) Extract text → collect URLs (no OCR)
            reader = PdfReader(pdf_path, strict=False)
            total_pages = len(reader.pages)
            if total_pages < 1:
                abort(400, "The uploaded PDF appears to be empty.")

            urls = set()
            for i in range(total_pages):
                try:
                    text = (reader.pages[i].extract_text() or "")
                    for u in extract_urls_from_text(text):
                        urls.add(u)
                except Exception as ex:
                    # keep going if a page fails to extract
                    print(f"[IDENTIFY_URLS] page {i+1} extract error: {ex}")

            stem = Path(name).stem
            ofmt = (request.form.get("output_format") or "pdf").lower()

            # 3) Output as PDF (recommended): clickable hyperlinks via ReportLab
            if ofmt == "pdf":
                buf = io.BytesIO()
                doc = SimpleDocTemplate(
                    buf, pagesize=A4,
                    leftMargin=20*mm, rightMargin=20*mm, topMargin=20*mm, bottomMargin=20*mm
                )
                styles = getSampleStyleSheet()
                h1 = styles["Heading1"]
                body = styles["BodyText"]
                link_style = ParagraphStyle("LinkBody", parent=body, textColor=blue)

                story = []
                story.append(Paragraph(f'URLs found in "{stem}.pdf"', h1))
                if urls:
                    story.append(Paragraph(f"Total unique URLs: {len(urls)}", body))
                    story.append(Spacer(1, 6))
                    for u in sorted(urls, key=str.lower):
                        nu = normalize_url(u)
                        story.append(Paragraph(f'<link href="{nu}">{nu}</link>', link_style))
                        story.append(Spacer(1, 2))
                else:
                    story.append(Paragraph("No URLs were found in the text of this PDF.", body))
                    story.append(Paragraph("(Note: scanned PDFs/images need OCR; text-only extraction was used.)", body))

                doc.build(story)
                buf.seek(0)
                return send_file(
                    buf,
                    as_attachment=True,
                    download_name=f"{stem}_URLs.pdf",
                    mimetype="application/pdf",
                )

            # 4) Output as DOCX: clickable hyperlinks with XML + field fallback
            docx_buf = io.BytesIO()
            doc = Document()
            doc.add_heading(f'URLs found in "{stem}.pdf"', level=1)
            if urls:
                doc.add_paragraph(f"Total unique URLs: {len(urls)}")
                doc.add_paragraph(
                    "(Links below are inserted as clickable hyperlinks. "
                    "If your viewer disables them, they will still display as plain URLs.)"
                )
                for u in sorted(urls, key=str.lower):
                    p = doc.add_paragraph()
                    try:
                        add_hyperlink(p, u)              # primary (relationship hyperlink)
                    except Exception as ex:
                        print(f"[IDENTIFY_URLS primary failed] {u}: {ex}")
                        try:
                            add_hyperlink_field(p, u)     # fallback (field code)
                        except Exception as ex2:
                            print(f"[IDENTIFY_URLS fallback failed] {u}: {ex2}")
                            p.add_run(normalize_url(u))   # last resort: plaintext
            else:
                doc.add_paragraph("No URLs were found in the text of this PDF.")
                doc.add_paragraph("(Note: scanned PDFs/images need OCR; text-only extraction was used.)")

            out_name = f"{stem}_URLs.docx"
            doc.save(docx_buf)
            docx_buf.seek(0)
            return send_file(
                docx_buf,
                as_attachment=True,
                download_name=out_name,
                mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )

        finally:
            # delete uploaded PDF + temps
            shutil.rmtree(workdir, ignore_errors=True)

    except Exception as e:
        print("[/identify-urls ERROR]", repr(e))
        traceback.print_exc()
        abort(500, "An error occurred while identifying URLs. Please try another file.")

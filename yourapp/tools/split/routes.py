import os, io, tempfile, shutil, zipfile
from pathlib import Path
from typing import List, Tuple
import traceback

from flask import Blueprint, render_template, request, send_file, abort
from werkzeug.utils import secure_filename

from pypdf import PdfReader, PdfWriter
from pdf2docx import Converter

bp = Blueprint("split", __name__, url_prefix="/split")

def is_pdf(name: str) -> bool:
    return name.lower().endswith(".pdf")

def parse_ranges(req) -> List[Tuple[int, int]]:
    """Read multiple ranges from the form: start[] + end[]; return 1-based inclusive tuples."""
    starts = req.form.getlist("start[]")
    ends   = req.form.getlist("end[]")
    ranges = []
    for s, e in zip(starts, ends):
        if not s or not e:
            continue
        try:
            s_i = int(s)
            e_i = int(e)
        except ValueError:
            raise ValueError("Page ranges must be integers.")
        if s_i < 1 or e_i < 1 or e_i < s_i:
            raise ValueError("Each range must have start ≥1 and end ≥ start.")
        ranges.append((s_i, e_i))
    if not ranges:
        raise ValueError("Please add at least one valid page range.")
    # Sort & normalize (optional: merge overlaps if needed)
    ranges.sort(key=lambda t: (t[0], t[1]))
    return ranges

@bp.route("", methods=["GET"])
@bp.route("/", methods=["GET"])
def split_get():
    return render_template("split.html")

@bp.route("", methods=["POST"])
@bp.route("/", methods=["POST"])
def split_post():
    import io, tempfile, zipfile, gc, traceback
    try:
        f = request.files.get("file")
        ofmt = (request.form.get("output_format") or "").lower()
        if not f or not f.filename:
            abort(400, "Please upload a PDF file.")
        name = secure_filename(f.filename)
        if not is_pdf(name):
            abort(400, "Only PDF files are accepted.")
        if ofmt not in {"pdf", "docx"}:
            abort(400, "Please choose an output format: PDF or DOCX.")

        ranges = parse_ranges(request)  # may raise ValueError

        workdir = tempfile.mkdtemp(prefix="split_")
        try:
            # Save original PDF
            pdf_path = os.path.join(workdir, name)
            f.save(pdf_path)

            reader = PdfReader(pdf_path)
            total_pages = len(reader.pages)
            print(f"[SPLIT] total_pages={total_pages}, requested_ranges={ranges}, ofmt={ofmt}")
            if total_pages < 1:
                abort(400, "The uploaded PDF appears to be empty.")

            # Clip & normalize ranges
            clipped = []
            for (s, e) in ranges:
                if s > total_pages:
                    continue
                e = min(e, total_pages)
                if e >= s:
                    clipped.append((s, e))
            if not clipped:
                abort(400, "All ranges fall outside the document's page count.")

            # Auto-append remainder if needed
            last_end = max(e for _, e in clipped)
            if last_end < total_pages:
                clipped.append((last_end + 1, total_pages))
            print(f"[SPLIT] effective_ranges={clipped}")

            # Use a spooled temp file for ZIP to avoid holding big buffers in RAM
            zip_spooled = tempfile.SpooledTemporaryFile(max_size=5 * 1024 * 1024)  # 5MB in RAM, then disk
            with zipfile.ZipFile(zip_spooled, "w", compression=zipfile.ZIP_DEFLATED) as zf:
                for idx, (s, e) in enumerate(clipped, start=1):
                    writer = PdfWriter()
                    for p in range(s - 1, e):
                        writer.add_page(reader.pages[p])

                    slice_name_pdf = f"{Path(name).stem}_part{idx}_{s}-{e}.pdf"
                    slice_pdf_path = os.path.join(workdir, slice_name_pdf)
                    with open(slice_pdf_path, "wb") as outpdf:
                        writer.write(outpdf)
                    # free writer/page refs ASAP
                    del writer
                    gc.collect()

                    if ofmt == "pdf":
                        zf.write(slice_pdf_path, arcname=slice_name_pdf)
                    else:
                        # Convert this slice to DOCX
                        slice_name_docx = f"{Path(name).stem}_part{idx}_{s}-{e}.docx"
                        slice_docx_path = os.path.join(workdir, slice_name_docx)
                        cv = Converter(slice_pdf_path)
                        cv.convert(slice_docx_path, start=0, end=None)
                        cv.close()
                        zf.write(slice_docx_path, arcname=slice_name_docx)
                        # clean converter refs
                        del cv
                        gc.collect()

            # Rewind spooled file for sending
            zip_spooled.seek(0)
            dl_name = "splits_pdfs.zip" if ofmt == "pdf" else "splits_docx.zip"
            return send_file(
                zip_spooled,
                as_attachment=True,
                download_name=dl_name,
                mimetype="application/zip",
                max_age=0
            )
        finally:
            shutil.rmtree(workdir, ignore_errors=True)

    except ValueError as ve:
        print("[/split BAD_RANGE]", str(ve))
        abort(400, str(ve))
    except Exception as e:
        print("[/split ERROR]", repr(e))
        traceback.print_exc()
        abort(500, "An error occurred while splitting. Please try PDF output first or smaller ranges.")

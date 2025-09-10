import io, os, json, shutil, tempfile, traceback
from pathlib import Path
from typing import List, Dict, Any, Tuple

from flask import Blueprint, render_template, request, send_file, abort
from werkzeug.utils import secure_filename

from pypdf import PdfReader, PdfWriter, PageObject
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter  # placeholder; will use real page size
from reportlab.lib.utils import ImageReader
from PIL import Image, ImageDraw, ImageFont

bp = Blueprint("sign", __name__, url_prefix="/sign")

# Put a cursive TTF into your repo, e.g. assets/fonts/Signature.ttf (Great Vibes / Dancing Script)
FONT_PATH = os.environ.get("SIGNATURE_FONT_PATH", os.path.join(os.path.dirname(__file__), "..", "..", "assets", "fonts", "Signature.ttf"))

def is_pdf(name: str) -> bool:
    return name.lower().endswith(".pdf")

def make_signature_png(full_name: str, px_width: int = 800, px_height: int = 220, text_pad: int = 20) -> Image.Image:
    """
    Render a stylized signature PNG with transparent background.
    px_width is the *maximum* canvas width; we scale font to fit width nicely.
    """
    if not full_name.strip():
        full_name = "Signature"
    img = Image.new("RGBA", (px_width, px_height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Load font (fallback to default if missing)
    try:
        # try large size then shrink to fit
        font_size = 180
        font = ImageFont.truetype(FONT_PATH, font_size)
    except Exception:
        font = ImageFont.load_default()
        font_size = 60

    # Fit text within width – decrease until it fits
    max_w = px_width - 2 * text_pad
    while font.getlength(full_name) > max_w and font_size > 20:
        font_size -= 4
        try:
            font = ImageFont.truetype(FONT_PATH, font_size)
        except Exception:
            font = ImageFont.load_default()

    # Center text
    tw = font.getlength(full_name)
    th = font.size
    x = (px_width - tw) / 2
    y = (px_height - th) / 2
    draw.text((x, y), full_name, fill=(20, 20, 20, 255), font=font)

    # Trim transparent padding
    bbox = img.getbbox()
    if bbox:
        img = img.crop(bbox)
    return img

def paste_signature_on_pdf(
    pdf_path: str,
    placements: List[Dict[str, Any]],
    full_name: str,
    sig_width_pt: float,
) -> bytes:
    """
    placements: list of {page_index, x_norm, y_norm}
    x_norm, y_norm are 0..1 in *viewer* top-left origin.
    We convert to PDF coords (bottom-left), scale by page size.
    sig_width_pt: width in PDF points (1/72 inch).
    """
    reader = PdfReader(pdf_path)
    writer = PdfWriter()

    # Prepare a reusable PNG for the signature at high resolution
    # We'll scale it in reportlab to sig_width_pt
    sig_png = make_signature_png(full_name)
    sig_reader = ImageReader(sig_png)

    # Group placements by page
    by_page: Dict[int, List[Tuple[float, float]]] = {}
    for p in placements:
        try:
            idx = int(p["page_index"])
            x_norm = float(p["x_norm"])
            y_norm = float(p["y_norm"])
        except Exception:
            continue
        by_page.setdefault(idx, []).append((x_norm, y_norm))

    for page_index, page in enumerate(reader.pages):
        media = page.mediabox
        page_w = float(media.width)
        page_h = float(media.height)

        # If this page needs signatures, create an overlay PDF and merge
        if page_index in by_page and by_page[page_index]:
            # Compute signature height preserving aspect ratio
            sig_w_px, sig_h_px = sig_png.size
            aspect = sig_h_px / sig_w_px if sig_w_px else 0.3
            sig_h_pt = sig_width_pt * aspect

            # Create overlay PDF in memory with the same page size
            overlay_bytes = io.BytesIO()
            c = canvas.Canvas(overlay_bytes, pagesize=(page_w, page_h))

            for (x_norm, y_norm) in by_page[page_index]:
                # Convert normalized top-left coords to PDF bottom-left coords
                x_pt = x_norm * page_w
                y_top_pt = y_norm * page_h
                y_pt = page_h - y_top_pt - sig_h_pt  # top-left -> bottom-left, then shift by height

                # Draw signature image
                c.drawImage(sig_reader, x_pt, y_pt, width=sig_width_pt, height=sig_h_pt, mask='auto')

            c.save()
            overlay_bytes.seek(0)

            # Merge overlay onto current page
            overlay_pdf = PdfReader(overlay_bytes)
            overlay_page = overlay_pdf.pages[0]
            page.merge_page(overlay_page)

        # Add (possibly modified) page to writer
        writer.add_page(page)

    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()

@bp.route("", methods=["GET"])
@bp.route("/", methods=["GET"])
def sign_get():
    return render_template("sign.html")

@bp.route("", methods=["POST"])
@bp.route("/", methods=["POST"])
def sign_post():
    """
    Expects multipart/form-data:
      - file: the PDF
      - full_name: user's full name (string)
      - placements_json: JSON list of {page_index, x_norm, y_norm}
      - sig_width_pt: optional signature width in points (default 200)
    Returns a signed PDF download.
    """
    try:
        f = request.files.get("file")
        full_name = (request.form.get("full_name") or "").strip()
        placements_json = request.form.get("placements_json") or "[]"
        sig_width_pt = float(request.form.get("sig_width_pt") or "200")

        if not f or not f.filename:
            abort(400, "Please upload a PDF.")
        name = secure_filename(f.filename)
        if not is_pdf(name):
            abort(400, "Only PDF files are accepted.")
        placements = json.loads(placements_json)
        if not isinstance(placements, list) or not placements:
            abort(400, "Please add at least one signature placement.")
        if not full_name:
            abort(400, "Please enter your full name.")

        workdir = tempfile.mkdtemp(prefix="sign_")
        try:
            pdf_path = os.path.join(workdir, name)
            f.save(pdf_path)

            # Sign
            signed_bytes = paste_signature_on_pdf(pdf_path, placements, full_name, sig_width_pt)

            # Return signed PDF
            stem = Path(name).stem
            return send_file(
                io.BytesIO(signed_bytes),
                as_attachment=True,
                download_name=f"{stem}_signed.pdf",
                mimetype="application/pdf",
            )
        finally:
            shutil.rmtree(workdir, ignore_errors=True)

    except Exception as e:
        print("[/sign ERROR]", repr(e))
        traceback.print_exc()
        abort(500, "An error occurred while signing. Please try again.")

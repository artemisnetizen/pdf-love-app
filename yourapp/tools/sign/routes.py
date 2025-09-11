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

from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

bp = Blueprint("sign", __name__, url_prefix="/sign")

DEFAULT_FONT_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "assets", "fonts", "Signature.ttf")
)
FONT_PATH = os.environ.get("SIGNATURE_FONT_PATH", DEFAULT_FONT_PATH)

_SIGNATURE_FONT_NAME = "SignatureFont__custom"

def ensure_signature_font_registered():
    """Register the TTF with ReportLab once; no-op if already registered."""
    try:
        if _SIGNATURE_FONT_NAME not in pdfmetrics.getRegisteredFontNames():
            if not os.path.exists(FONT_PATH):
                raise FileNotFoundError(f"Signature font not found at {FONT_PATH}")
            pdfmetrics.registerFont(TTFont(_SIGNATURE_FONT_NAME, FONT_PATH))
        return _SIGNATURE_FONT_NAME
    except Exception as e:
        # As a last resort, fall back to Helvetica (will look non-cursive)
        print(f"[SIGN] Could not register font ({FONT_PATH}): {e}. Falling back to Helvetica.")
        return "Great_Vibes"

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
    Draw the signature as vector text (no PNG) using the embedded TTF.
    placements: list of {page_index, x_norm, y_norm} with top-left normalized coords (0..1).
    sig_width_pt: target text width in PDF points.
    """
    reader = PdfReader(pdf_path)
    writer = PdfWriter()

    font_name = ensure_signature_font_registered()

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

        if page_index in by_page and by_page[page_index]:
            overlay_bytes = io.BytesIO()
            c = canvas.Canvas(overlay_bytes, pagesize=(page_w, page_h))

            # Compute a font size that fits the requested width
            # Try from a large size down until stringWidth <= sig_width_pt
            candidate_size = 120
            txt = full_name.strip() or "Signature"
            # Guard against zero width string
            string_w = pdfmetrics.stringWidth(txt, font_name, candidate_size) or 1.0
            if string_w < sig_width_pt:
                # scale up proportionally
                candidate_size = max(10, candidate_size * (sig_width_pt / string_w))

            # refine to not exceed
            for _ in range(12):
                w = pdfmetrics.stringWidth(txt, font_name, candidate_size)
                if w <= sig_width_pt or candidate_size <= 10:
                    break
                candidate_size -= max(1, candidate_size * 0.08)

            c.setFont(font_name, candidate_size)
            # Optional: darker gray looks more “ink-like”
            c.setFillGray(0.1)

            # approximate ascent to convert top-left to baseline Y
            ascent_approx = candidate_size * 0.80

            for (x_norm, y_norm) in by_page[page_index]:
                x_pt = x_norm * page_w
                y_top_pt = y_norm * page_h
                # convert to baseline (PDF origin bottom-left)
                y_baseline = page_h - y_top_pt - (candidate_size - (candidate_size - ascent_approx))
                c.drawString(x_pt, y_baseline, txt)

            c.save()
            overlay_bytes.seek(0)

            overlay_pdf = PdfReader(overlay_bytes)
            page.merge_page(overlay_pdf.pages[0])

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

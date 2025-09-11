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
from reportlab.pdfbase.ttfonts import TTFont, TTFError

bp = Blueprint("sign", __name__, url_prefix="/sign")

DEFAULT_FONT_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "assets", "fonts", "Signature.ttf")
)
FONT_PATH = os.environ.get("SIGNATURE_FONT_PATH", DEFAULT_FONT_PATH)

_SIGNATURE_FONT_NAME = "SignatureFont__custom"
_FONT_REGISTERED = False

def _candidate_font_paths():
    import os
    here = os.path.dirname(__file__)                           # /app/yourapp/tools/sign
    yourapp_root = os.path.abspath(os.path.join(here, "..", ".."))  # /app/yourapp
    return [
        os.environ.get("SIGNATURE_FONT_PATH"),                          # env override
        os.path.join(yourapp_root, "assets", "fonts", "Signature.ttf"), # default
        # common alternates (in case filename differs)
        os.path.join(yourapp_root, "assets", "fonts", "GreatVibes-Regular.ttf"),
        os.path.join(yourapp_root, "assets", "fonts", "DancingScript-Regular.ttf"),
        # absolute fallbacks (Render app root)
        "/app/yourapp/assets/fonts/Signature.ttf",
        "/app/yourapp/assets/fonts/GreatVibes-Regular.ttf",
        "/app/yourapp/assets/fonts/DancingScript-Regular.ttf",
        "/app/assets/fonts/Signature.ttf",
        "/app/assets/fonts/GreatVibes-Regular.ttf",
        "/app/assets/fonts/DancingScript-Regular.ttf",
    ]

def ensure_signature_font_registered() -> str:
    """
    Find and register a static TTF for the signature. Returns the font name to use.
    Raises FileNotFoundError if no font file is found, or TTFError if the file is invalid.
    """
    import os, sys
    global _FONT_REGISTERED

    print("[SIGN] ensure_signature_font_registered() called", flush=True)
    print(f"[SIGN] CWD={os.getcwd()}", flush=True)
    print(f"[SIGN] __file__ dir={os.path.dirname(__file__)}", flush=True)
    print(f"[SIGN] Env SIGNATURE_FONT_PATH={os.environ.get('SIGNATURE_FONT_PATH')}", flush=True)

    # Already registered in this process?
    if _FONT_REGISTERED or _SIGNATURE_FONT_NAME in pdfmetrics.getRegisteredFontNames():
        print(f"[SIGN] Font already registered: {_SIGNATURE_FONT_NAME}", flush=True)
        return _SIGNATURE_FONT_NAME

    # Pick the first existing candidate
    candidates = [p for p in _candidate_font_paths() if p]
    chosen = None
    for p in candidates:
        if os.path.exists(p):
            chosen = p
            break

    if not chosen:
        msg = (
            "Signature font file not found. "
            "Set SIGNATURE_FONT_PATH env var or add a static TTF at yourapp/assets/fonts/Signature.ttf"
        )
        print(f"[SIGN] {msg}", flush=True)
        raise FileNotFoundError(msg)

    print(f"[SIGN] Using font path: {chosen}", flush=True)

    # Register the TTF (must be a static TTF, not a VariableFont)
    try:
        pdfmetrics.registerFont(TTFont(_SIGNATURE_FONT_NAME, chosen))
        _FONT_REGISTERED = True
        print(f"[SIGN] Registered TTF: {_SIGNATURE_FONT_NAME}", flush=True)
        return _SIGNATURE_FONT_NAME
    except TTFError as e:
        # Typically happens with variable fonts or corrupt files
        print(f"[SIGN] TTFError registering font ({chosen}): {e}", flush=True)
        raise
    except Exception as e:
        print(f"[SIGN] Unexpected error registering font ({chosen}): {e}", flush=True)
        raise

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

    txt = full_name.strip() or "Signature"
    font_name = ensure_signature_font_registered()
    
    """
    Draw the signature as vector text (no PNG) using the embedded TTF.
    placements: list of {page_index, x_norm, y_norm} with top-left normalized coords (0..1).
    sig_width_pt: target text width in PDF points.
    """
    reader = PdfReader(pdf_path)
    writer = PdfWriter()

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

            # Start with a guess, scale to target width, clamp to [4, 300] pt
            candidate_size = 120.0
            w = pdfmetrics.stringWidth(txt, font_name, candidate_size) or 1.0
            scale = sig_width_pt / w
            candidate_size = max(4.0, min(candidate_size * scale, 300.0))

            # Fine-tune downward so we don't exceed requested width
            for _ in range(20):
                w = pdfmetrics.stringWidth(txt, font_name, candidate_size) or 0.1
                if w <= sig_width_pt or candidate_size <= 4.0:
                    break
                candidate_size = max(4.0, candidate_size * 0.92)
            
            c.setFont(font_name, candidate_size)
            c.setFillGray(0.1)  # ink-like
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

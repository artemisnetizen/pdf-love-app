# yourapp/registry.py
BASE = "https://www.ihatepdf.co"  # change if needed

TOOLS = [
    {
        "name": "Convert PDF → DOCX",
        "path": "/convert-pdf",
        "description": "Upload one PDF and download an editable Word document.",
        "absolute_url": f"{BASE}/convert-pdf",
    },
    {
        "name": "Merge 2 PDFs → 1 DOCX",
        "path": "/merge-pdf",
        "description": "Upload two PDFs; we convert each to DOCX and merge into one.",
        "absolute_url": f"{BASE}/merge-pdf",
    },
    {
    "name": "Split PDF by Ranges",
    "path": "/split-pdf",
    "description": "Select one or more page ranges and download each as PDF or DOCX.",
    "absolute_url": f"{BASE}/split-pdf",
    },
    {
    "name": "Identify URLs in a PDF",
    "path": "/identify-urls",
    "description": "Extract all web links from your PDF and download them as a DOCX list.",
    "absolute_url": f"{BASE}/identify-urls",
    },
    {
    "name": "Sign PDF",
    "path": "/sign-pdf",
    "description": "Place one or more signatures on any pages, then download the signed PDF.",
    "absolute_url": f"{BASE}/sign-pdf",
    },
    # Add more tools here as you grow
]

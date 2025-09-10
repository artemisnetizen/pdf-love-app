# yourapp/registry.py
BASE = "https://www.ihatepdf.co"  # change if needed

TOOLS = [
    {
        "name": "Convert PDF → DOCX",
        "path": "/convert",
        "description": "Upload one PDF and download an editable Word document.",
        "absolute_url": f"{BASE}/convert",
    },
    {
        "name": "Merge 2 PDFs → 1 DOCX",
        "path": "/merge",
        "description": "Upload two PDFs; we convert each to DOCX and merge into one.",
        "absolute_url": f"{BASE}/merge",
    },
    {
    "name": "Split PDF by Ranges",
    "path": "/split",
    "description": "Select one or more page ranges and download each as PDF or DOCX.",
    "absolute_url": f"{BASE}/split",
    },
    {
    "name": "Identify URLs in a PDF",
    "path": "/identify-urls",
    "description": "Extract all web links from your PDF and download them as a DOCX list.",
    "absolute_url": f"{BASE}/identify-urls",
    },
    # Add more tools here as you grow
]

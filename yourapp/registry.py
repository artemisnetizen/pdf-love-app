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
    # Add more tools here as you grow
]

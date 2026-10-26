import io

from pypdf import PdfReader

MAX_CHARS_FOR_SCANNED = 50

def extract_text(pdf_bytes:bytes) -> tuple[str,int]:
    reader = PdfReader(io.BytesIO(pdf_bytes))

    pages = []
    for page in reader.pages:
        pages.append(page.extract_text() or "")

    full_text = "\n".join(pages)
    return full_text,len(reader.pages)

def looks_like_scanned(text:str) -> bool:
    return len(text.strip()) < MAX_CHARS_FOR_SCANNED
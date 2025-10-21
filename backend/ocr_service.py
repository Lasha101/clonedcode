import os
import re
import io
from datetime import datetime
from typing import Dict, Optional, List
import logging

from pdf2image import convert_from_bytes
from google.cloud import vision
from fastapi import HTTPException

# --- Logger Setup ---
# The logger is still created, but by commenting out basicConfig,
# it will no longer print to the terminal by default.
logger = logging.getLogger("ocr_service")
logger.setLevel(logging.INFO)
# logging.basicConfig(level=logging.INFO) # <-- THIS LINE IS COMMENTED OUT

# --- Google Cloud Client Initialization ---
vision_client = None
try:
    # logger.info("--- [GCP] Initializing Google Vision client... ---") # This will no longer print
    if not os.getenv("GOOGLE_APPLICATION_CREDENTIALS"):
        # logger.error("...") # This will no longer print
        raise ValueError("GOOGLE_APPLICATION_CREDENTIALS environment variable must be set.")
    
    vision_client = vision.ImageAnnotatorClient()
    # logger.info("✅ [GCP] Google Vision client initialized successfully.") # This will no longer print
except Exception as e:
    # logger.error(f"🔴 [GCP] FAILED to initialize Google Cloud clients: {e}") # This will no longer print
    # We still raise the exception so the program stops if it fails
    raise e


# --- Parsing Helper Functions ---
def _parse_date_from_mrz(date_str: str) -> Optional[str]:
    if not date_str or len(date_str) != 6 or '<' in date_str: return None
    try:
        year, month, day = int(date_str[0:2]), int(date_str[2:4]), int(date_str[4:6])
        current_year_short = datetime.now().year % 100
        year += 1900 if year > current_year_short + 10 else 2000
        return datetime(year, month, day).strftime('%Y-%m-%d')
    except (ValueError, TypeError): return None

def _parse_date(date_str: Optional[str]) -> Optional[str]:
    if not date_str: return None
    try:
        cleaned_date_str = re.sub(r'[\s.]', '/', date_str).strip()
        match = re.search(r'(\d{2}/\d{2}/\d{4})', cleaned_date_str)
        if match: return datetime.strptime(match.group(1), '%d/%m/%Y').strftime('%Y-%m-%d')
        return None
    except ValueError: return None


def _extract_value_from_line(line: str, keywords: List[str]) -> Optional[str]:
    keyword_pattern = '|'.join(keywords)
    match = re.search(fr'(?:{keyword_pattern})\s*[:/]?\s*(.*)', line, re.IGNORECASE)
    if not match:
        return None
    value = match.group(1).strip()
    value = re.sub(r'prénom|given name|nom|surname', '', value, flags=re.IGNORECASE)
    value = re.sub(r'[/:]', '', value).strip()
    if len(value) > 1 and any(c.isalpha() for c in value):
        return value
    return None

def _parse_passport_text(raw_text: str) -> Dict[str, Optional[str]]:
    data = {
        "first_name": None, "last_name": None, "passport_number": None,
        "birth_date": None, "delivery_date": None, "expiration_date": None,
        "nationality": "FRANCAISE",
    }
    text_lines = [line.strip() for line in raw_text.split('\n')]
    mrz_line1_index = next((i for i, line in enumerate(text_lines) if line.replace(' ', '').replace('«', '<').startswith('P<')), -1)
    if mrz_line1_index != -1 and mrz_line1_index + 1 < len(text_lines):
        line1 = text_lines[mrz_line1_index].replace(' ', '').replace('«', '<').ljust(44, '<')
        line2_raw = text_lines[mrz_line1_index + 1].replace(' ', '').replace('«', '<')
        line2 = re.sub(r'[^A-Z0-9<]', '', line2_raw).ljust(44, '<')
        data["passport_number"] = line2[0:9].replace('<', '').strip() or None
        data["nationality"] = line2[10:13].strip() or "FRANCAISE"
        data["birth_date"] = _parse_date_from_mrz(line2[13:19])
        data["expiration_date"] = _parse_date_from_mrz(line2[21:27])
        name_part = line1[5:44]
        parts = name_part.split('<<')
        if len(parts) >= 1: data["last_name"] = parts[0].replace('<', ' ').strip() or None
        if len(parts) >= 2: data["first_name"] = parts[1].replace('<', ' ').strip() or None
    if not data["passport_number"]:
        match = re.search(r'(?:Passeport\s*N°|Passport\s*No\.?)\s*([A-Z0-9]{9})\b', raw_text, re.IGNORECASE)
        if match: data["passport_number"] = match.group(1).strip()
        else:
            match = re.search(r'\b([A-Z]{2}\d{7}|\d{2}[A-Z]{2}\d{5})\b', raw_text.replace(" ", ""))
            if match: data["passport_number"] = match.group(1).strip()
    date_patterns = {
        'birth_date': r'(?:(?:Date\sde\s)?naissance|birth)[\s\S]{0,50}?(\d{2}[./\s]\d{2}[./\s]\d{4})',
        'delivery_date': r'(?:(?:Date\sde\s)?délivrance|delivrance|issue)[\s\S]{0,50}?(\d{2}[./\s]\d{2}[./\s]\d{4})',
        'expiration_date': r'(?:(?:Date\sd\'?)?expiration|expiry|expire\s*le)[\s\S]{0,50}?(\d{2}[./\s]\d{2}[./\s]\d{4})'
    }
    for key, pattern in date_patterns.items():
        if not data.get(key):
            match = re.search(pattern, raw_text, re.IGNORECASE)
            if match:
                parsed_date = _parse_date(match.group(1))
                if parsed_date: data[key] = parsed_date
    for line in text_lines:
        if not data["last_name"]:
            last_name = _extract_value_from_line(line, ["nom", "surname"])
            if last_name: data["last_name"] = last_name
        if not data["first_name"]:
            first_name = _extract_value_from_line(line, ["prénom\(s\)", "prénom", "given name\(s\)", "given name"])
            if first_name: data["first_name"] = first_name
    required_fields = ["last_name", "first_name", "birth_date", "passport_number", "delivery_date", "expiration_date"]
    missing_fields = [field for field in required_fields if not data.get(field)]
    if missing_fields:
        missing_list = ', '.join([field.replace('_', ' ').title() for field in missing_fields])
        raise ValueError(f"Could not extract required fields: {missing_list}.")
    return data


def extract_data_page_by_page(file_content: bytes, content_type: str) -> List[Dict]:
    if not vision_client: raise RuntimeError("Google Vision client is not initialized.")
    all_results = []; image_pages = []
    if "pdf" in content_type:
        try:
            image_pages = convert_from_bytes(file_content, dpi=300)
        except Exception as e:
            raise RuntimeError("Could not process PDF. Ensure 'poppler' is installed and in PATH.") from e
    elif "image" in content_type:
        image_pages.append(file_content)
    else:
        raise HTTPException(status_code=400, detail="Unsupported file type.")

    for i, page_image in enumerate(image_pages):
        page_num = i + 1
        try:
            image_bytes = None
            if "pdf" in content_type:
                with io.BytesIO() as output: page_image.save(output, format="PNG"); image_bytes = output.getvalue()
            else: image_bytes = page_image
            image = vision.Image(content=image_bytes)
            response = vision_client.document_text_detection(image=image)
            if response.error.message: raise Exception(f"Google Vision API Error: {response.error.message}")
            full_text = response.full_text_annotation.text
            if not full_text: raise ValueError("No text detected on page.")

            # This is now the ONLY part that prints to the terminal
            mrz_lines_found = [line.strip() for line in full_text.split('\n') if '<' in line]
            if mrz_lines_found:
                print(f"PAGE {page_num}:")
                for line in mrz_lines_found:
                    print(line)

            parsed_data = _parse_passport_text(full_text)
            total_confidence, symbol_count = 0, 0
            for page in response.full_text_annotation.pages:
                for block in page.blocks:
                    for paragraph in block.paragraphs:
                        for word in paragraph.words:
                            for symbol in word.symbols:
                                total_confidence += symbol.confidence; symbol_count += 1
            average_confidence = (total_confidence / symbol_count) if symbol_count > 0 else 0.0
            parsed_data['confidence_score'] = round(average_confidence, 4)
            all_results.append({"page_number": page_num, "data": parsed_data})
        except Exception as e:
            # The error message from the logger will not print, but you'll get the raw error
            all_results.append({"page_number": page_num, "error": str(e)})
    return all_results
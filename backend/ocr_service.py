# --------------- START OF FILE: ocr_service.py ---------------

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
logger = logging.getLogger("ocr_service")
logger.setLevel(logging.INFO)
# logging.basicConfig(level=logging.INFO) # Logger is configured in main.py

# --- Google Cloud Client Initialization ---
vision_client = None
try:
    if not os.getenv("GOOGLE_APPLICATION_CREDENTIALS"):
        raise ValueError("GOOGLE_APPLICATION_CREDENTIALS environment variable must be set.")
    vision_client = vision.ImageAnnotatorClient()
except Exception as e:
    logger.error(f"🔴 [GCP] FAILED to initialize Google Cloud clients: {e}")
    raise e


# --- Parsing Helper Functions ---
def _parse_date_from_mrz(date_str: str) -> Optional[str]:
    if not date_str or len(date_str) != 6 or '<' in date_str: return None
    try:
        year, month, day = int(date_str[0:2]), int(date_str[2:4]), int(date_str[4:6])
        # Simple YY to YYYY conversion logic
        current_year_short = datetime.now().year % 100
        # Assumes birth dates are in the past and expiry dates are in the future
        # This logic might need refinement, but good for most cases.
        year += 1900 if year > current_year_short + 10 else 2000
        return datetime(year, month, day).strftime('%Y-%m-%d')
    except (ValueError, TypeError): return None

# --- Removed _parse_date and _extract_value_from_line as they are no longer needed ---

def _parse_passport_text(raw_text: str) -> Dict[str, Optional[str]]:
    """
    Extracts passport data exclusively from MRZ lines.
    """
    data = {
        "first_name": None, "last_name": None, "passport_number": None,
        "birth_date": None, "delivery_date": None, "expiration_date": None,
        "nationality": None,
    }
    
    # Clean all lines and remove spaces/special chars
    text_lines = [line.strip().replace(' ', '').replace('«', '<') for line in raw_text.split('\n')]
    
    # Find the start of the 2-line MRZ block
    mrz_line1_index = -1
    for i, line in enumerate(text_lines):
        # CRUCIAL: Find MRZ Line 1. It can start with P< (standard)
        # or <[3_LETTER_CODE] (if 'P' is hidden/not scanned).
        is_p_line = line.startswith('P<')
        is_alt_line = re.match(r'^<[A-Z]{3}', line)
        
        # Check if it looks like Line 1 (has '<<' for names) and is long enough
        if (is_p_line or is_alt_line) and '<<' in line and len(line) >= 44:
            # Check if the *next* line also looks like an MRZ line (Line 2)
            if i + 1 < len(text_lines) and len(text_lines[i+1].replace('<','')) > 10 and len(text_lines[i+1]) >= 44:
                mrz_line1_index = i
                break

    if mrz_line1_index != -1 and mrz_line1_index + 1 < len(text_lines):
        # --- We found the MRZ block, now parse it exclusively ---
        line1 = text_lines[mrz_line1_index].ljust(44, '<')
        line2_raw = text_lines[mrz_line1_index + 1]
        line2 = re.sub(r'[^A-Z0-9<]', '', line2_raw).ljust(44, '<') # Clean line 2

        # --- Parse Line 2 ---
        passport_num_raw = line2[0:9]
        
        # CRUCIAL: Correct '11' to 'II' in DD11DDDDD pattern
        match = re.match(r'(\d{2})11(\d{5})', passport_num_raw)
        if match:
            passport_num = f"{match.group(1)}II{match.group(2)}"
        else:
            passport_num = passport_num_raw.replace('<', '').strip()
        
        data["passport_number"] = passport_num or None
        data["nationality"] = line2[10:13].replace('<', '').strip() or None
        data["birth_date"] = _parse_date_from_mrz(line2[13:19])
        data["expiration_date"] = _parse_date_from_mrz(line2[21:27])

        # --- Parse Line 1 ---
        name_part = line1[5:44]
        parts = name_part.split('<<')
        if len(parts) >= 1:
            data["last_name"] = parts[0].replace('<', ' ').strip() or None
        if len(parts) >= 2:
            data["first_name"] = parts[1].replace('<', ' ').strip() or None
    
    # --- All other parsing logic is removed to meet MRZ-exclusive requirement ---

    # Check for required fields *from the MRZ*.
    # delivery_date is NOT in the MRZ, so it is not checked here.
    required_fields = ["last_name", "first_name", "birth_date", "passport_number", "expiration_date", "nationality"]
    missing_fields = [field for field in required_fields if not data.get(field)]
    
    if not data["passport_number"] and not data["last_name"]:
        raise ValueError("Could not find or parse MRZ lines.")
        
    if missing_fields:
        missing_list = ', '.join([field.replace('_', ' ').title() for field in missing_fields])
        raise ValueError(f"Could not extract required MRZ fields: {missing_list}.")
    
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
            line_to_extract = ""

            if mrz_lines_found:
                print(f"PAGE {page_num}:")
                for line in mrz_lines_found:
                    new_line = ""
                    for i in range(len(line)):
                        if line[i] == " " and line[i-1].isupper() and line[i+1].isupper():
                            new_line += "<"
                        elif line[i] == " ":
                            continue
                        else:
                            new_line += line[i]
                    line_to_extract += new_line   

                print(line_to_extract)
                print()

            parsed_data = _parse_passport_text(full_text)
            
            # Calculate confidence score
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
            all_results.append({"page_number": page_num, "error": str(e)})
            
    return all_results

# --------------- END OF FILE: ocr_service.py ---------------
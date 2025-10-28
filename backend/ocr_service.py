import os
import re
import io
import asyncio
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


# --- Helper function for date parsing (UNCHANGED) ---
def _parse_date_from_mrz(date_str: str) -> Optional[str]:
    """Helper to parse YYMMDD date string to YYYY-MM-DD."""
    # Remove any potential '<'
    date_str = date_str.replace('<', '')
    if not date_str or len(date_str) != 6 or not date_str.isdigit():
        return None
    try:
        # Parse date parts
        year, month, day = int(date_str[0:2]), int(date_str[2:4]), int(date_str[4:6])
        
        # Simple YY to YYYY conversion
        current_year_short = datetime.now().year % 100
        if year > current_year_short + 15: # e.g., '82' -> 1982 (likely birth date)
            year_full = 1900 + year
        else: # e.g., '33' (expiry) or '05' (birth) -> 2033 or 2005
            year_full = 2000 + year
            
        return datetime(year_full, month, day).strftime('%Y-%m-%d')
    except (ValueError, TypeError):
        return None

# --- FINAL Parsing Function (WITH FIX) ---
def _parse_passport_text(line_to_extract: str) -> Dict[str, Optional[str]]:
    """
    Extracts passport data from a single, concatenated MRZ string,
    which may have missing '<' or extra initials/noise from OCR.
    """
    data = {
        "first_name": None, "last_name": None, "passport_number": None,
        "birth_date": None, "delivery_date": None, # delivery_date is not in the MRZ
        "expiration_date": None, "nationality": None,
    }

    # Clean the string: remove spaces and fix common OCR errors
    s = line_to_extract.replace(' ', '').replace('«', '<')

    # This regex finds the stable "Line 2" block. This is the most
    # reliable anchor in a string with missing '<' characters.
    line2_pattern = re.compile(
        r'([A-Z0-9<]{9})'   # Group 1: Passport Number
        r'([0-9<]{1})'      # Group 2: Passport Check Digit
        r'(FRA)'            # Group 3: Nationality
        r'([0-9<]{6})'      # Group 4: Date of Birth
        r'([0-9<]{1})'      # Group 5: DOB Check Digit
        r'([MF<]{1})'       # Group 6: Sex
        r'([0-9<]{6})'      # Group 7: Expiration Date
        r'([0-9<]{1})'      # Group 8: Expiry Check Digit
    )
    
    line2_match = line2_pattern.search(s)

    if not line2_match:
        # If the pattern isn't found, we can't parse the string.
        raise ValueError("Could not parse MRZ. Stable pattern (Passport/FRA/Dates) not found.")

    # --- Extract data from the found pattern (UNCHANGED) ---
    passport_raw = line2_match.group(1).replace('<', '')
    data["nationality"] = line2_match.group(3)
    data["birth_date"] = _parse_date_from_mrz(line2_match.group(4))
    data["expiration_date"] = _parse_date_from_mrz(line2_match.group(7))

    # --- CRUCIAL: This handles the "1" vs "I" problem (UNCHANGED) ---
    if len(passport_raw) == 9:
        p_digits1 = passport_raw[0:2] # First 2 digits
        p_letters = passport_raw[2:4] # The 2 letters
        p_digits2 = passport_raw[4:9] # Last 5 digits
        
        # This replaces any '1' with 'I' ONLY in the letter part.
        p_letters_fixed = p_letters.replace('1', 'I')
        
        # Reconstruct the number
        data["passport_number"] = p_digits1 + p_letters_fixed + p_digits2
    else:
        # Fallback for malformed numbers (still replaces all '1's)
        data["passport_number"] = "---!!!---"

    # --- Parse the name from the part of the string BEFORE the match ---
    # *********** THIS IS THE FIX ***********
    line1_part = s[:line2_match.start()]
    
    # Find the 'FRA' country code in the first line. The name starts right after it.
    # This robustly handles 'P<FRA...', '<FRA...', or even just 'FRA...'
    code_index = line1_part.find('FRA')
    
    if code_index != -1:
        # Get everything after 'FRA'
        name_part = line1_part[code_index + 3:]
    else:
        # Fallback if 'FRA' isn't in the first part (unlikely)
        # We can't safely parse, so we'll just have an empty name
        name_part = "" 

    # Split name into last and first
    if name_part:
        name_parts = name_part.rstrip('<').split('<<')
        
        # This handles multiple last names like 'LE<SARAZIN'
        data["last_name"] = name_parts[0].replace('<', ' ').strip()
        
        if len(name_parts) > 1:
            # This joins all given names AND any initials (like R or C)
            data["first_name"] = ' '.join(name_parts[1:]).replace('<', ' ').strip()
    
    return data



async def extract_data_page_by_page(file_content: bytes, content_type: str) -> List[Dict]:
    if not vision_client: raise RuntimeError("Google Vision client is not initialized.")
    all_results = []; image_pages = []

    if "pdf" in content_type:
        try:
            # 3. Run the slow, blocking code in a thread
            image_pages = await asyncio.to_thread(
                convert_from_bytes, file_content, dpi=300
            )
        except Exception as e:
            raise RuntimeError("Could not process PDF. Ensure 'poppler' is in PATH.") from e
            
    # --- THIS IS THE MISSING PART ---
    elif "image" in content_type:
        image_pages.append(file_content) # Add the raw image bytes to the list
    # --- END OF FIX ---
    
    else:
        # You should also handle unsupported types
        raise HTTPException(status_code=400, detail="Unsupported file type.")


    for i, page_image in enumerate(image_pages):
        page_num = i + 1
        try:
            image_bytes = None
            if "pdf" in content_type:
                # page_image is a PIL Image, convert it to bytes
                with io.BytesIO() as output:
                    page_image.save(output, format="PNG")
                    image_bytes = output.getvalue()
            else:
                # page_image is already bytes (from the elif block)
                image_bytes = page_image 
            
            image = vision.Image(content=image_bytes)
            
            # 4. Run the slow, blocking network call in a thread
            response = await asyncio.to_thread(
                vision_client.document_text_detection, image=image
            )
            
            if response.error.message: raise Exception(f"Google Vision API Error: {response.error.message}")
            
            # ... (rest of your parsing logic remains the same) ...
            
            # Find and concatenate MRZ lines
            full_text = response.full_text_annotation.text
            if not full_text: raise ValueError("No text detected on page.")

            mrz_lines_found = [line.strip() for line in full_text.split('\n') if '<' in line]
            line_to_extract = ""

            if mrz_lines_found:
                # ... (This is your original logic from ocr_service.py)
                for line in mrz_lines_found:
                    new_line = ""
                    for j in range(len(line)):
                        if line[j] == " " and j > 0 and j < len(line) - 1 and line[j-1].isupper() and line[j+1].isupper():
                            new_line += "<"
                        elif line[j] == " ":
                            continue
                        else:
                            new_line += line[j]
                    line_to_extract += new_line
            
            if not line_to_extract:
                raise ValueError("No MRZ lines were found or concatenated.")

            parsed_data = _parse_passport_text(line_to_extract)
            
            # Calculate confidence
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
            # --- End of parsing logic ---
            
        except Exception as e:
            all_results.append({"page_number": page_num, "error": str(e)})

    return all_results
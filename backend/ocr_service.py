# --------------- START OF FILE: ocr_service.py ---------------

import os
import re
import logging
from datetime import datetime
from typing import Dict, Optional, List

# --- Google Cloud Vision API Configuration ---
# Make sure the GOOGLE_APPLICATION_CREDENTIALS environment variable is set.
from google.cloud import vision
from google.api_core import exceptions
from fastapi import HTTPException

# --- Logger Setup ---
# Use print statements for immediate visibility in the terminal during development
# logger = logging.getLogger("ocr_service")
# logger.setLevel(logging.INFO)

# --- Google Cloud Vision Client Initialization ---
vision_client = None
try:
    print("--- [GCP] Initializing Google Vision client... ---")
    if not os.getenv("GOOGLE_APPLICATION_CREDENTIALS"):
        print("🔴 [GCP] CRITICAL: GOOGLE_APPLICATION_CREDENTIALS environment variable is NOT SET.")
        raise ValueError("GOOGLE_APPLICATION_CREDENTIALS environment variable must be set.")
    
    vision_client = vision.ImageAnnotatorClient()
    print("✅ [GCP] Google Vision client initialized successfully.")
except Exception as e:
    print(f"🔴 [GCP] FAILED to initialize Google Vision client: {e}")
    # Application can run, but OCR features will fail.

def _parse_date_from_mrz(date_str: str) -> Optional[str]:
    """Parses a YYMMDD date string from MRZ and returns YYYY-MM-DD."""
    if not date_str or len(date_str) != 6 or '<' in date_str:
        return None
    try:
        year = int(date_str[0:2])
        month = int(date_str[2:4])
        day = int(date_str[4:6])

        current_year_short = datetime.now().year % 100
        # Add a 10 year buffer for expiry dates in the future
        if year > current_year_short + 10:
            year += 1900
        else:
            year += 2000

        return datetime(year, month, day).strftime('%Y-%m-%d')
    except (ValueError, TypeError):
        print(f"🟡 WARNING: Could not parse MRZ date string: {date_str}")
        return None

def _parse_date(date_str: Optional[str]) -> Optional[str]:
    """Helper to parse and format date string."""
    if not date_str:
        return None
    try:
        # Normalize separators and handle spaces
        cleaned_date_str = re.sub(r'[\s.]', '/', date_str).strip()
        # Find the date pattern
        match = re.search(r'(\d{2}/\d{2}/\d{4})', cleaned_date_str)
        if match:
            dt_obj = datetime.strptime(match.group(1), '%d/%m/%Y')
            return dt_obj.strftime('%Y-%m-%d')
        return None
    except ValueError:
        print(f"🟡 WARNING: Could not parse visual date string: {date_str}")
        return None

def _parse_passport_text(raw_text: str) -> Dict[str, Optional[str]]:
    """
    Parses raw OCR text from a passport to extract structured data.
    This version uses more robust regex for visual parsing and has detailed logging.
    """
    print("\n--- NEW PAGE ANALYSIS ---")
    # print("--- RAW OCR TEXT ---\n" + raw_text + "\n--- END RAW OCR TEXT ---")
    
    data = {
        "first_name": None, "last_name": None, "passport_number": None,
        "birth_date": None, "delivery_date": None, "expiration_date": None,
        "nationality": "FRANCAISE",
    }
    
    raw_text_lines = raw_text.split('\n')
    text_lines = [line.strip() for line in raw_text_lines]
    
    # --- STAGE 1: Attempt to parse the MRZ (most reliable) ---
    print("[STAGE 1] Searching for MRZ (Machine-Readable Zone)...")
    mrz_line1_index = -1
    for i, line in enumerate(text_lines):
        cleaned_line = line.replace(' ', '').replace('«', '<')
        if cleaned_line.startswith('P<') and len(cleaned_line) > 30:
            mrz_line1_index = i
            break
            
    if mrz_line1_index != -1 and mrz_line1_index + 1 < len(text_lines):
        print(f"✅ Found potential MRZ Line 1 at index {mrz_line1_index}.")
        line1 = text_lines[mrz_line1_index].replace(' ', '').replace('«', '<').ljust(44, '<')
        line2_raw = text_lines[mrz_line1_index + 1].replace(' ', '').replace('«', '<')
        line2 = re.sub(r'[^A-Z0-9<]', '', line2_raw).ljust(44, '<')

        # --- Parse Line 2 ---
        data["passport_number"] = line2[0:9].replace('<', '').strip() or None
        data["nationality"] = line2[10:13].strip() or "FRANCAISE"
        data["birth_date"] = _parse_date_from_mrz(line2[13:19])
        data["expiration_date"] = _parse_date_from_mrz(line2[21:27])
        
        # --- Parse Line 1 ---
        name_part = line1[5:44]
        parts = name_part.split('<<')
        if len(parts) >= 1:
            data["last_name"] = parts[0].replace('<', ' ').strip() or None
        if len(parts) >= 2:
            data["first_name"] = parts[1].replace('<', ' ').strip() or None
        
        print(f"    MRZ Parse Result -> Name: {data['first_name']} {data['last_name']}, PN: {data['passport_number']}, DoB: {data['birth_date']}, Exp: {data['expiration_date']}")
    else:
        print("    No valid MRZ found.")

    # --- STAGE 2: Use regex on the visual part as a fallback or to supplement ---
    print("[STAGE 2] Using visual analysis as fallback...")

    # Fallback for Passport Number
    if not data["passport_number"]:
        match = re.search(r'\b([A-Z]{2}\d{7}|\d{2}[A-Z]{2}\d{5})\b', raw_text.replace(" ", ""))
        if match:
            data["passport_number"] = match.group(1)
            print(f"    Fallback found Passport Number: {data['passport_number']}")

    # Fallback for Names
    for line in raw_text_lines:
        if not data["last_name"] and ("nom" in line.lower() or "surname" in line.lower()):
            value = re.sub(r'(nom|surname|/|\s|:)*', '', line, flags=re.IGNORECASE).strip()
            if len(value) > 1:
                data["last_name"] = value
                print(f"    Fallback found Last Name: {data['last_name']}")
        
        if not data["first_name"] and ("prénom" in line.lower() or "given name" in line.lower()):
            value = re.sub(r'(prénom\(s\)|prénom|given name\(s\)|given name|/|\s|:)*', '', line, flags=re.IGNORECASE).strip()
            if len(value) > 1:
                data["first_name"] = value
                print(f"    Fallback found First Name: {data['first_name']}")

    # A more robust fallback for DATES that looks for the keyword and date across multiple lines
    date_patterns = {
        'birth_date': r'(?:naissance|birth)[\s\S]*?(\d{2}[./\s]\d{2}[./\s]\d{4})',
        'delivery_date': r'(?:délivrance|issue)[\s\S]*?(\d{2}[./\s]\d{2}[./\s]\d{4})',
        'expiration_date': r'(?:expiration|expiry|expire\sle)[\s\S]*?(\d{2}[./\s]\d{2}[./\s]\d{4})'
    }

    for key, pattern in date_patterns.items():
        if not data.get(key):
            match = re.search(pattern, raw_text, re.IGNORECASE)
            if match:
                parsed_date = _parse_date(match.group(1))
                if parsed_date:
                    data[key] = parsed_date
                    print(f"    Fallback found {key}: {data[key]}")

    # --- STAGE 3: Final validation ---
    print("[STAGE 3] Validating required fields...")
    required_fields = ["last_name", "first_name", "birth_date", "passport_number", "delivery_date", "expiration_date"]
    missing_fields = [field for field in required_fields if not data.get(field)]
    
    if missing_fields:
        missing_list = ', '.join([field.replace('_', ' ').title() for field in missing_fields])
        print(f"    🔴 FAILED: Missing fields -> {missing_list}")
        raise ValueError(f"Could not extract required fields: {missing_list}.")
    
    print(f"    ✅ SUCCESS: All required fields found.")
    return data

def extract_document_data_sync(file_content: bytes, content_type: str) -> List[Dict]:
    """
    Performs synchronous OCR on a multi-page PDF/image, parses the results,
    and returns the structured data.
    """
    print("\n\n--- [Vision] Starting new document extraction job ---")
    if not vision_client:
        print("🔴 [Vision] Cannot start OCR: Google Vision client is not initialized.")
        raise RuntimeError("Google Vision client is not initialized.")
        
    if "pdf" not in content_type and "image" not in content_type:
        raise HTTPException(status_code=400, detail="Only PDF and image files are supported.")

    input_config = vision.InputConfig(content=file_content, mime_type=content_type)
    feature = vision.Feature(type_=vision.Feature.Type.DOCUMENT_TEXT_DETECTION)
    request = vision.AnnotateFileRequest(features=[feature], input_config=input_config)

    try:
        print("[Vision] Sending batch_annotate_files request to Google...")
        response = vision_client.batch_annotate_files(requests=[request])
        print("✅ [Vision] Received response from Google.")
    except exceptions.GoogleAPICallError as e:
        print(f"🔴 [Vision] API call failed: {e}")
        raise RuntimeError(f"Google Vision API Error: {e.message}") from e

    document_responses = response.responses[0].responses
    print(f"[Vision] Found {len(document_responses)} pages in the document.")
    
    results = []
    for page_response in document_responses:
        actual_page_num = page_response.context.page_number
        print(f"\n==================== PROCESSING PAGE {actual_page_num} ====================")
        try:
            if page_response.error.message:
                raise ValueError(page_response.error.message)
            
            full_text = page_response.full_text_annotation.text
            if not full_text:
                raise ValueError("No text detected on page.")

            parsed_data = _parse_passport_text(full_text)
            
            total_confidence, symbol_count = 0, 0
            for page in page_response.full_text_annotation.pages:
                for block in page.blocks:
                    for paragraph in block.paragraphs:
                        for word in paragraph.words:
                            for symbol in word.symbols:
                                total_confidence += symbol.confidence
                                symbol_count += 1
            
            average_confidence = (total_confidence / symbol_count) if symbol_count > 0 else 0.0
            parsed_data['confidence_score'] = round(average_confidence, 4)
            
            print(f"✅ Successfully parsed page {actual_page_num}. Confidence: {average_confidence:.2%}")
            results.append({"page_number": actual_page_num, "data": parsed_data})

        except Exception as e:
            print(f"🔴 Failed to parse page {actual_page_num}: {e}")
            results.append({"page_number": actual_page_num, "error": str(e)})
            
    return results

# --------------- END OF FILE: ocr_service.py ---------------
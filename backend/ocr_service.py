# there must be integrated the content provided of you for this file
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
logger = logging.getLogger("ocr_service")
logger.setLevel(logging.INFO)

# --- Google Cloud Vision Client Initialization ---
vision_client = None
try:
    logger.info("--- [GCP] Initializing Google Vision client... ---")
    if not os.getenv("GOOGLE_APPLICATION_CREDENTIALS"):
        logger.error("🔴 [GCP] CRITICAL: GOOGLE_APPLICATION_CREDENTIALS environment variable is NOT SET.")
        raise ValueError("GOOGLE_APPLICATION_CREDENTIALS environment variable must be set.")
    
    vision_client = vision.ImageAnnotatorClient()
    logger.info("✅ [GCP] Google Vision client initialized successfully.")
except Exception as e:
    logger.error(f"🔴 [GCP] FAILED to initialize Google Vision client: {e}")
    # Application can run, but OCR features will fail.

def _parse_date_from_mrz(date_str: str) -> Optional[str]:
    """Parses a YYMMDD date string from MRZ and returns YYYY-MM-DD."""
    if not date_str or len(date_str) != 6:
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
        logger.warning(f"Could not parse MRZ date string: {date_str}")
        return None

def _parse_date(date_str: Optional[str]) -> Optional[str]:
    """Helper to parse and format date string."""
    if not date_str:
        return None
    try:
        cleaned_date_str = date_str.replace('.', '/').replace(' ', '/')
        dt_obj = datetime.strptime(cleaned_date_str, '%d/%m/%Y')
        return dt_obj.strftime('%Y-%m-%d')
    except ValueError:
        logger.warning(f"Could not parse date string: {date_str}")
        return None

def _parse_passport_text(raw_text: str) -> Dict[str, Optional[str]]:
    """
    Parses raw OCR text from a passport to extract structured data.
    It prioritizes parsing the Machine-Readable Zone (MRZ) for accuracy.
    """
    data = {
        "first_name": None, "last_name": None, "passport_number": None,
        "birth_date": None, "delivery_date": None, "expiration_date": None,
        "nationality": "FRANCAISE",
    }
    
    raw_text_lines = raw_text.split('\n')
    text_lines = [line.strip() for line in raw_text_lines]
    
    # --- STAGE 1: Attempt to parse the MRZ (most reliable) ---
    mrz_line1_index = -1

    for i, line in enumerate(text_lines):
        cleaned_line = line.replace(' ', '').replace('«', '<')
        if cleaned_line.startswith('P<') and len(cleaned_line) > 30:
            mrz_line1_index = i
            break
            
    if mrz_line1_index != -1 and mrz_line1_index + 1 < len(text_lines):
        logger.info(f"Found potential MRZ Line 1 at index {mrz_line1_index}.")
        line1 = text_lines[mrz_line1_index].replace(' ', '').replace('«', '<').ljust(44, '<')
        line2_raw = text_lines[mrz_line1_index + 1].replace(' ', '').replace('«', '<')
        line2 = re.sub(r'[^A-Z0-9<]', '', line2_raw).ljust(44, '<')

        # --- Parse Line 2 ---
        data["passport_number"] = line2[0:9].replace('<', '').strip() or None
        data["nationality"] = line2[10:13].strip() or "FRANCAISE"
        data["birth_date"] = _parse_date_from_mrz(line2[13:19])
        data["expiration_date"] = _parse_date_from_mrz(line2[21:27])
        logger.info(f"MRZ Line 2 Parsed: PN={data['passport_number']}, Nat={data['nationality']}, DoB={data['birth_date']}, Exp={data['expiration_date']}")

        # --- Parse Line 1 ---
        name_part = line1[5:44]
        parts = name_part.split('<<')
        if len(parts) >= 1:
            data["last_name"] = parts[0].replace('<', ' ').strip() or None
        if len(parts) >= 2:
            data["first_name"] = parts[1].replace('<', ' ').strip() or None
        logger.info(f"MRZ Line 1 Parsed: Last={data['last_name']}, First={data['first_name']}")

    # --- STAGE 2: Use regex on the visual part as a fallback ---
    if not data["passport_number"]:
        match = re.search(r'\b([A-Z]{2}\d{7}|\d{2}[A-Z]{2}\d{5})\b', raw_text.replace(" ", ""))
        if match: data["passport_number"] = match.group(1)

    for line in raw_text_lines:
        line_lower = line.lower()
        if not data["last_name"] and ('nom' in line_lower or 'surname' in line_lower):
            value = re.sub(r'(nom|surname|/|\s|:)*', '', line, flags=re.IGNORECASE)
            if len(value) > 1: data["last_name"] = value.strip()
        
        if not data["first_name"] and ('prénom' in line_lower or 'given name' in line_lower):
            value = re.sub(r'(prénom\(s\)|prénom|given name\(s\)|given name|/|\s|:)*', '', line, flags=re.IGNORECASE)
            if len(value) > 1: data["first_name"] = value.strip()
        
        date_match = re.search(r'(\d{2}[./\s]\d{2}[./\s]\d{4})', line)
        if date_match:
            if not data["birth_date"] and ('naissance' in line_lower or 'birth' in line_lower):
                data["birth_date"] = _parse_date(date_match.group(1))
            if not data["delivery_date"] and ('délivrance' in line_lower or 'issue' in line_lower):
                data["delivery_date"] = _parse_date(date_match.group(1))
            if not data["expiration_date"] and ('expiration' in line_lower or 'expiry' in line_lower):
                data["expiration_date"] = _parse_date(date_match.group(1))

    # --- STAGE 3: Final validation ---
    required_fields = ["last_name", "first_name", "birth_date", "passport_number"]
    missing_fields = [field for field in required_fields if not data.get(field)]
    
    if missing_fields:
        missing_list = ', '.join([field.replace('_', ' ').title() for field in missing_fields])
        logger.warning(f"Missing required fields after parsing: {missing_list}")
        raise ValueError(f"Could not extract required fields: {missing_list}.")
        
    return data

def extract_document_data_sync(file_content: bytes, content_type: str) -> List[Dict]:
    """
    Performs synchronous OCR on a multi-page PDF file's content, parses the results,
    and returns the structured data.
    """
    logger.info("--- [Vision] Starting synchronous OCR extraction ---")
    if not vision_client:
        logger.error("🔴 [Vision] Cannot start OCR: Google Vision client is not initialized.")
        raise RuntimeError("Google Vision client is not initialized.")
        
    if "pdf" not in content_type and "image" not in content_type:
        raise HTTPException(status_code=400, detail="Only PDF and image files are supported.")

    # Prepare the request for the Vision API using the file's byte content directly
    input_config = vision.InputConfig(content=file_content, mime_type=content_type)
    feature = vision.Feature(type_=vision.Feature.Type.DOCUMENT_TEXT_DETECTION)
    request = vision.AnnotateFileRequest(features=[feature], input_config=input_config)

    try:
        # Execute the synchronous batch request
        logger.info("[Vision] Sending batch_annotate_files request to Google...")
        response = vision_client.batch_annotate_files(requests=[request])
        logger.info("✅ [Vision] Received response from Google.")
    except exceptions.GoogleAPICallError as e:
        logger.error(f"🔴 [Vision] API call failed: {e}")
        raise RuntimeError(f"Google Vision API Error: {e.message}") from e

    # The batch response contains a list of responses, one for each file in the request.
    # Since we only send one file, we access the first one.
    document_responses = response.responses[0].responses
    logger.info(f"[Vision] Found {len(document_responses)} pages in the document.")
    
    results = []
    for page_response in document_responses:
        actual_page_num = page_response.context.page_number
        try:
            if page_response.error.message:
                raise ValueError(page_response.error.message)
            
            full_text = page_response.full_text_annotation.text
            if not full_text:
                raise ValueError("No text detected on page.")

            # Parse the extracted text to get structured data
            parsed_data = _parse_passport_text(full_text)
            
            # Calculate the average confidence score for the page
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
            
            logger.info(f"✅ Parsed page {actual_page_num} successfully. Confidence: {average_confidence:.2%}")
            results.append({"page_number": actual_page_num, "data": parsed_data})

        except Exception as e:
            logger.warning(f"🟡 Failed to parse page {actual_page_num}: {e}")
            results.append({"page_number": actual_page_num, "error": str(e)})
            
    return results

# --------------- END OF FILE: ocr_service.py ---------------
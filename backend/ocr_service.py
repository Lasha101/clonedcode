import os
import re
import io
from datetime import datetime
from typing import Dict, Optional, List
import logging
import json
import asyncio
import uuid # For unique filenames

from google.cloud import vision
from google.cloud import storage # <-- NEW: For GCS
from fastapi import HTTPException

# --- Logger Setup ---
logger = logging.getLogger("ocr_service")
logger.setLevel(logging.INFO)

# --- Google Cloud Client Initialization ---
vision_client = None
storage_client = None
GCS_INPUT_BUCKET = os.getenv("GCS_INPUT_BUCKET")
GCS_OUTPUT_BUCKET = os.getenv("GCS_OUTPUT_BUCKET")

try:
    if not os.getenv("GOOGLE_APPLICATION_CREDENTIALS"):
        raise ValueError("GOOGLE_APPLICATION_CREDENTIALS environment variable must be set.")
    if not GCS_INPUT_BUCKET or not GCS_OUTPUT_BUCKET:
        raise ValueError("GCS_INPUT_BUCKET and GCS_OUTPUT_BUCKET must be set in .env")

    vision_client = vision.ImageAnnotatorClient()
    storage_client = storage.Client()
    logger.info("✅ Google Cloud Vision and Storage clients initialized.")

except Exception as e:
    logger.error(f"🔴 [GCP] FAILED to initialize Google Cloud clients: {e}")
    # We don't raise here, to allow the app to start, but OCR will fail.
    # The functions below will check for client initialization.

# --- Helper Functions (UNCHANGED) ---

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

def _parse_passport_text(line_to_extract: str) -> Dict[str, Optional[str]]:
    """
    Extracts passport data from a single, concatenated MRZ string.
    (This function is unchanged from your original)
    """
    data = {
        "first_name": None, "last_name": None, "passport_number": None,
        "birth_date": None, "delivery_date": None, # delivery_date is not in the MRZ
        "expiration_date": None, "nationality": None,
    }
    s = line_to_extract.replace(' ', '').replace('«', '<')
    line2_pattern = re.compile(
        r'([A-Z0-9<]{9})'    # Group 1: Passport Number
        r'([0-9<]{1})'      # Group 2: Passport Check Digit
        r'(FRA)'             # Group 3: Nationality
        r'([0-9<]{6})'      # Group 4: Date of Birth
        r'([0-9<]{1})'      # Group 5: DOB Check Digit
        r'([MF<]{1})'       # Group 6: Sex
        r'([0-9<]{6})'      # Group 7: Expiration Date
        r'([0-9<]{1})'      # Group 8: Expiry Check Digit
    )
    line2_match = line2_pattern.search(s)
    if not line2_match:
        raise ValueError("Could not parse MRZ. Stable pattern (Passport/FRA/Dates) not found.")
    
    passport_raw = line2_match.group(1).replace('<', '')
    data["nationality"] = line2_match.group(3)
    data["birth_date"] = _parse_date_from_mrz(line2_match.group(4))
    data["expiration_date"] = _parse_date_from_mrz(line2_match.group(7))

    if len(passport_raw) == 9:
        p_digits1 = passport_raw[0:2]; p_letters = passport_raw[2:4]; p_digits2 = passport_raw[4:9]
        p_letters_fixed = p_letters.replace('1', 'I')
        data["passport_number"] = p_digits1 + p_letters_fixed + p_digits2
    else:
        data["passport_number"] = "---!!!---"

    line1_part = s[:line2_match.start()]
    code_index = line1_part.find('FRA')
    
    if code_index != -1:
        name_part = line1_part[code_index + 3:]
    else:
        name_part = "" 

    if name_part:
        name_parts = name_part.rstrip('<').split('<<')
        data["last_name"] = name_parts[0].replace('<', ' ').strip()
        if len(name_parts) > 1:
            data["first_name"] = ' '.join(name_parts[1:]).replace('<', ' ').strip()
    
    return data

# --- NEW GCS HELPER FUNCTIONS ---

async def _upload_to_gcs(file_content: bytes, content_type: str, file_name: str) -> str:
    """Uploads file content to GCS and returns the GCS URI."""
    if not storage_client:
        raise RuntimeError("Google Storage client is not initialized.")
    
    bucket = storage_client.bucket(GCS_INPUT_BUCKET)
    blob = bucket.blob(file_name)
    
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(
        None, # Uses the default thread pool
        lambda: blob.upload_from_string(file_content, content_type=content_type)
    )
    
    return f"gs://{GCS_INPUT_BUCKET}/{file_name}"

async def _delete_gcs_blob(bucket_name: str, blob_name: str):
    """Deletes a file from a GCS bucket."""
    try:
        bucket = storage_client.bucket(bucket_name)
        blob = bucket.blob(blob_name)
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, blob.delete)
        logger.info(f"Cleaned up GCS blob: {bucket_name}/{blob_name}")
    except Exception as e:
        logger.warning(f"Failed to cleanup GCS blob: {bucket_name}/{blob_name}. Error: {e}")

async def _delete_gcs_prefix(bucket_name: str, prefix: str):
    """Deletes all files under a 'folder' in GCS."""
    try:
        bucket = storage_client.bucket(bucket_name)
        blobs_to_delete = list(bucket.list_blobs(prefix=prefix)) # Must list() before async loop
        loop = asyncio.get_event_loop()
        delete_tasks = []
        for blob in blobs_to_delete:
            delete_tasks.append(
                loop.run_in_executor(None, blob.delete)
            )
        if delete_tasks:
            await asyncio.gather(*delete_tasks)
        logger.info(f"Cleaned up GCS prefix: {bucket_name}/{prefix}")
    except Exception as e:
        logger.warning(f"Failed to cleanup GCS prefix: {bucket_name}/{prefix}. Error: {e}")

# --- MAIN SERVICE FUNCTION (COMPLETELY REWRITTEN) ---

def _parse_mrz_from_response(response, page_num: int) -> Dict:
    """
    Internal helper to parse a single Vision API response.
    This logic was moved from the main function.
    """
    try:
        # Check for errors in the Vision API response itself
        if hasattr(response, 'error') and response.error.message:
            raise Exception(f"Google Vision API Error: {response.error.message}")
        
        full_text = response.full_text_annotation.text
        if not full_text:
            raise ValueError("No text detected on page.")

        # --- This is your original MRZ-finding logic ---
        mrz_lines_found = [line.strip() for line in full_text.split('\n') if '<' in line]
        line_to_extract = ""
        if mrz_lines_found:
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
        # --- End of MRZ-finding logic ---

        # Calculate confidence
        total_confidence, symbol_count = 0, 0
        if response.full_text_annotation.pages:
            for page in response.full_text_annotation.pages:
                for block in page.blocks:
                    for paragraph in block.paragraphs:
                        for word in paragraph.words:
                            for symbol in word.symbols:
                                total_confidence += symbol.confidence; symbol_count += 1
        average_confidence = (total_confidence / symbol_count) if symbol_count > 0 else 0.0
        parsed_data['confidence_score'] = round(average_confidence, 4)
        
        return {"page_number": page_num, "data": parsed_data}

    except Exception as e:
        logger.error(f"Error parsing response for page {page_num}: {e}", exc_info=True)
        return {"page_number": page_num, "error": str(e)}


async def extract_data_page_by_page(file_content: bytes, content_type: str) -> List[Dict]:
    """
    Extracts passport data by offloading all processing to Google Cloud.
    """
    if not vision_client or not storage_client:
        raise HTTPException(status_code=500, detail="OCR service is not initialized.")

    # Generate a unique name for the GCS file
    file_id = str(uuid.uuid4())
    gcs_input_filename = f"ocr_uploads/{file_id}"
    gcs_input_uri = f"gs://{GCS_INPUT_BUCKET}/{gcs_input_filename}"
    
    all_results = []
    loop = asyncio.get_event_loop()

    try:
        # 1. Upload the file to GCS (runs in a thread)
        await _upload_to_gcs(file_content, content_type, gcs_input_filename)

        if "pdf" in content_type:
            # --- PDF Processing (Batch Mode) ---
            gcs_output_uri_prefix = f"ocr_results/{file_id}/"
            gcs_output_uri = f"gs://{GCS_OUTPUT_BUCKET}/{gcs_output_uri_prefix}"

            mime_type = 'application/pdf'
            feature = vision.Feature(type_=vision.Feature.Type.DOCUMENT_TEXT_DETECTION)
            
            # --- FIX IS HERE ---
            # 1. Create the GcsSource
            gcs_source = vision.GcsSource(uri=gcs_input_uri)
            # 2. Create the InputConfig and put the GcsSource AND mime_type inside it
            input_config = vision.InputConfig(
                gcs_source=gcs_source,
                mime_type=mime_type
            )
            
            # 3. Create the GcsDestination
            gcs_destination = vision.GcsDestination(uri=gcs_output_uri)
            # 4. Create the OutputConfig and put the GcsDestination inside it
            output_config = vision.OutputConfig(
                gcs_destination=gcs_destination,
                batch_size=1 # Specify batch size for PDF
            )

            # 5. Now, this request is valid because all its parameters are the correct type
            request = vision.AsyncAnnotateFileRequest(
                features=[feature],
                input_config=input_config,
                output_config=output_config
            )
            # --- END OF FIX ---

            # Start the batch operation
            # --- FIX IS HERE ---
            # We must use a lambda to correctly pass the `requests` keyword argument
            # to the client function when using run_in_executor.
            operation = await loop.run_in_executor(
                None,
                lambda: vision_client.async_batch_annotate_files(requests=[request])
            )
            # --- END OF FIX ---
            
            logger.info(f"Waiting for GCS batch operation {operation.operation.name}...")
            # Wait for the operation to complete. This polls Google.
            # We set a timeout (e.g., 5 minutes)
            # --- FIX IS HERE ---
            # We must use a lambda to pass the `timeout` keyword argument
            # to the operation.result() function.
            response = await loop.run_in_executor(
                None, lambda: operation.result(timeout=300)
            )
            # --- END OF FIX ---
            
            logger.info(f"Batch operation complete. Fetching results from {gcs_output_uri}")

            # 3. Get results from output bucket
            output_bucket = storage_client.bucket(GCS_OUTPUT_BUCKET)
            blobs = list(output_bucket.list_blobs(prefix=gcs_output_uri_prefix)) # Must list()
            
            json_blobs = [b for b in blobs if b.name.endswith('.json')]
            json_blobs.sort(key=lambda b: b.name) # Sort to get pages in order

            if not json_blobs:
                raise Exception("No result files found in GCS output bucket.")

            for blob in json_blobs:
                # Download JSON content
                json_string = await loop.run_in_executor(None, blob.download_as_string)
                response_json = json.loads(json_string)
                
                # Each JSON file can contain multiple page responses
                for page_index, resp_dict in enumerate(response_json['responses']):
                    # Convert the dict back to a standard Vision API response object
                    # so our parser function can be reused
                    page_response = vision.AnnotateImageResponse.from_json(json.dumps(resp_dict))
                    
                    page_num = page_response.context.page_number
                    if page_num == 0: # Fallback if page number isn't in context
                        page_num = page_index + 1
                        
                    result = _parse_mrz_from_response(page_response, page_num)
                    all_results.append(result)

            # 4. Clean up GCS output "folder"
            await _delete_gcs_prefix(GCS_OUTPUT_BUCKET, gcs_output_uri_prefix)

        elif "image" in content_type:
            # --- Single Image Processing ---
            image = vision.Image(source=vision.ImageSource(gcs_image_uri=gcs_input_uri))
            # --- FIX IS HERE --- (Corrected double underscore typo)
            feature = vision.Feature(type_=vision.Feature.Type.DOCUMENT_TEXT_DETECTION)
            request = vision.AnnotateImageRequest(image=image, features=[feature])

            # --- FIX IS HERE ---
            # Pass `request` as a positional argument, not a keyword argument
            # to run_in_executor.
            response = await loop.run_in_executor(
                None, vision_client.annotate_image, request
            )
            # --- END OF FIX ---
            
            # --- FIX IS HERE --- (Corrected typo from our previous conversation)
            result = _parse_mrz_from_response(response, page_num=1)
            all_results.append(result)
        
        else:
            raise HTTPException(status_code=400, detail="Unsupported file type.")

    except Exception as e:
        logger.error(f"Error during GCS extraction: {e}", exc_info=True)
        # Add a general failure if the whole process died
        if not all_results:
            all_results.append({"page_number": 1, "error": f"Failed to process file: {str(e)}"})
    
    finally:
        # 5. Clean up the input file from GCS, regardless of success or failure
        if gcs_input_filename: # Check if it was ever set
            await _delete_gcs_blob(GCS_INPUT_BUCKET, gcs_input_filename)

    return all_results



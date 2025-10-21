
import re
from datetime import datetime
from google.cloud import vision
from fastapi import HTTPException
import logging
import fitz  # PyMuPDF
import unicodedata



# It's good practice to use logging to see what the OCR is detecting
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def clean_and_parse_date(date_str: str) -> datetime | None:
    """
    Cleans a date string by removing unexpected characters and
    attempts to parse it into a datetime object.
    """
    if not date_str:
        return None
    # Replace common separators like '.' or ',' with a space to handle OCR errors
    cleaned_str = re.sub(r'[.,]', ' ', date_str)
    # Remove any other non-digit, non-space characters
    cleaned_str = re.sub(r'[^\d\s]', '', cleaned_str)
    # Normalize multiple spaces to a single space
    cleaned_str = re.sub(r'\s+', ' ', cleaned_str).strip()
    
    # The expected format is DD MM YYYY
    try:
        return datetime.strptime(cleaned_str, "%d %m %Y")
    except ValueError:
        logger.warning(f"Impossible d'analyser la date : '{date_str}' (nettoyée en: '{cleaned_str}')")
        return None


def _extract_passport_data_from_image_bytes(image_bytes: bytes) -> dict:
    """
    (Internal function) Uses Google Vision API to extract text from image bytes
    and attempts to parse it into structured French passport data.

    Args:
        image_bytes: The byte content of an image file (PNG, JPEG, etc.).

    Returns:
        A dictionary containing the extracted passport information.
    """
    client = vision.ImageAnnotatorClient()
    image = vision.Image(content=image_bytes)
    image_context = vision.ImageContext(language_hints=['fr'])

    # Perform document text detection for better accuracy on documents
    response = client.document_text_detection(image=image, image_context=image_context)
    full_text_annotation = response.full_text_annotation

    if not full_text_annotation or not full_text_annotation.pages:
        raise HTTPException(status_code=400, detail="Aucun texte n'a pu être détecté dans le document.")

    # The full, raw text.
    raw_text = full_text_annotation.text
    clean_text = re.sub(r'[\n/]', ' ', raw_text)  # Replace newlines and slashes with spaces
    full_text = re.sub(r'\s+', ' ', clean_text).strip()  # Normalize all whitespace

    logger.info("--- Texte OCR extrait complet ---")
    logger.info(full_text)
    logger.info("-----------------------------")

    # --- Parsing Logic for French Passports ---
    data = {
        "first_name": "", "last_name": "", "passport_number": "",
        "nationality": "", "birth_date": "", "delivery_date": "",
        "expiration_date": "", "confidence_score": 0.0
    }

    # --- MRZ-First Parsing & Verification ---
    mrz_text = full_text.replace(' ', '').replace('<', '<')
    mrz_line1_match = re.search(r'P<FRA([A-Z<]+)<<([A-Z<]+)', mrz_text)
    if mrz_line1_match:
        data["last_name"] = mrz_line1_match.group(1).replace('<', ' ').strip()
        data["first_name"] = ' '.join(mrz_line1_match.group(2).replace('<', ' ').strip().split())

    mrz_line2_match = re.search(r'(\d{2}[A-Z]{2}\d{5})\d?(FRA)(\d{2}\d{2}\d{2})\d[MFX<](\d{2}\d{2}\d{2})', mrz_text)
    if mrz_line2_match:
        data["nationality"] = "Française"
        data["passport_number"] = mrz_line2_match.group(1)
        dob_str = mrz_line2_match.group(3)
        try:
            year = int(dob_str[0:2])
            # Corrected century logic for birth dates
            current_year_short = datetime.now().year % 100
            prefix = "19" if year > current_year_short else "20"
            dob_dt = datetime.strptime(f"{prefix}{dob_str}", "%Y%m%d")
            data["birth_date"] = dob_dt.strftime("%Y-%m-%d")
        except ValueError:
            logger.warning(f"Impossible d'analyser la date de naissance à partir de la MRZ : {dob_str}")

        exp_str = mrz_line2_match.group(4)
        try:
            # Assuming expiration dates are always in the 21st century for modern passports
            exp_dt = datetime.strptime(f"20{exp_str}", "%Y%m%d")
            data["expiration_date"] = exp_dt.strftime("%Y-%m-%d")
        except ValueError:
            logger.warning(f"Impossible d'analyser la date d'expiration à partir de la MRZ : {exp_str}")

    # --- Visual Zone Parsing (Fallback) ---
    if not data["passport_number"]:
        passport_match = re.search(r'\b(\d{2}[A-Z]{2}\d{5})\b', full_text)
        if passport_match: data["passport_number"] = passport_match.group(1)
    if not data["last_name"]:
        last_name_match = re.search(r'(?:Nom|SURNAME)\s+([A-Z\s\'-]+?)(?=\s*Prénom|GIVEN|Nationalité|Date|P<|$)', full_text, re.IGNORECASE)
        if last_name_match: data["last_name"] = last_name_match.group(1).strip()
    if not data["first_name"]:
        first_name_match = re.search(r'(?:Prénom\(s\)|Prénoms|GIVEN NAMES)\s+([A-Z][a-zA-Z\s\'-]+?)(?=\s*Nationalité|Date|Sexe|Sex|P<|$)', full_text, re.IGNORECASE)
        if first_name_match: data["first_name"] = first_name_match.group(1).strip()
    if data["last_name"] and not data["first_name"] and ' ' in data["last_name"]:
        parts = data["last_name"].split()
        if len(parts) > 1:
            data["last_name"] = parts[0]
            data["first_name"] = " ".join(parts[1:])
    if not data["nationality"]:
        nationality_match = re.search(r'(?:Nationalité|Nationality)\s+([A-Za-zçÇéÉèÈàÀâÂêÊîÎôÔûÛ]+)', full_text, re.IGNORECASE)
        if nationality_match and "française".lower() in nationality_match.group(1).lower():
            data["nationality"] = "Française"
    if not data["delivery_date"]:
        date_matches = re.findall(r'(\d{2}\s*[.,]?\s*\d{2}\s*[.,]?\s*\d{4})', full_text)
        parsed_dates = [dt for dt_str in date_matches if (dt := clean_and_parse_date(dt_str))]
        unique_dates = sorted(list(set(parsed_dates)))
        birth_dt = datetime.strptime(data["birth_date"], "%Y-%m-%d") if data["birth_date"] else None
        exp_dt = datetime.strptime(data["expiration_date"], "%Y-%m-%d") if data["expiration_date"] else None
        for dt in unique_dates:
            if dt != birth_dt and dt != exp_dt:
                data["delivery_date"] = dt.strftime("%Y-%m-%d")
                break

    relevant_confidences = []
    target_words = set()

    def clean_for_match(text: str) -> str:
        text = text.upper()
        text = ''.join(c for c in unicodedata.normalize('NFD', text) if unicodedata.category(c) != 'Mn')
        text = re.sub(r'[^A-Z0-9]', '', text)
        return text
    
    fields_to_score = ["last_name", "first_name", "passport_number", "nationality"]

    for field in fields_to_score:
        value = data.get(field, "")
        if value:
            parts = re.split(r'[\s-]+', value.upper())
            cleaned_parts = [clean_for_match(p) for p in parts if p]
            for part in cleaned_parts:
                target_words.add(part)
            if len(cleaned_parts) > 1:
                concat = ''.join(cleaned_parts)
                target_words.add(concat)

    logger.info(f"DEBUG: Mots cibles pour le score : {target_words}")

    for page in full_text_annotation.pages:
        for block in page.blocks:
            for paragraph in block.paragraphs:
                for word in paragraph.words:
                    word_text = ''.join(symbol.text for symbol in word.symbols)
                    confidence = word.confidence
                    cleaned_description = clean_for_match(word_text)
                    if cleaned_description and cleaned_description in target_words:
                        logger.info(f"  └─> CORRESPONDANCE TROUVÉE pour '{cleaned_description}'!")
                        relevant_confidences.append(confidence)
    
    final_confidence = sum(relevant_confidences) / len(relevant_confidences) if relevant_confidences else 0.0
    data["confidence_score"] = round(final_confidence, 4)
    logger.info(f"--- Score de confiance des mots pertinents : {data['confidence_score']:.2f} ---")
    
    logger.info(f"--- Données analysées ---\n{data}\n--------------------")

    if data["nationality"] != "Française":
        raise HTTPException(status_code=422, detail="Le document n'a pas pu être confirmé comme un passeport français.")
    if not all([data["passport_number"], data["last_name"], data["first_name"], data["birth_date"], data["expiration_date"]]):
        raise HTTPException(status_code=422, detail="Impossible d'analyser automatiquement tous les détails essentiels du passeport.")

    return data



def extract_passport_data(file_content: bytes, content_type: str) -> list:
    results = []

    if content_type.startswith("image/"):
        logger.info("Traitement en tant que fichier image unique.")
        try:
            extracted_data = _extract_passport_data_from_image_bytes(file_content)
            results.append({"page_number": 1, "data": extracted_data})
        except HTTPException as e:
            results.append({"page_number": 1, "error": e.detail})
        except Exception as e:
            logger.error(f"Erreur inattendue lors du traitement de l'image : {e}")
            results.append({"page_number": 1, "error": "Une erreur serveur inattendue est survenue lors du traitement."})

    elif content_type == "application/pdf":
        logger.info("Traitement en tant que fichier PDF.")
        try:
            pdf_document = fitz.open(stream=file_content, filetype="pdf")
            for page_num in range(len(pdf_document)):
                page_index = page_num + 1
                logger.info(f"--- Traitement de la page PDF {page_index} ---")
                try:
                    page = pdf_document.load_page(page_num)
                    pix = page.get_pixmap(dpi=300)
                    image_bytes = pix.tobytes("png")
                    extracted_data = _extract_passport_data_from_image_bytes(image_bytes)
                    results.append({"page_number": page_index, "data": extracted_data})
                    logger.info(f"Données extraites avec succès de la page {page_index}.")
                except HTTPException as e:
                    logger.warning(f"Échec de l'extraction des données de la page {page_index}: {e.detail}")
                    results.append({"page_number": page_index, "error": e.detail})
                except Exception as e:
                    logger.error(f"Erreur inattendue sur la page {page_index}: {e}")
                    results.append({"page_number": page_index, "error": "Une erreur serveur inattendue est survenue."})
            pdf_document.close()
        except Exception as e:
            logger.error(f"Échec de l'ouverture ou de la lecture du fichier PDF : {e}")
            raise HTTPException(status_code=500, detail=f"Erreur lors de la lecture du fichier PDF : {e}")
    else:
        raise HTTPException(status_code=400, detail=f"Type de fichier non supporté : {content_type}.")

    if not results:
        raise HTTPException(status_code=500, detail="Échec de la production de résultats à partir du fichier téléchargé.")

    return results




# def extract_passport_data(file_path: str, content_type: str) -> list:
#     results = []

#     if content_type.startswith("image/"):
#         logger.info("Processing as a single image file from disk.")
#         try:
#             # --- CHANGED SECTION ---
#             # Read the bytes from the file on disk only when needed
#             with open(file_path, "rb") as f:
#                 image_bytes = f.read()
#             extracted_data = _extract_passport_data_from_image_bytes(image_bytes)
#             # --- END OF CHANGED SECTION ---
#             results.append({"page_number": 1, "data": extracted_data})
#         except HTTPException as e:
#             results.append({"page_number": 1, "error": e.detail})
#         except Exception as e:
#             logger.error(f"Unexpected error while processing image from disk: {e}")
#             results.append({"page_number": 1, "error": "An unexpected server error occurred during processing."})

#     elif content_type == "application/pdf":
#         logger.info("Processing as a PDF file from disk.")
#         try:
#             # --- CHANGED SECTION ---
#             # Best Practice: Open the PDF directly from its file path.
#             # This is highly memory-efficient.
#             pdf_document = fitz.open(file_path)
#             # --- END OF CHANGED SECTION ---
#             for page_num in range(len(pdf_document)):
#                 page_index = page_num + 1
#                 logger.info(f"--- Processing PDF page {page_index} ---")
#                 try:
#                     page = pdf_document.load_page(page_num)
#                     pix = page.get_pixmap(dpi=300)
#                     image_bytes = pix.tobytes("png")
#                     extracted_data = _extract_passport_data_from_image_bytes(image_bytes)
#                     results.append({"page_number": page_index, "data": extracted_data})
#                     logger.info(f"Successfully extracted data from page {page_index}.")
#                 except HTTPException as e:
#                     logger.warning(f"Failed to extract data from page {page_index}: {e.detail}")
#                     results.append({"page_number": page_index, "error": e.detail})
#                 except Exception as e:
#                     logger.error(f"Unexpected error on page {page_index}: {e}")
#                     results.append({"page_number": page_index, "error": "An unexpected server error occurred."})
#             pdf_document.close()
#         except Exception as e:
#             logger.error(f"Failed to open or read the PDF file from disk: {e}")
#             raise HTTPException(status_code=500, detail=f"Error reading PDF file: {e}")
#     else:
#         raise HTTPException(status_code=400, detail=f"Unsupported file type: {content_type}.")

#     if not results:
#         raise HTTPException(status_code=500, detail="Failed to produce any results from the uploaded file.")

#     return results

# # export GOOGLE_APPLICATION_CREDENTIALS="google-credentials.json"

# # echo $GOOGLE_APPLICATION_CREDENTIALS
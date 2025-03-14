#function_app.py

import fitz  # PyMuPDF
import json
import logging
import azure.functions as func
import base64
import traceback
import requests

app = func.FunctionApp()

def process_pdf(pdf_bytes):
    """Splits a PDF into pages and extracts text."""
    try:
        # First check if we have enough data
        if len(pdf_bytes) < 100:
            return None, "PDF data too small to be valid"
            
        # Try to open the PDF with additional error handling
        try:
            pdf_document = fitz.open(stream=pdf_bytes, filetype="pdf")
        except Exception as e:
            logging.error(f"Failed to open PDF: {str(e)}")
            return None, f"Cannot open PDF document: {str(e)}"
        
        total_page_count = len(pdf_document)
        logging.warning(f"Successfully processed PDF with {total_page_count} pages")
        
        # Handle very large documents by limiting pages
        max_pages = min(total_page_count, 300)  # Process up to 300 pages
        
        pages = []
        for page_num in range(max_pages):
            try:
                page = pdf_document.load_page(page_num)
                text = page.get_text("text")
                # Limit text size per page to avoid overloading
                if len(text) > 100000:
                    text = text[:100000] + "... [content truncated]"
                logging.warning(f"Extracted text from page {page_num + 1}, length: {len(text)}")
                pages.append(text)
            except Exception as page_error:
                logging.error(f"Error extracting page {page_num}: {str(page_error)}")
                pages.append(f"[Error extracting page {page_num+1}: {str(page_error)}]")
        
        return pages, None
    except Exception as e:
        error_details = traceback.format_exc()
        logging.error(f"Error processing PDF: {str(e)}\n{error_details}")
        return None, f"Error processing PDF: {str(e)}"

def process_skillset_content(content, record_id):
    """Process content from the skillset."""
    try:
        # Log content type and length for debugging
        logging.warning(f"Processing content of type {type(content)}, length: {len(content) if content else 0}")
        
        # Check if content is a URL/path (from metadata_storage_path)
        if isinstance(content, str) and (content.startswith("http") or content.startswith("https")):
            logging.warning(f"Content appears to be a URL: {content}")
            try:
                # Download the file from the URL
                response = requests.get(content, timeout=30)
                if response.status_code == 200:
                    pdf_bytes = response.content
                    logging.warning(f"Successfully downloaded {len(pdf_bytes)} bytes from URL")
                    return process_pdf(pdf_bytes)
                else:
                    return None, f"Failed to download from URL: status code {response.status_code}"
            except Exception as e:
                logging.error(f"Error downloading from URL: {str(e)}")
                return None, f"Error downloading from URL: {str(e)}"
                
        # Check if content is base64 (typical for Azure AI Search)
        try:
            pdf_bytes = base64.b64decode(content)
            logging.warning(f"Successfully decoded base64, {len(pdf_bytes)} bytes")
            return process_pdf(pdf_bytes)
        except:
            # If not base64 or URL, treat as raw text
            logging.warning(f"Content is not base64 or URL, treating as raw text")
            
            # Just return the content split by newlines or chunks as "pages"
            if content and isinstance(content, str):
                lines = content.split("\n")
                pages = []
                current_page = ""
                for line in lines:
                    current_page += line + "\n"
                    if len(current_page) > 5000:  # Create artificial pages of ~5000 chars
                        pages.append(current_page)
                        current_page = ""
                if current_page:
                    pages.append(current_page)
                logging.warning(f"Split raw text into {len(pages)} pages")
                return pages, None
            else:
                return None, "Invalid or empty content"
                
    except Exception as e:
        error_details = traceback.format_exc()
        logging.error(f"Error processing content: {str(e)}\n{error_details}")
        return None, f"Error processing content: {str(e)}"

@app.route(route="split_pdf", methods=["POST"], auth_level=func.AuthLevel.ANONYMOUS)
def split_pdf(req: func.HttpRequest) -> func.HttpResponse:
    """Azure Function HTTP Trigger to process PDF and return pages."""
    logging.warning("Received request to split PDF")
    
    try:
        # Log headers for debugging
        for header_name, header_value in req.headers.items():
            logging.info(f"Header: {header_name}={header_value}")
            
        # Check if this is a skillset request (JSON) or direct PDF upload
        content_type = req.headers.get('Content-Type', '')
        
        if 'application/json' in content_type:
            # Handle skillset request
            try:
                request_json = req.get_json()
                logging.warning(f"Skillset request received: {json.dumps(request_json)[:500]}...")
            except ValueError:
                logging.error("Invalid JSON in request")
                return func.HttpResponse(
                    json.dumps({"values": [{"recordId": "0", "errors": ["Invalid JSON in request"]}]}),
                    mimetype="application/json",
                    status_code=400
                )
            
            if 'values' in request_json and len(request_json['values']) > 0:
                values = request_json['values']
                record_id = values[0].get('recordId', '0')
                
                # Check if data and content exist
                if 'data' not in values[0]:
                    return create_error_response(record_id, "No data field in request")
                
                content = values[0]['data'].get('content', '')
                if not content:
                    return create_error_response(record_id, "No content provided in request")
                
                # Use the enhanced content processing function
                pages, error = process_skillset_content(content, record_id)
                
                if error:
                    return create_error_response(record_id, error)
                
                # Format response according to skillset expectations
                response = {
                    "values": [
                        {
                            "recordId": record_id,
                            "data": {
                                "pages": pages
                            }
                        }
                    ]
                }
                
                logging.warning("Successfully created skillset response")
                return func.HttpResponse(
                    json.dumps(response),
                    mimetype="application/json"
                )
            else:
                # Ensure response follows required format even for errors
                return func.HttpResponse(
                    json.dumps({
                        "values": [
                            {
                                "recordId": "0",
                                "errors": ["Invalid request format: missing 'values' array"]
                            }
                        ]
                    }),
                    mimetype="application/json",
                    status_code=400
                )
        else:
            # Direct PDF processing
            pdf_bytes = req.get_body()
            logging.warning(f"Received direct PDF with {len(pdf_bytes)} bytes")
            
            if len(pdf_bytes) == 0:
                return func.HttpResponse("No PDF data received in request body.", status_code=400)
            
            pages, error = process_pdf(pdf_bytes)
            
            if error:
                return func.HttpResponse(f"Error: {error}", status_code=500)
            
            # Format response for direct API calls
            result = {
                "pages": [{"page_number": i+1, "content": content} for i, content in enumerate(pages)]
            }
            
            return func.HttpResponse(
                json.dumps(result),
                mimetype="application/json"
            )
    except Exception as e:
        error_details = traceback.format_exc()
        logging.error(f"General error: {str(e)}\n{error_details}")
        
        # Always return response in the format expected by the skill
        return func.HttpResponse(
            json.dumps({
                "values": [
                    {
                        "recordId": "0",
                        "errors": [f"General function error: {str(e)}"]
                    }
                ]
            }),
            mimetype="application/json",
            status_code=500
        )

def create_error_response(record_id, error_message):
    """Creates an error response in the format expected by Azure AI Search skillsets."""
    logging.error(f"Creating error response: {error_message}")
    response = {
        "values": [
            {
                "recordId": record_id,
                "errors": [error_message]
            }
        ]
    }
    return func.HttpResponse(
        json.dumps(response),
        mimetype="application/json"
    )
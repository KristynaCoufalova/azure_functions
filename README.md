cat << 'EOF' > README.md
# Azure Functions PDF Processor for RAG System

This repository contains an Azure Function that processes PDF documents for use in a Retrieval-Augmented Generation (RAG) system. The function splits PDFs into pages, extracts text, and prepares the content for indexing in Azure AI Search.

##  Purpose

This project was created to address a specific limitation in Azure AI Search's built-in skillsets. While Azure AI Search offers various text-splitting capabilities, it doesn't provide a native "chunk by pages" functionality for PDFs. When building RAG systems, maintaining the original page structure of documents is often crucial for:

- **Source attribution** – Allowing the system to reference specific pages where information was found
- **Contextual integrity** – Preserving the natural boundaries of content as they appear in the original document
- **Improved retrieval accuracy** – Treating pages as logical units can improve relevance in certain domains

This custom skill seamlessly integrates with Azure AI Search to enable page-based chunking, allowing each page to be indexed separately while maintaining document relationships through parent-child mappings in the index.

## Features

- **PDF Processing:** Extract text from PDF documents using PyMuPDF  
- **Multiple Input Formats:** Handle direct PDF uploads, base64-encoded content, or URLs  
- **Chunking:** Split large text documents into manageable chunks  
- **Azure AI Search Integration:** Format responses for use with Azure AI Search skillsets  
- **Robust Error Handling:** Comprehensive error catching and reporting  
- **Large Document Support:** Process PDFs up to 300 pages with content size limits  
- **Docker Support:** Containerized deployment option  

## Prerequisites

- Azure subscription  
- Azure Functions runtime  
- Python 3.11+  

## Installation

Clone this repository:

\`\`\`bash
git clone https://github.com/yourusername/azure-functions-pdf-processor.git
cd azure-functions-pdf-processor
\`\`\`

Install dependencies:

\`\`\`bash
pip install -r requirements.txt
\`\`\`

Set up local settings:

\`\`\`bash
cp local.settings.json.example local.settings.json
# Edit local.settings.json with your settings
\`\`\`

## Project Structure

\`\`\`
├── .funcignore            # Files to exclude when deploying
├── .gitignore             # Git ignore file
├── Dockerfile             # For containerized deployment
├── function_app.py        # Main function app entry point
├── host.json              # Function host configuration
├── requirements.txt       # Python dependencies
└── split_pdf/             # PDF splitting function
    ├── __init__.py        # Main function code
    └── function.json      # Function configuration
\`\`\`

## Deployment

### Deploy to Azure Functions

\`\`\`bash
az login
func azure functionapp publish your-function-app-name
\`\`\`

### Deploy using Docker (Optional)

\`\`\`bash
docker build -t pdf-processor .
docker run -p 8080:80 pdf-processor
\`\`\`

Docker deployment may be beneficial in these scenarios:

- When deploying across multiple environments  
- If you experience dependency conflicts with PyMuPDF  
- For more control over the runtime environment  
- When scaling to handle high document processing volumes  

## 📝 Usage & Data Flow

### 1. Direct PDF Processing

Send a PDF file directly to the endpoint:

\`\`\`bash
curl -X POST https://your-function-app.azurewebsites.net/api/split_pdf \\
  -H "Content-Type: application/pdf" \\
  --data-binary @document.pdf
\`\`\`

**Response:**

\`\`\`json
{
  "pages": [
    {"page_number": 1, "content": "Page 1 text content..."},
    {"page_number": 2, "content": "Page 2 text content..."}
  ]
}
\`\`\`

### 2. Azure AI Search Skillset Integration

#### Input Format

\`\`\`json
{
  "values": [
    {
      "recordId": "record1",
      "data": {
        "content": "[PDF CONTENT]"
      }
    }
  ]
}
\`\`\`

The `[PDF CONTENT]` can be:

- A URL pointing to the PDF (e.g., from `metadata_storage_path`)
- Base64-encoded PDF binary data
- Raw text

#### Processing Flow

1. **Content Identification:**
   - If content starts with `http` or `https`, it's treated as a URL
   - Else, try base64 decoding
   - If decoding fails, treat it as raw text

2. **PDF Retrieval and Processing:**
   - URL: use `requests.get()`, pass content to processing
   - Base64: decode with `base64.b64decode()`
   - Raw text: split into artificial 5k character "pages"

3. **PDF Binary Processing:**
   - Use `fitz.open(stream=pdf_bytes, filetype="pdf")`
   - Limit to 300 pages
   - Extract text via `page.get_text("text")`
   - Trim if longer than 100,000 characters

4. **Chunking Strategy:**
   - Each page = one array item
   - Natural page boundaries only (no semantic splitting)

#### Output Format

\`\`\`json
{
  "values": [
    {
      "recordId": "record1",
      "data": {
        "pages": [
          "Full text content from page 1",
          "Full text content from page 2"
        ]
      }
    }
  ]
}
\`\`\`

#### Integration Example

**Web API Skill in skillset:**

\`\`\`json
{
  "@odata.type": "#Microsoft.Skills.Custom.WebApiSkill",
  "description": "Custom PDF page splitting using Azure Function",
  "uri": "https://your-function-app.azurewebsites.net/api/split_pdf",
  "context": "/document",
  "batchSize": 1,
  "inputs": [
    {
      "name": "content",
      "source": "/document/metadata_storage_path"
    }
  ],
  "outputs": [
    {
      "name": "pages",
      "targetName": "pages"
    }
  ]
}
\`\`\`

**Embedding Skill:**

\`\`\`json
{
  "@odata.type": "#Microsoft.Skills.Text.AzureOpenAIEmbeddingSkill",
  "context": "/document/pages/*",
  "inputs": [{"name": "text", "source": "/document/pages/*"}],
  "outputs": [{"name": "embedding", "targetName": "vector"}]
}
\`\`\`

**Index Projection:**

\`\`\`json
{
  "selectors": [{
    "targetIndexName": "your-index",
    "parentKeyFieldName": "parent_id",
    "sourceContext": "/document/pages/*",
    "mappings": [
      {"name": "chunk", "source": "/document/pages/*"},
      {"name": "vector", "source": "/document/pages/*/vector"},
      {"name": "title", "source": "/document/metadata_storage_name"}
    ]
  }]
}
\`\`\`

## 🔌 Integration with Azure AI Search

Use this function as a custom skill in Azure AI Search to:

- Index each page individually with its own embedding vector  
- Maintain document structure via parent-child mapping  
- Return page-specific results for better source attribution  
- Create coherent page-based content chunks  

## 📖 Error Handling

The function provides clear error messages for:

- Invalid PDF input  
- URL fetch failures  
- PyMuPDF exceptions  
- Page-level text extraction errors  

## Performance Considerations

- 300 page processing limit  
- 100,000 character max per page  
- Scale your Function App Plan for high document throughput  

## Security

- Enable authentication for production environments  
- Add API key check or other security measure  

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

This project is licensed under the MIT License – see the [LICENSE](LICENSE) file for details.
EOF

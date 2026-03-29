#!/usr/bin/env python3
"""
Standalone File Upload Test Server

Minimal FastAPI server for testing file upload functionality without full database setup.
"""

import asyncio
import os
import uuid
from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# Import our file parser
from cortex.rag.parsers import parse_file, UnsupportedFileTypeError, FileParsingError

app = FastAPI(title="File Upload Test Server")

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all for testing
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class IngestResponse(BaseModel):
    doc_id: str
    chunks: int
    message: str


class BatchIngestItem(BaseModel):
    doc_id: str
    filename: str
    chunk_count: int


class BatchIngestError(BaseModel):
    filename: str
    error: str


class BatchIngestResponse(BaseModel):
    success_count: int
    error_count: int
    results: list[BatchIngestItem]
    errors: list[BatchIngestError] | None = None


@app.get("/health")
async def health():
    """Health check endpoint"""
    return {"status": "healthy", "message": "Test server running"}


@app.post("/api/v1/projects/{project_uid}/documents", response_model=IngestResponse)
async def upload_document(project_uid: str, file: UploadFile = File(...)):
    """Upload and parse a single document"""
    max_size_mb = 10
    content_bytes = await file.read()

    # Validate size
    if len(content_bytes) > max_size_mb * 1024 * 1024:
        raise HTTPException(
            status_code=413,
            detail=f"File exceeds {max_size_mb}MB limit"
        )

    # Parse file
    try:
        content = await parse_file(
            content_bytes=content_bytes,
            filename=file.filename or "unknown",
            content_type=file.content_type,
        )
    except UnsupportedFileTypeError as e:
        raise HTTPException(status_code=415, detail=str(e))
    except FileParsingError as e:
        raise HTTPException(status_code=422, detail=f"Failed to parse: {str(e)}")

    # Simulate chunking (just count characters / 1000)
    chunk_count = max(1, len(content) // 1000)
    doc_id = f"doc_{uuid.uuid4().hex[:12]}"

    print(f"✅ Parsed {file.filename}: {len(content)} chars, {chunk_count} chunks")

    return IngestResponse(
        doc_id=doc_id,
        chunks=chunk_count,
        message=f"Ingested '{file.filename}' as {chunk_count} chunk(s)"
    )


@app.post("/api/v1/projects/{project_uid}/documents/batch", response_model=BatchIngestResponse)
async def upload_documents_batch(project_uid: str, files: list[UploadFile] = File(...)):
    """Upload multiple documents at once"""
    max_size_mb = 10
    max_batch_size = 10

    if len(files) > max_batch_size:
        raise HTTPException(
            status_code=400,
            detail=f"Maximum {max_batch_size} files per batch"
        )

    if not files:
        raise HTTPException(status_code=400, detail="No files provided")

    results = []
    errors = []

    for file in files:
        try:
            # Validate size
            content_bytes = await file.read()
            if len(content_bytes) > max_size_mb * 1024 * 1024:
                errors.append(BatchIngestError(
                    filename=file.filename or "unknown",
                    error=f"File exceeds {max_size_mb}MB limit"
                ))
                continue

            # Parse file
            try:
                content = await parse_file(
                    content_bytes=content_bytes,
                    filename=file.filename or "unknown",
                    content_type=file.content_type,
                )
            except UnsupportedFileTypeError as e:
                errors.append(BatchIngestError(filename=file.filename or "unknown", error=str(e)))
                continue
            except FileParsingError as e:
                errors.append(BatchIngestError(
                    filename=file.filename or "unknown",
                    error=f"Failed to parse: {str(e)}"
                ))
                continue

            # Success
            chunk_count = max(1, len(content) // 1000)
            doc_id = f"doc_{uuid.uuid4().hex[:12]}"

            results.append(BatchIngestItem(
                doc_id=doc_id,
                filename=file.filename or "unknown",
                chunk_count=chunk_count,
            ))

            print(f"✅ Parsed {file.filename}: {len(content)} chars, {chunk_count} chunks")

        except Exception as e:
            errors.append(BatchIngestError(
                filename=file.filename or "unknown",
                error=f"Unexpected error: {str(e)}"
            ))

    return BatchIngestResponse(
        success_count=len(results),
        error_count=len(errors),
        results=results,
        errors=errors if errors else None
    )


if __name__ == "__main__":
    import uvicorn

    print("\n" + "="*60)
    print("🚀 File Upload Test Server")
    print("="*60)
    print("\nServer starting at: http://localhost:8000")
    print("\nEndpoints:")
    print("  - GET  /health")
    print("  - POST /api/v1/projects/{uid}/documents (single upload)")
    print("  - POST /api/v1/projects/{uid}/documents/batch (batch upload)")
    print("\nSupported formats:")
    print("  PDF, DOCX, Excel, HTML, Markdown, Text")
    print("\nOpen the test page:")
    print("  file:///Users/sgurubelli/aiplatform/cortex-ui/test-file-upload.html")
    print("\n" + "="*60 + "\n")

    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")

"""
CareerCompass — FastAPI Backend Service

Exposes API endpoints to upload student academic plan PDFs and return
structured academic transcript & plan data.

Endpoints:
    - POST /api/transcript/upload : Receives PDF upload, parses & returns structured JSON
    - GET  /api/health            : Service health check
"""

import os
import shutil
from pathlib import Path
from fastapi import FastAPI, File, UploadFile, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from src.modules.transcript_parser import parse_academic_plan, save_extraction

app = FastAPI(
    title="CareerCompass API",
    description="API service for parsing student academic plans, skill gap analysis, and course/job recommendations.",
    version="1.0.0",
)

# Enable CORS for web frontend integration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health_check():
    """Service health check endpoint."""
    return {"status": "ok", "service": "CareerCompass API"}


@app.post("/api/transcript/upload")
async def upload_transcript(
    file: UploadFile = File(...),
    save_output: bool = True
):
    """
    Receive a student academic plan PDF file and extract structured JSON data.

    Args:
        file: Multipart PDF file upload.
        save_output: Whether to save the JSON output file in src/data/extracted/

    Returns:
        JSON response with student profile, requirement categories, course lists, and summary stats.
    """
    # Validate file extension
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid file format. Only PDF files (.pdf) are supported."
        )

    # Save uploaded file to a temporary file for pdfplumber processing
    temp_dir = Path("src/data/temp")
    temp_dir.mkdir(parents=True, exist_ok=True)
    temp_file_path = temp_dir / f"upload_{os.urandom(8).hex()}_{file.filename}"

    try:
        with open(temp_file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        # Parse the academic plan PDF using our parser module
        parsed_result = parse_academic_plan(str(temp_file_path))

        # Save extraction to src/data/extracted if requested
        if save_output:
            extracted_dir = Path("src/data/extracted")
            extracted_dir.mkdir(parents=True, exist_ok=True)
            output_filename = f"{Path(file.filename).stem}.json"
            save_extraction(parsed_result, str(extracted_dir / output_filename))

        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                "success": True,
                "message": "Academic plan parsed successfully.",
                "filename": file.filename,
                "data": parsed_result,
            }
        )

    except FileNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to parse PDF academic plan: {str(e)}"
        )
    finally:
        # Clean up temporary uploaded file
        if temp_file_path.exists():
            try:
                os.remove(temp_file_path)
            except OSError:
                pass


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("src.app:app", host="0.0.0.0", port=8000, reload=True)

import os
import json
from io import BytesIO
from pathlib import Path
from datetime import datetime, timezone

import requests
from dotenv import load_dotenv
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from pypdf import PdfReader
from pymongo import MongoClient
from pymongo.errors import PyMongoError, ConfigurationError


# --------------------------------------------------
# 1. Environment variables
# --------------------------------------------------

ENV_PATH = Path(__file__).resolve().parent / ".env"
load_dotenv(ENV_PATH, override=True)

MONGODB_URI = os.getenv("MONGODB_URI")

print("Env file exists:", ENV_PATH.is_file())
print("Mongo URI loaded:", bool(MONGODB_URI))


# --------------------------------------------------
# 2. MongoDB connection
# --------------------------------------------------

client = None
db = None
candidate_profiles = None

if MONGODB_URI:
    try:
        client = MongoClient(
            MONGODB_URI,
            serverSelectionTimeoutMS=5000
        )

        db = client["ai_job_agent_pyt"]
        candidate_profiles = db["candidate_profiles"]

    except (ConfigurationError, ValueError):
        print("MongoDB URI configuration is invalid.")
        client = None
        db = None
        candidate_profiles = None

# --------------------------------------------------
# 3. FastAPI application
# --------------------------------------------------

app = FastAPI(
    title="AI Job Agent API",
    description="API for resume parsing and AI-powered job matching",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --------------------------------------------------
# 4. AI resume parser
# --------------------------------------------------

def analyze_resume_with_ai(resume_text: str):
    prompt = f"""
You are an expert resume parser and career analyst.

Extract the candidate's information from the resume.
Return a valid JSON object with exactly these fields:

{{
    "name": null,
    "skills": [],
    "experience_years": null,
    "current_role": null,
    "education": [],
    "projects": [],
    "suggested_roles": []
}}

Instructions:
1. Extract technical skills explicitly supported by the resume.
2. Include programming languages, frameworks, databases,
   tools, cloud platforms, operating systems and technologies.
3. Extract the current or most recent job title.
4. Extract education qualifications and institutions.
5. Extract project names.
6. Suggest suitable roles based on actual skills and experience.
7. Estimate experience only when supported by the resume.
8. Never invent skills, qualifications or experience.
9. Use null for unavailable scalar fields and [] for unavailable lists.
10. Return only valid JSON without Markdown fences.

Resume text:
<resume>
{resume_text}
</resume>
"""

    response = requests.post(
        "http://localhost:11434/api/generate",
        json={
            "model": "llama3.2:3b",
            "prompt": prompt,
            "stream": False,
            "format": "json",
        },
        timeout=120,
    )

    response.raise_for_status()

    result = response.json()
    return json.loads(result["response"])


# --------------------------------------------------
# 5. Skill matching request model
# --------------------------------------------------

class SkillsMatchRequest(BaseModel):
    required_skills: list[str]
    having_skills: list[str]


# --------------------------------------------------
# 6. Basic endpoints
# --------------------------------------------------

@app.get("/")
def home():
    return {
        "message": "AI Job Agent API is running",
        "status": "success",
    }


@app.get("/health")
def health_check():
    return {"status": "healthy"}


# --------------------------------------------------
# 7. MongoDB health check
# --------------------------------------------------

@app.get("/db-check")

def check_database():
    if client is None:
        raise HTTPException(
            status_code=500,
            detail="MongoDB URI is missing or invalid."
        )
    try:
        client.admin.command("ping")
        return {
            "status": "success",
            "message": "MongoDB Atlas connected successfully"
        }
    except Exception as e:
        # Diagnostic details appear in your local terminal only.
        print("MongoDB error type:", type(e).__name__)
        print("MongoDB error:", str(e))
        raise HTTPException(
            status_code=503,
            detail="MongoDB connection failed. Check the backend terminal."
        )

# --------------------------------------------------
# 8. Upload, parse and save resume
# --------------------------------------------------

@app.post("/resume/upload")
async def upload_resume(file: UploadFile = File(...)):

    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(
            status_code=400,
            detail="Only PDF files are allowed.",
        )

    content = await file.read()

    if not content.startswith(b"%PDF-"):
        raise HTTPException(
            status_code=400,
            detail="The uploaded file is not a valid PDF.",
        )

    try:
        reader = PdfReader(BytesIO(content))

        resume_text = "\n".join(
            page.extract_text() or ""
            for page in reader.pages
        )

    except Exception:
        raise HTTPException(
            status_code=400,
            detail="Could not read this PDF.",
        )

    if not resume_text.strip():
        raise HTTPException(
            status_code=422,
            detail="No extractable text found. The PDF may be scanned.",
        )

    # Parse the resume using the local Llama model.
    try:
        resume_profile = analyze_resume_with_ai(resume_text)

        if not isinstance(resume_profile, dict):
            raise ValueError("AI response must be a JSON object.")

    except requests.RequestException:
        raise HTTPException(
            status_code=503,
            detail="AI service is unavailable. Please try again later.",
        )

    except (ValueError, KeyError, TypeError):
        raise HTTPException(
            status_code=502,
            detail="AI returned an invalid response.",
        )

    # Save the parsed profile to MongoDB.
    if candidate_profiles is None:
        raise HTTPException(
            status_code=503,
            detail="MongoDB is not configured. Resume profile was not saved.",
        )

    document = {
        "resume_profile": resume_profile,
        "filename": file.filename,
        "page_count": len(reader.pages),
        "uploaded_at": datetime.now(timezone.utc),
    }

    try:
        result = candidate_profiles.insert_one(document)

    except PyMongoError:
        raise HTTPException(
            status_code=503,
            detail="Could not save the resume profile to MongoDB.",
        )

    return {
        "message": "Resume parsed and saved successfully.",
        "profile_id": str(result.inserted_id),
        "filename": file.filename,
        "page_count": len(reader.pages),
        "content_type": file.content_type,
        "resume_profile": resume_profile,
    }


# --------------------------------------------------
# 9. Skill matching helper endpoint
# --------------------------------------------------

@app.post("/jobs/match-skills")
def match_skills(request: SkillsMatchRequest):

    required = {
        skill.strip().casefold()
        for skill in request.required_skills
        if skill.strip()
    }

    having = {
        skill.strip().casefold()
        for skill in request.having_skills
        if skill.strip()
    }

    matched_skills = required & having
    missing_skills = required - having

    match_percentage = (
        len(matched_skills) / len(required) * 100
        if required
        else 0
    )

    return {
        "matched_skills": sorted(matched_skills),
        "missing_skills": sorted(missing_skills),
        "match_percentage": round(match_percentage, 2),
    }

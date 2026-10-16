from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi import UploadFile , File , HTTPException
from pypdf import PdfReader
from io import BytesIO
from pydantic import BaseModel

class skillsMatchRequest(BaseModel) : 
    required_skills : list[str] 
    having_skills : list[str]

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

@app.get("/")
def home():
    return {
        "message": "AI Job Agent API is running",
        "status" : "success",
    }

@app.get("/health")
def health_check():
    return {"status": "healthy"}

# Important: async does not make every line run in parallel. 
# It allows asynchronous operations to yield control while waiting

@app.post("/resume/upload")

async def upload_resume(file : UploadFile  = File(...)) : 
    if not file.filename or not file.filename.lower().endswith(".pdf") : 
        raise HTTPException(
            status_code  = 400  , 
            detail = "Only PDF files are allowed..."
        )
    
    content = await file.read()  

    if not content.startswith(b"%PDF-") : 
        raise HTTPException(
            status_code = 400 , 
            detail = "The uploaded file is not a valid PDF"
        )

    try : 
        reader  = PdfReader(BytesIO(content))
        resume_text = "\n".join(
            page.extract_text() or "" for page in reader.pages
        )

    except Exception  :
        raise HTTPException(
            status_code=400,
            detail="Could not read this PDF"
        )

    if not resume_text.strip() : 
        raise HTTPException(
            status_code= 422,
            detail="No extractable text found. The PDF may be scanned."
        )

    return {
        "message" : "Resume uploaded successfully..." , 
        "filename" : file.filename , 
        "page_count" : len(reader.pages) , 
        "content_type" : file.content_type ,
        "resume_text" : resume_text
    }

@app.post("/jobs/match-skills")
def match_skills(request : skillsMatchRequest) :

    required = {skill.lower() for skill in request.required_skills}
    having   = {skill.lower() for skill in request.having_skills} 

    matched_skills = required & having
    missing_skills = required - having

    if not required : 
        match_percentage = 0 
        
    else :
        match_percentage = (len(matched_skills) / len(required))  * 100 ;

    return {
        "matched_skills" : list(matched_skills) , 
        "missing_skills" : list(missing_skills) , 
        "match_percentage" : match_percentage
    }
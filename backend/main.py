from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi import UploadFile , File , HTTPException
from pypdf import PdfReader
from io import BytesIO
from pydantic import BaseModel
import requests
import json 

def analyze_resume_with_ai(resume_text : str) : 
    prompt = f"""
        You are an expert resume parser and career analyst.
        Read the resume carefully and extract the candidate's information.
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
            1. Extract all technical skills explicitly mentioned in the resume.
            2. Include programming languages, frameworks, databases, tools,
            cloud platforms, operating systems, and relevant technologies.
            3. Extract the candidate's current or most recent job title.
            4. Extract education qualifications and institution names.
            5. Extract project names from the Projects section.
            6. Suggest suitable job roles based on the candidate's actual skills
            and experience. Do not suggest roles based only on unrelated assumptions.
            7. Set experience_years to a number only when the resume supports
            a reasonable estimate. Otherwise use null.
            8. Never invent skills, qualifications, employers, or experience.
            9. If a field cannot be determined, use null for scalar fields
            and [] for list fields.
            10. Return only valid JSON. Do not include Markdown code fences.
        Resume text:
        <resume>
        {resume_text}
        </resume>
    """
    response = requests.post(
        "http://localhost:11434/api/generate" , 
        json = {
            "model": "llama3.2:3b",
            "prompt": prompt,
            "stream": False,
            "format": "json"
        } ,
        timeout = 120
    )
    response.raise_for_status()
    result = response.json()
    return json.loads(result["response"])

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

    try : 
        resume_profile = analyze_resume_with_ai(resume_text)
    
    except requests.RequestException : 
        raise HTTPException(
            status_code = 503 , 
            detail = "Ai service is unavailble .Please try again later"
        )
    
    except (ValueError , KeyError) :
        raise HTTPException(
            status_code=502,
            detail="AI returned an invalid response."
        )
 
    return {
        "message" : "Resume uploaded successfully..." , 
        "filename" : file.filename , 
        "page_count" : len(reader.pages) , 
        "content_type" : file.content_type ,
        "resume_profile" : resume_profile
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

if __name__ == "__main__":
    sample_resume = """
    Ankush Kushwaha
    Software Engineer at TCS
    Skills: Python, React, Node.js, MongoDB
    Education: B.E. Computer Science
    Project: MERN E-Commerce Application
    """
    result = analyze_resume_with_ai(sample_resume)
    print(json.dumps(result, indent=2))
import os
from fastapi import FastAPI, HTTPException, Header
from pydantic import BaseModel
from supabase import create_client, Client
import uvicorn

app = FastAPI(title="Conlenz License Server")

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    print("Warning: SUPABASE_URL and SUPABASE_KEY must be set in the environment.")

class VerifyRequest(BaseModel):
    token: str

@app.post("/verify")
def verify_token(req: VerifyRequest):
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise HTTPException(status_code=500, detail="Server misconfigured (missing Supabase credentials).")
    
    # In production, use your own table name and column names!
    # We assume a table named 'tokens' with 'token' and 'is_active' columns.
    try:
        supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
        response = supabase.table("tokens").select("*").eq("token", req.token).execute()
        
        data = response.data
        if not data:
            return {"valid": False, "message": "Token not found."}
        
        token_record = data[0]
        is_active = token_record.get("is_active", False)
        
        if is_active:
            return {"valid": True, "message": "Paid tier unlocked."}
        else:
            return {"valid": False, "message": "Token is inactive or expired."}
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error checking token: {str(e)}")

@app.get("/health")
def health_check():
    return {"status": "ok"}

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)

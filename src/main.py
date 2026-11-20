"""Main application runner: FastAPI + Telegram Bot + Static Proof Host."""
import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, HTTPException, Request, Security, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, PlainTextResponse, FileResponse
from fastapi.security.api_key import APIKeyHeader
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import List, Optional

from src.config import HOST, PORT, PROOF_DIR, TELEGRAM_BOT_TOKEN, PROJECT_ROOT, REQUIRE_API_KEY
from src.db import init_db, get_task
from src.keys import init_keys_table, validate_api_key, generate_api_key
from src.telegram_bot import create_telegram_app
from src.mcp_server import (
    set_telegram_app, 
    portland_physical_verification,
    portland_storefront_audit, 
    request_custom_physical_task, 
    check_task_status
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("ground_truth.main")

telegram_app = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global telegram_app
    logger.info("Initializing Portland Ground-Truth Pilot...")
    await init_db()
    await init_keys_table()

    # Start Telegram bot if token configured
    if TELEGRAM_BOT_TOKEN and TELEGRAM_BOT_TOKEN != "your_telegram_bot_token_here":
        telegram_app = create_telegram_app()
        set_telegram_app(telegram_app)
        await telegram_app.initialize()
        await telegram_app.start()
        await telegram_app.updater.start_polling()
        logger.info("Telegram Bot polling started.")
    else:
        logger.warning("TELEGRAM_BOT_TOKEN not configured. Running in offline/mock mode.")

    yield

    if telegram_app and telegram_app.updater.running:
        logger.info("Stopping Telegram Bot...")
        await telegram_app.updater.stop()
        await telegram_app.stop()
        await telegram_app.shutdown()

tags_metadata = [
    {
        "name": "Physical Actuation",
        "description": "Real-world ground truth verification endpoints for autonomous agents in Portland, OR.",
    },
    {
        "name": "Task Status",
        "description": "Polling and verification lifecycle retrieval.",
    },
]

app = FastAPI(
    title="GroundTruth Protocol: Node #001 (Portland)",
    description="Physical verification and actuation middleware for autonomous AI agents in Portland, Oregon.",
    version="0.1.0",
    openapi_tags=tags_metadata,
    lifespan=lifespan
)

# Enable CORS for browser agents and sandboxed clients
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve verified proof photos statically
app.mount("/proof", StaticFiles(directory=str(PROOF_DIR)), name="proof")

# API Key security scheme
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

async def verify_api_key(api_key: Optional[str] = Security(api_key_header)):
    """Validates API Key if configured/required, else logs usage for research."""
    if not REQUIRE_API_KEY:
        if api_key:
            await validate_api_key(api_key)
        return True

    if not api_key:
        raise HTTPException(
            status_code=401,
            detail="Missing required X-API-Key header. Request access at tobias@algernontechnology.com"
        )

    is_valid, key_record = await validate_api_key(api_key)
    if not is_valid:
        raise HTTPException(status_code=403, detail="Invalid or revoked API key.")
    return key_record

class PhysicalVerificationRequest(BaseModel):
    location: str
    specific_questions: List[str]
    stated_purpose: Optional[str] = "Physical reality verification"
    client_id: Optional[str] = "rest_client_default"

class StorefrontAuditRequest(BaseModel):
    business_name: str
    address: str
    specific_questions: List[str]
    stated_purpose: Optional[str] = "Commercial ground truth verification"
    client_id: Optional[str] = "rest_client_default"

class CustomTaskRequest(BaseModel):
    location: str
    proposed_action: str
    stated_purpose: str
    client_id: Optional[str] = "rest_client_default"

@app.get("/", response_class=HTMLResponse, tags=["Discovery"])
async def get_root_landing():
    """Root landing page with machine-readable auto-discovery headers."""
    return """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <link rel="alternate" type="text/plain" href="/llms.txt" title="LLMs.txt" />
    <title>GroundTruth Protocol: Node #001 (Portland Metro)</title>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, monospace; max-width: 800px; margin: 40px auto; padding: 20px; line-height: 1.6; background: #06090e; color: #e2e8f0; }
        h1 { color: #38bdf8; border-bottom: 1px solid #1e293b; padding-bottom: 10px; }
        code { background: #0f172a; padding: 2px 6px; border-radius: 4px; color: #38bdf8; }
        a { color: #38bdf8; text-decoration: none; }
        a:hover { text-decoration: underline; }
        .card { background: #0b111a; border: 1px solid #1e293b; padding: 20px; border-radius: 8px; margin: 20px 0; }
        .badge { background: #065f46; color: #34d399; padding: 4px 10px; border-radius: 20px; font-size: 0.85em; font-weight: bold; }
    </style>
</head>
<body>
    <span class="badge">Node #001: Active</span>
    <h1>GroundTruth Protocol: Physical Agency for AI Agents</h1>
    <p>Real-world physical ground truth and actuation bridge connecting autonomous agents to verified human-in-the-loop nodes in the Portland, Oregon metropolitan area.</p>
    
    <div class="card">
        <h3>Agent & Developer Resources</h3>
        <ul>
            <li><strong>Machine-Readable Specification:</strong> <a href="/llms.txt"><code>/llms.txt</code></a></li>
            <li><strong>Interactive API Documentation:</strong> <a href="/docs">Swagger UI (<code>/docs</code>)</a></li>
            <li><strong>OpenAPI Specification:</strong> <a href="/openapi.json"><code>/openapi.json</code></a></li>
            <li><strong>Protocol Health:</strong> <a href="/health"><code>/health</code></a></li>
        </ul>
    </div>
    
    <p><small>&copy; 2026 Algernon Technology &bull; Contact: <a href="mailto:tobias@algernontechnology.com">tobias@algernontechnology.com</a></small></p>
</body>
</html>"""

@app.get("/llms.txt", response_class=PlainTextResponse, tags=["Discovery"])
async def get_llms_txt():
    """Serves machine-readable service instructions for autonomous searching agents."""
    llms_path = PROJECT_ROOT / "llms.txt"
    if llms_path.exists():
        return llms_path.read_text(encoding="utf-8")
    return "Portland Ground Truth Service Active."

@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "service": "portland_ground_truth_pilot",
        "bot_active": bool(telegram_app and telegram_app.updater.running)
    }

@app.post("/v1/dispatch/verify")
async def api_physical_verification(req: PhysicalVerificationRequest, _auth: bool = Depends(verify_api_key)):
    """Dispatches a human field operator to verify any physical location in Portland, OR."""
    res = await portland_physical_verification(
        location=req.location,
        specific_questions=req.specific_questions,
        stated_purpose=req.stated_purpose,
        client_id=req.client_id
    )
    if res.get("status") == "rejected_operator_unavailable":
        raise HTTPException(status_code=503, detail=res.get("error"))
    if res.get("status") == "rejected_by_policy":
        raise HTTPException(status_code=429, detail=res.get("error"))
    return res

@app.post("/v1/dispatch/storefront")
async def api_storefront_audit(req: StorefrontAuditRequest, _auth: bool = Depends(verify_api_key)):
    """Dispatches a human field inspector to verify a commercial storefront in Portland, OR."""
    res = await portland_storefront_audit(
        business_name=req.business_name,
        address=req.address,
        specific_questions=req.specific_questions,
        stated_purpose=req.stated_purpose,
        client_id=req.client_id
    )
    if res.get("status") == "rejected_operator_unavailable":
        raise HTTPException(status_code=503, detail=res.get("error"))
    if res.get("status") == "rejected_by_policy":
        raise HTTPException(status_code=429, detail=res.get("error"))
    return res

@app.post("/v1/dispatch/custom")
async def api_custom_task(req: CustomTaskRequest, _auth: bool = Depends(verify_api_key)):
    """Propose a custom physical task in Portland, OR for operator review."""
    res = await request_custom_physical_task(
        location=req.location,
        proposed_action=req.proposed_action,
        stated_purpose=req.stated_purpose,
        client_id=req.client_id
    )
    if res.get("status") == "rejected_operator_unavailable":
        raise HTTPException(status_code=503, detail=res.get("error"))
    if res.get("status") == "rejected_by_policy":
        raise HTTPException(status_code=429, detail=res.get("error"))
    return res

@app.get("/v1/tasks/{task_id}")
async def api_get_task_status(task_id: str, request: Request):
    """Poll the status of an ongoing or completed task."""
    res = await check_task_status(task_id)
    if res.get("status") == "not_found":
        raise HTTPException(status_code=404, detail="Task not found")

    # Ensure returned photo_url is accessible via current caller host/tunnel
    if res.get("photo_url"):
        filename = Path(res["photo_url"]).name
        proto = request.headers.get("x-forwarded-proto", request.url.scheme)
        host = request.headers.get("x-forwarded-host", request.headers.get("host", request.url.netloc))
        res["photo_url"] = f"{proto}://{host}/proof/{filename}"
    return res

@app.get("/v1/tasks/{task_id}/photo")
async def api_get_task_photo(task_id: str):
    """Directly stream proof photo for a completed task."""
    task = await get_task(task_id)
    if not task or not task.get("photo_url"):
        raise HTTPException(status_code=404, detail="Photo not available for this task.")
    filename = Path(task["photo_url"]).name
    file_path = PROOF_DIR / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Photo file not found on disk.")
    return FileResponse(file_path, media_type="image/jpeg")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("src.main:app", host=HOST, port=PORT, reload=True)

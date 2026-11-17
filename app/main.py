import os
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse

from app.submissions import build_router

app = FastAPI(
    title="CloudPulse",
    description="Document-processing reliability lab",
    version="0.1.0",
)

app.state.failed = False


def require_demo_mode():
    if os.getenv("CLOUDPULSE_DEMO_MODE") != "true":
        raise HTTPException(status_code=404, detail="Not found")


@app.get("/")
def root():
    return {
        "project": "CloudPulse",
        "message": "Service is running",
    }


@app.get("/health")
def health():
    if app.state.failed:
        return JSONResponse(
            status_code=503,
            content={
                "status": "unhealthy",
                "reason": "simulated failure",
            },
        )

    return {"status": "healthy"}


@app.post("/demo/fail")
def simulate_failure():
    require_demo_mode()
    app.state.failed = True
    return {"message": "Simulated failure enabled"}


@app.post("/demo/reset")
def reset_failure():
    require_demo_mode()
    app.state.failed = False
    return {"message": "Simulated failure cleared"}


app.include_router(build_router(Path(".cloudpulse")))
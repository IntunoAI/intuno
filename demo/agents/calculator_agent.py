"""
Simple Calculator Agent

This agent provides basic mathematical operations.
"""

from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI(title="Calculator Agent", version="1.0.0")


class AddRequest(BaseModel):
    a: float
    b: float


class AddResponse(BaseModel):
    result: float


class SubtractRequest(BaseModel):
    a: float
    b: float


class SubtractResponse(BaseModel):
    result: float


class MultiplyRequest(BaseModel):
    a: float
    b: float


class MultiplyResponse(BaseModel):
    result: float


@app.post("/invoke", response_model=dict)
async def invoke(request: dict):
    """
    Invoke endpoint that handles all capabilities.
    The broker will send requests in the format:
    {
        "capability_id": "add",
        "input": {"a": 5, "b": 3}
    }
    """
    capability_id = request.get("capability_id")
    input_data = request.get("input", {})
    
    if capability_id == "add":
        result = input_data.get("a", 0) + input_data.get("b", 0)
        return {"result": result}
    
    elif capability_id == "subtract":
        result = input_data.get("a", 0) - input_data.get("b", 0)
        return {"result": result}
    
    elif capability_id == "multiply":
        result = input_data.get("a", 0) * input_data.get("b", 0)
        return {"result": result}
    
    else:
        return {"error": f"Unknown capability: {capability_id}"}


@app.get("/health")
async def health():
    return {"status": "healthy"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)


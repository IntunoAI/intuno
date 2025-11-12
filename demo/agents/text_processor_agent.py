"""
Simple Text Processor Agent

This agent provides text manipulation capabilities.
"""

from fastapi import FastAPI

app = FastAPI(title="Text Processor Agent", version="1.0.0")


@app.post("/invoke", response_model=dict)
async def invoke(request: dict):
    """
    Invoke endpoint that handles all capabilities.
    The broker will send requests in the format:
    {
        "capability_id": "uppercase",
        "input": {"text": "hello world"}
    }
    """
    capability_id = request.get("capability_id")
    input_data = request.get("input", {})
    
    if capability_id == "uppercase":
        text = input_data.get("text", "")
        return {"result": text.upper()}
    
    elif capability_id == "lowercase":
        text = input_data.get("text", "")
        return {"result": text.lower()}
    
    elif capability_id == "reverse":
        text = input_data.get("text", "")
        return {"result": text[::-1]}
    
    else:
        return {"error": f"Unknown capability: {capability_id}"}


@app.get("/health")
async def health():
    return {"status": "healthy"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8002)


from fastapi import APIRouter
from fastapi.responses import JSONResponse

router = APIRouter(prefix="/health", tags=["Health"])


@router.get("")
async def health_check():
    """
    Gets health status of the application
    :return: JSONResponse
    """
    health_status = {"status": "healthy"}

    return JSONResponse(content=health_status, status_code=200)

from fastapi import APIRouter
from fastapi.responses import JSONResponse

router = APIRouter(prefix="/health")


@router.get("")
async def health_check():
    """
    Gets health status of the application
    :return:
    """
    health_status = {"status": "healthy"}

    return JSONResponse(content=health_status, status_code=200)

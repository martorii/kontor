from typing import Annotated

from fastapi import APIRouter, Depends, UploadFile, status

from kontor.api.dependencies import get_import_service
from kontor.api.schemas import ImportResponse
from kontor.application.import_service import ImportService

router = APIRouter()


@router.post("/imports", status_code=status.HTTP_201_CREATED)
def create_import(
    file: UploadFile,
    service: Annotated[ImportService, Depends(get_import_service)],
) -> ImportResponse:
    result = service.import_file(file.filename or "upload.csv", file.file.read())
    return ImportResponse.from_domain(result)

"""Dataset summary and atomic import of the starter ZIP archive."""

from fastapi import APIRouter, HTTPException, UploadFile

from backend.api.dependencies import DbSession
from backend.services.analytics import analysis_write, run_analysis, summary
from backend.services.dataset_import import MAX_UPLOAD, import_archive

router = APIRouter(prefix="/dataset", tags=["dataset"])


@router.get("")
def get_dataset(session: DbSession) -> dict:
    return summary(session)


@router.post("/import", status_code=201)
def upload_dataset(file: UploadFile, session: DbSession) -> dict:
    content = file.file.read(MAX_UPLOAD + 1)
    if len(content) > MAX_UPLOAD:
        raise HTTPException(413, "Архив должен быть не больше 30 МБ.")
    with analysis_write(session):
        import_archive(session, content)
        result = run_analysis(session)
        session.commit()
        return result

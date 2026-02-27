from fastapi import APIRouter, UploadFile, File, Form
from app.services.vision_adapter import answer_image_question
from app.services.barcode_service import scan_barcode

router = APIRouter(prefix="/image", tags=["image"])


@router.post("/qa")
async def image_qa(file: UploadFile = File(...), question: str = Form(...)):
    data = await file.read()
    return {"answer": answer_image_question(data, question)}


@router.post("/barcode")
async def image_barcode(file: UploadFile = File(...)):
    data = await file.read()
    return scan_barcode(data)

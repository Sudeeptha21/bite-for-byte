from io import BytesIO
from PIL import Image


try:
    from pyzbar.pyzbar import decode as pyzbar_decode
except Exception:
    pyzbar_decode = None

try:
    import cv2
    import numpy as np
except Exception:
    cv2 = None
    np = None


def barcode_runtime_info() -> dict:
    return {
        "pyzbar_available": pyzbar_decode is not None,
        "opencv_available": cv2 is not None and np is not None,
        "opencv_version": getattr(cv2, "__version__", None),
    }


def _decode_with_pyzbar(image: Image.Image) -> list[dict]:
    if not pyzbar_decode:
        return []

    decoded = pyzbar_decode(image)
    codes = []
    for item in decoded:
        value = item.data.decode("utf-8", errors="replace")
        code_type = item.type
        codes.append({"value": value, "type": code_type})
    return codes


def _decode_qr_with_opencv(image_bytes: bytes) -> list[dict]:
    if cv2 is None or np is None:
        return []

    np_arr = np.frombuffer(image_bytes, np.uint8)
    frame = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
    if frame is None:
        return []

    detector = cv2.QRCodeDetector()
    text, _, _ = detector.detectAndDecode(frame)
    if text:
        return [{"value": text, "type": "QRCODE"}]

    return []


def scan_barcode(image_bytes: bytes) -> dict:
    try:
        image = Image.open(BytesIO(image_bytes))
    except Exception as exc:
        return {"status": "error", "message": f"Invalid image: {exc}", "codes": []}

    try:
        codes = _decode_with_pyzbar(image)
        if codes:
            return {"status": "ok", "codes": codes, "decoder": "pyzbar"}

        qr_codes = _decode_qr_with_opencv(image_bytes)
        if qr_codes:
            return {
                "status": "ok",
                "codes": qr_codes,
                "decoder": "opencv_qr_fallback",
                "message": "zbar runtime missing; QR fallback used",
            }

        if pyzbar_decode is None:
            return {
                "status": "error",
                "message": "zbar runtime missing. Install zbar for UPC/EAN/CODE128 support.",
                "codes": [],
            }

        return {"status": "not_found", "message": "No barcode detected", "codes": []}
    except Exception as exc:
        return {"status": "error", "message": str(exc), "codes": []}

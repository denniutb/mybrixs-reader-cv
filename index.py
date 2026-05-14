from __future__ import annotations

import base64
import os
import re
import time
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import cv2
import numpy as np
import requests
from flask import Flask, jsonify, render_template, request


app = Flask(__name__)

BRIX_MIN = 0.0
BRIX_MAX = 32.0
BRIX_STEP = 0.2

# Validated non-linear calibration from the MyBrixS computer-vision prototype.
# Maps boundary row y in the aligned reference coordinate system to % Brix.
CAL_A = -4.37964177e-06
CAL_B = -1.55056894e-02
CAL_C = 35.4113679

REFERENCE_IMAGE_PATH = (
    Path(__file__).resolve().parent
    / "assets"
    / "calibration_reference_10_2_brix.jpg"
)

MAX_DECODED_IMAGE_BYTES = 3 * 1024 * 1024


class ScanError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def clean_batch_id(batch_id: Any) -> str:
    raw = str(batch_id or "scan").strip()
    raw = re.sub(r"[^a-zA-Z0-9_-]+", "_", raw)
    raw = raw.strip("_")
    return (raw[:60] or "scan")


def decode_image_payload(image_payload: Any) -> Tuple[np.ndarray, bytes]:
    if not isinstance(image_payload, str) or not image_payload.strip():
        raise ScanError("Image payload is required.", 400)

    payload = image_payload.strip()

    # Accept either raw base64 or a data URL.
    if payload.startswith("data:"):
        match = re.match(r"^data:image/[a-zA-Z0-9.+-]+;base64,(.+)$", payload, re.S)
        if not match:
            raise ScanError("Image data URL is not valid.", 400)
        payload = match.group(1)

    payload = re.sub(r"\s+", "", payload)

    try:
        image_bytes = base64.b64decode(payload, validate=True)
    except Exception as exc:
        raise ScanError("Image base64 could not be decoded.", 400) from exc

    if not image_bytes:
        raise ScanError("Decoded image is empty.", 400)

    if len(image_bytes) > MAX_DECODED_IMAGE_BYTES:
        raise ScanError(
            "Image is too large. Please retry; the browser normally compresses it automatically.",
            413,
        )

    arr = np.frombuffer(image_bytes, dtype=np.uint8)
    image = cv2.imdecode(arr, cv2.IMREAD_COLOR)

    if image is None or image.size == 0:
        raise ScanError("Image could not be interpreted as a valid photograph.", 400)

    return image, image_bytes


def load_reference_image() -> np.ndarray:
    reference = cv2.imread(str(REFERENCE_IMAGE_PATH), cv2.IMREAD_COLOR)
    if reference is None or reference.size == 0:
        raise ScanError("MyBrixS calibration reference image is missing.", 500)
    return reference


def detect_scale_x(img: np.ndarray) -> int:
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 50, 150)
    colsum = edges.sum(axis=0).astype(np.float32)

    if colsum.size == 0:
        raise ScanError("Could not locate the refractometer scale.", 422)

    window_width = min(80, max(20, img.shape[1] // 8))
    conv = np.convolve(colsum, np.ones(window_width, dtype=np.float32), mode="same")

    return int(np.argmax(conv))


def extract_scale_crop(img: np.ndarray, target_width: int = 1000) -> Tuple[np.ndarray, int, int]:
    scale_x = detect_scale_x(img)
    _, width = img.shape[:2]
    crop_width = min(target_width, width)

    x1 = max(0, scale_x - crop_width // 2)
    x2 = min(width, x1 + crop_width)

    if x2 - x1 < crop_width:
        x1 = max(0, x2 - crop_width)

    crop = img[:, x1:x2].copy()

    if crop.size == 0:
        raise ScanError("Could not crop the refractometer scale area.", 422)

    return crop, x1, scale_x


def align_to_reference(
    moving_crop: np.ndarray,
    reference_crop: np.ndarray,
) -> Tuple[np.ndarray, int, int]:
    moving_gray = cv2.cvtColor(moving_crop, cv2.COLOR_BGR2GRAY)
    reference_gray = cv2.cvtColor(reference_crop, cv2.COLOR_BGR2GRAY)

    orb = cv2.ORB_create(
        nfeatures=4000,
        scaleFactor=1.2,
        nlevels=8,
        edgeThreshold=31,
        patchSize=31,
    )

    kp_moving, des_moving = orb.detectAndCompute(moving_gray, None)
    kp_reference, des_reference = orb.detectAndCompute(reference_gray, None)

    if des_moving is None or des_reference is None:
        raise ScanError("The scale was not clear enough to align. Please retake the image.", 422)

    matcher = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=False)
    matches = matcher.knnMatch(des_moving, des_reference, k=2)

    good_matches = []
    for pair in matches:
        if len(pair) < 2:
            continue
        first, second = pair
        if first.distance < 0.75 * second.distance:
            good_matches.append(first)

    if len(good_matches) < 10:
        raise ScanError(
            "Too few scale features were detected. Please capture the refractometer scale more centrally.",
            422,
        )

    src_pts = np.float32([kp_moving[m.queryIdx].pt for m in good_matches]).reshape(-1, 1, 2)
    dst_pts = np.float32([kp_reference[m.trainIdx].pt for m in good_matches]).reshape(-1, 1, 2)

    homography, mask = cv2.findHomography(src_pts, dst_pts, cv2.RANSAC, 5.0)

    if homography is None:
        raise ScanError("Image alignment failed. Please retake the image.", 422)

    aligned = cv2.warpPerspective(
        moving_crop,
        homography,
        (reference_crop.shape[1], reference_crop.shape[0]),
    )

    inliers = int(mask.sum()) if mask is not None else 0
    return aligned, inliers, len(good_matches)


def detect_boundary_y(aligned_img: np.ndarray, scale_x_ref: int) -> Tuple[int, float]:
    height, width = aligned_img.shape[:2]

    bands = []
    for offset_left, offset_right in [(-380, -120), (120, 380)]:
        x1 = max(0, scale_x_ref + offset_left)
        x2 = min(width, scale_x_ref + offset_right)
        if x2 > x1:
            bands.append(aligned_img[:, x1:x2])

    if not bands:
        raise ScanError("Boundary detection bands could not be formed.", 422)

    arr = np.concatenate(bands, axis=1)

    gray = cv2.cvtColor(arr, cv2.COLOR_BGR2GRAY).astype(np.float32)
    blue_minus_red = arr[:, :, 0].astype(np.float32) - arr[:, :, 2].astype(np.float32)

    gray_profile = gray.mean(axis=1)
    colour_profile = blue_minus_red.mean(axis=1)

    gray_smooth = cv2.GaussianBlur(gray_profile.reshape(-1, 1), (1, 31), 0).ravel()
    colour_smooth = cv2.GaussianBlur(colour_profile.reshape(-1, 1), (1, 31), 0).ravel()

    gray_grad = np.gradient(gray_smooth)
    colour_grad = np.gradient(colour_smooth)

    positive_brightness_jump = np.maximum(gray_grad, 0)
    negative_blue_jump = np.maximum(-colour_grad, 0)

    bright_norm = np.percentile(positive_brightness_jump, 99.5) + 1e-6
    blue_norm = np.percentile(negative_blue_jump, 99.5) + 1e-6

    score = (positive_brightness_jump / bright_norm) * (negative_blue_jump / blue_norm)

    boundary_y = int(np.argmax(score))
    boundary_score = float(score[boundary_y])

    if boundary_y <= 0 or boundary_y >= height - 1:
        raise ScanError("The blue-white boundary could not be located reliably.", 422)

    return boundary_y, boundary_score


def brix_from_boundary_y(boundary_y: int) -> Tuple[float, float]:
    raw_brix = CAL_A * (boundary_y ** 2) + CAL_B * boundary_y + CAL_C
    raw_brix = max(BRIX_MIN, min(BRIX_MAX, float(raw_brix)))

    rounded_brix = round(raw_brix / BRIX_STEP) * BRIX_STEP
    rounded_brix = round(max(BRIX_MIN, min(BRIX_MAX, rounded_brix)), 1)

    return rounded_brix, raw_brix


def classify_confidence(inliers: int, good_matches: int, boundary_score: float) -> str:
    if inliers >= 100 and good_matches >= 150 and boundary_score >= 0.25:
        return "high"
    if inliers >= 50 and good_matches >= 80 and boundary_score >= 0.10:
        return "medium"
    return "low"


def build_notes(confidence: str) -> str:
    if confidence == "high":
        return "Boundary and scale were detected clearly."
    if confidence == "medium":
        return "Reading completed; image quality or alignment was moderate."
    return "Reading completed, but recapture is recommended for stronger confidence."


def analyze_brix(image: np.ndarray) -> Dict[str, Any]:
    reference = load_reference_image()

    reference_crop, _, _ = extract_scale_crop(reference, target_width=1000)
    reference_scale_x = detect_scale_x(reference_crop)

    moving_crop, _, _ = extract_scale_crop(image, target_width=1000)
    aligned, inliers, good_matches = align_to_reference(moving_crop, reference_crop)

    boundary_y, boundary_score = detect_boundary_y(aligned, reference_scale_x)
    brix, raw_brix = brix_from_boundary_y(boundary_y)
    confidence = classify_confidence(inliers, good_matches, boundary_score)

    return {
        "brix": brix,
        "raw_brix": raw_brix,
        "confidence": confidence,
        "boundary_y": boundary_y,
        "inliers": inliers,
        "good_matches": good_matches,
        "boundary_score": boundary_score,
        "notes": build_notes(confidence),
    }


def supabase_configured() -> bool:
    return bool(os.environ.get("SUPABASE_URL")) and bool(os.environ.get("SUPABASE_SERVICE_KEY"))


def supabase_values() -> Tuple[str, str]:
    return os.environ.get("SUPABASE_URL", "").rstrip("/"), os.environ.get("SUPABASE_SERVICE_KEY", "")


def upload_image_to_supabase(image_bytes: bytes, batch_id: Any) -> Optional[str]:
    if not supabase_configured():
        return None

    supabase_url, service_key = supabase_values()
    filename = f"{int(time.time() * 1000)}_{clean_batch_id(batch_id)}.jpg"
    storage_url = f"{supabase_url}/storage/v1/object/mybrixs-images/{filename}"

    response = requests.post(
        storage_url,
        headers={
            "Authorization": f"Bearer {service_key}",
            "apikey": service_key,
            "Content-Type": "image/jpeg",
        },
        data=image_bytes,
        timeout=30,
    )

    if not response.ok:
        raise ScanError(
            f"Cloud image saving failed: {response.status_code} {response.text[:160]}",
            500,
        )

    return f"{supabase_url}/storage/v1/object/public/mybrixs-images/{filename}"


def insert_reading_to_supabase(
    *,
    payload: Dict[str, Any],
    reading: Dict[str, Any],
    image_url: Optional[str],
    boundary_position: str,
) -> None:
    if not supabase_configured():
        return

    supabase_url, service_key = supabase_values()
    insert_url = f"{supabase_url}/rest/v1/readings"

    body = {
        "fruit_type": payload.get("fruit_type") or "unspecified",
        "batch_id": payload.get("batch_id") or None,
        "brix": reading["brix"],
        "confidence": reading["confidence"],
        "boundary_position": boundary_position,
        "notes": reading["notes"],
        "latitude": payload.get("latitude") if payload.get("latitude") is not None else None,
        "longitude": payload.get("longitude") if payload.get("longitude") is not None else None,
        "image_url": image_url,
        "farmer_note": payload.get("farmer_note") or None,
    }

    response = requests.post(
        insert_url,
        headers={
            "Authorization": f"Bearer {service_key}",
            "apikey": service_key,
            "Content-Type": "application/json",
            "Prefer": "return=minimal",
        },
        json=body,
        timeout=30,
    )

    if not response.ok:
        raise ScanError(
            f"Cloud reading save failed: {response.status_code} {response.text[:160]}",
            500,
        )


@app.get("/")
def home() -> Any:
    return render_template("index.html")


@app.get("/api/health")
def health() -> Any:
    return jsonify(
        {
            "ok": True,
            "service": "mybrixs-standalone-webapp",
            "reference_image_present": REFERENCE_IMAGE_PATH.exists(),
            "supabase_configured": supabase_configured(),
        }
    )


@app.post("/api/scan")
def scan() -> Any:
    try:
        payload = request.get_json(silent=True) or {}
        image, image_bytes = decode_image_payload(payload.get("image"))

        reading = analyze_brix(image)

        boundary_position = (
            f"brix={reading['brix']} [cv-prototype] | "
            f"boundary_row={reading['boundary_y']} | "
            f"raw={reading['raw_brix']:.3f} | "
            f"inliers={reading['inliers']} | "
            f"matches={reading['good_matches']} | "
            f"boundary_score={reading['boundary_score']:.3f}"
        )

        image_url = upload_image_to_supabase(image_bytes, payload.get("batch_id"))

        insert_reading_to_supabase(
            payload=payload,
            reading=reading,
            image_url=image_url,
            boundary_position=boundary_position,
        )

        return jsonify(
            {
                "brix": reading["brix"],
                "confidence": reading["confidence"],
                "boundary_position": boundary_position,
                "notes": reading["notes"],
                "image_url": image_url,
            }
        )

    except ScanError as exc:
        return jsonify({"error": exc.message}), exc.status_code
    except Exception as exc:
        app.logger.exception("Unexpected MyBrixS scan failure")
        return jsonify({"error": str(exc) or "Scan failed"}), 500


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5328, debug=True)

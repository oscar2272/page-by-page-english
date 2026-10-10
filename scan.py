"""Conservative, lossless-of-content worksheet reading preview.

The original upload remains untouched. A full-page quadrilateral is rectified only
when all four paper edges are visible; otherwise the entire image is fitted to A4.
"""

from __future__ import annotations

import cv2
import numpy as np

A4_WIDTH = 1654
A4_HEIGHT = 2339


def _order_corners(points: np.ndarray) -> np.ndarray:
    points = points.reshape(4, 2).astype(np.float32)
    sums = points.sum(axis=1)
    differences = np.diff(points, axis=1).ravel()
    return np.array([points[np.argmin(sums)], points[np.argmin(differences)],
                     points[np.argmax(sums)], points[np.argmax(differences)]], dtype=np.float32)


def _paper_quad(image: np.ndarray) -> np.ndarray | None:
    height, width = image.shape[:2]
    scale = min(1.0, 1000 / max(width, height))
    small = cv2.resize(image, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    edges = cv2.Canny(blurred, 45, 140)
    contours, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    area = small.shape[0] * small.shape[1]
    for contour in sorted(contours, key=cv2.contourArea, reverse=True)[:20]:
        if cv2.contourArea(contour) < area * 0.55:
            continue
        perimeter = cv2.arcLength(contour, True)
        polygon = cv2.approxPolyDP(contour, perimeter * 0.025, True)
        if len(polygon) != 4 or not cv2.isContourConvex(polygon):
            continue
        corners = _order_corners(polygon) / scale
        # A cut-off edge is common in phone photos. Never crop such a page.
        if np.any(corners[:, 0] < width * 0.01) or np.any(corners[:, 0] > width * 0.99):
            continue
        if np.any(corners[:, 1] < height * 0.01) or np.any(corners[:, 1] > height * 0.99):
            continue
        top = np.linalg.norm(corners[1] - corners[0])
        bottom = np.linalg.norm(corners[2] - corners[3])
        left = np.linalg.norm(corners[3] - corners[0])
        right = np.linalg.norm(corners[2] - corners[1])
        ratio = max(top, bottom) / max(left, right)
        if 0.55 <= ratio <= 0.9:
            return corners
    return None


def _estimated_page_quad(image: np.ndarray) -> np.ndarray:
    """Use the complete capture when a distinct paper outline cannot be traced."""
    height, width = image.shape[:2]
    return np.array([[0, 0], [width - 1, 0], [width - 1, height - 1],
                     [0, height - 1]], dtype=np.float32)


def make_a4_preview(jpeg: bytes) -> tuple[bytes, str]:
    image = cv2.imdecode(np.frombuffer(jpeg, dtype=np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError("사진을 읽을 수 없습니다.")
    quad = _paper_quad(image)
    mode = "rectified" if quad is not None else "estimated"
    if quad is None:
        quad = _estimated_page_quad(image)
    target = np.array([[0, 0], [A4_WIDTH - 1, 0], [A4_WIDTH - 1, A4_HEIGHT - 1],
                       [0, A4_HEIGHT - 1]], dtype=np.float32)
    image = cv2.warpPerspective(image, cv2.getPerspectiveTransform(quad, target),
                                (A4_WIDTH, A4_HEIGHT), flags=cv2.INTER_CUBIC,
                                borderMode=cv2.BORDER_CONSTANT, borderValue=(255, 255, 255))
    # Flatten uneven lighting while retaining some of the original colored pencil.
    background = cv2.GaussianBlur(image, (0, 0), 40)
    flattened = cv2.divide(image, background, scale=255)
    image = cv2.addWeighted(image, 0.25, flattened, 0.75, 0)
    image = cv2.addWeighted(image, 1.12, cv2.GaussianBlur(image, (0, 0), 1.1), -0.12, 0)
    success, encoded = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, 89])
    if not success:
        raise ValueError("읽기용 페이지를 만들 수 없습니다.")
    return encoded.tobytes(), mode

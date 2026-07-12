"""
Pixabay APIから縦型背景動画を取得するモジュール。
APIキーなしの場合はグラデーション背景を自動生成する。
"""

import logging
import os
import random
from pathlib import Path

import numpy as np
import requests

logger = logging.getLogger(__name__)

PIXABAY_API = "https://pixabay.com/api/videos/"

SEARCH_KEYWORDS = [
    "skincare woman",
    "morning routine",
    "face massage beauty",
    "wellness lifestyle woman",
    "beauty routine",
]

CACHE_DIR = Path(__file__).parent / "video_cache"
CACHE_DIR.mkdir(exist_ok=True)

# グラデーション背景のカラーパレット（暖色・落ち着き系）
GRADIENT_PALETTES = [
    ((255, 200, 200), (200, 150, 200)),  # ピンク→パープル
    ((255, 220, 180), (220, 180, 220)),  # オレンジ→ラベンダー
    ((180, 220, 255), (200, 180, 240)),  # ブルー→パープル
    ((200, 240, 220), (180, 220, 255)),  # ミント→ブルー
]


def _make_gradient_video(output_path: Path, duration: int = 90) -> Path:
    """グラデーション背景動画をMoviePyで生成する（APIキー不要）"""
    from moviepy.editor import ColorClip, VideoClip
    from PIL import Image

    palette = random.choice(GRADIENT_PALETTES)
    c1, c2 = palette
    width, height = 1080, 1920

    def make_frame(t: float):
        img = Image.new("RGB", (width, height))
        pixels = img.load()
        for y in range(height):
            ratio = y / height
            r = int(c1[0] * (1 - ratio) + c2[0] * ratio)
            g = int(c1[1] * (1 - ratio) + c2[1] * ratio)
            b = int(c1[2] * (1 - ratio) + c2[2] * ratio)
            for x in range(width):
                pixels[x, y] = (r, g, b)
        return np.array(img)

    clip = VideoClip(make_frame, duration=duration)
    clip.write_videofile(str(output_path), fps=1, codec="libx264", logger=None)
    logger.info("グラデーション背景生成: %s", output_path)
    return output_path


def fetch_background_video(keyword: str | None = None) -> Path:
    """
    Pixabay APIから背景動画を取得。
    APIキーがない場合はグラデーション背景を自動生成して返す。
    """
    api_key = os.environ.get("PIXABAY_API_KEY", "")

    if not api_key:
        logger.info("PIXABAY_API_KEY 未設定 → グラデーション背景を使用")
        fallback = CACHE_DIR / "gradient_bg.mp4"
        if not fallback.exists():
            _make_gradient_video(fallback)
        return fallback

    query = keyword or random.choice(SEARCH_KEYWORDS)
    logger.info("Pixabay検索: %s", query)

    resp = requests.get(
        PIXABAY_API,
        params={
            "key": api_key,
            "q": query,
            "video_type": "film",
            "per_page": 10,
            "safesearch": "true",
        },
        timeout=15,
    )
    resp.raise_for_status()
    hits = resp.json().get("hits", [])

    if not hits:
        logger.warning("動画が見つからなかったのでグラデーション背景を使用")
        fallback = CACHE_DIR / "gradient_bg.mp4"
        if not fallback.exists():
            _make_gradient_video(fallback)
        return fallback

    hit = random.choice(hits)
    videos = hit.get("videos", {})
    # medium > small > tiny の優先順
    for size in ("medium", "small", "tiny"):
        if size in videos:
            video_url = videos[size]["url"]
            video_id = hit["id"]
            break
    else:
        raise RuntimeError("動画URLが取得できませんでした")

    cache_path = CACHE_DIR / f"pixabay_{video_id}.mp4"
    if cache_path.exists():
        logger.info("キャッシュから使用: %s", cache_path)
        return cache_path

    logger.info("動画ダウンロード中: %s", video_url)
    with requests.get(video_url, stream=True, timeout=60) as r:
        r.raise_for_status()
        with open(cache_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)

    logger.info("ダウンロード完了: %s", cache_path)
    return cache_path

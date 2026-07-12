"""
台本からTikTok縦型動画（9:16）を自動生成するモジュール。
構成: 背景動画(Pexels) + 半透明テキストボックス + 字幕スクロール + BGM
"""

import logging
import textwrap
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

# Pillow 10+ 互換パッチ
if not hasattr(Image, "ANTIALIAS"):
    Image.ANTIALIAS = Image.LANCZOS
from moviepy.editor import (
    VideoFileClip,
    ImageClip,
    CompositeVideoClip,
    AudioFileClip,
    concatenate_videoclips,
    ColorClip,
)

from .script_generator import TikTokScript

logger = logging.getLogger(__name__)

# 動画サイズ（TikTok縦型）
WIDTH, HEIGHT = 1080, 1920
FPS = 30

# フォントパス（Windows標準）
FONT_PATHS = [
    "C:/Windows/Fonts/YuGothM.ttc",   # 游ゴシック Medium
    "C:/Windows/Fonts/meiryo.ttc",    # メイリオ
    "C:/Windows/Fonts/msgothic.ttc",  # MSゴシック（フォールバック）
]

OUTPUT_DIR = Path(__file__).parent / "videos"
OUTPUT_DIR.mkdir(exist_ok=True)


def _find_font(size: int) -> ImageFont.FreeTypeFont:
    for path in FONT_PATHS:
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def _make_text_frame(
    lines: list[str],
    width: int = WIDTH,
    height: int = HEIGHT,
    font_size: int = 52,
    bg_alpha: int = 160,
) -> np.ndarray:
    """テキストオーバーレイ画像をRGBA ndarrayで返す"""
    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    font = _find_font(font_size)
    font_small = _find_font(38)

    # 半透明の黒ボックス（下部3分の2）
    box_top = height // 3
    overlay = Image.new("RGBA", (width, height - box_top), (0, 0, 0, bg_alpha))
    img.paste(overlay, (0, box_top), overlay)

    # テキストを描画
    y = box_top + 60
    for i, line in enumerate(lines):
        wrapped = textwrap.wrap(line, width=18) if len(line) > 18 else [line]
        for wline in wrapped:
            # 白テキスト＋黒縁取り（視認性UP）
            for dx, dy in [(-2, -2), (2, -2), (-2, 2), (2, 2)]:
                draw.text((width // 2 + dx, y + dy), wline, font=font, fill=(0, 0, 0, 255), anchor="mm")
            draw.text((width // 2, y), wline, font=font, fill=(255, 255, 255, 255), anchor="mm")
            y += font_size + 12

        y += 20  # 段落間スペース

    return np.array(img)


def _split_script_to_segments(script: TikTokScript) -> list[tuple[list[str], float]]:
    """
    台本を字幕セグメントに分割する。
    returns: [(lines, duration_seconds), ...]
    """
    segments = []

    # フック（3秒）
    hook_lines = textwrap.wrap(script.hook, width=20)
    segments.append((hook_lines, 4.0))

    # 本編を段落ごとに分割
    paragraphs = [p.strip() for p in script.body.split("\n") if p.strip()]
    per_para = max(3.0, (60.0 - 4.0) / max(len(paragraphs), 1))
    for para in paragraphs:
        lines = textwrap.wrap(para, width=20)
        segments.append((lines, per_para))

    # CTA（3秒）
    cta_lines = textwrap.wrap(script.cta, width=20)
    segments.append((cta_lines, 4.0))

    return segments


def create_video(
    script: TikTokScript,
    bg_video_path: Path,
    bgm_path: Path | None = None,
    output_filename: str | None = None,
) -> Path:
    """
    台本と背景動画からTikTok動画を生成してMP4パスを返す。
    """
    logger.info("動画生成開始: %s", script.title)

    segments = _split_script_to_segments(script)
    total_duration = sum(d for _, d in segments)

    # 背景動画を読み込み・リサイズ・ループ
    bg = VideoFileClip(str(bg_video_path), audio=False)
    bg = bg.resize(height=HEIGHT)
    # 横幅が足りない場合はクロップ
    if bg.w < WIDTH:
        bg = bg.resize(width=WIDTH)
    bg = bg.crop(x_center=bg.w / 2, y_center=bg.h / 2, width=WIDTH, height=HEIGHT)

    # 尺が足りない場合はループ
    if bg.duration < total_duration:
        loops = int(np.ceil(total_duration / bg.duration))
        from moviepy.editor import concatenate_videoclips
        bg = concatenate_videoclips([bg] * loops)
    bg = bg.subclip(0, total_duration)

    # テキストオーバーレイクリップを生成
    text_clips = []
    t = 0.0
    for lines, duration in segments:
        if not lines:
            t += duration
            continue
        frame = _make_text_frame(lines)
        clip = (
            ImageClip(frame, ismask=False)
            .set_start(t)
            .set_duration(duration)
            .set_opacity(1.0)
            .crossfadein(0.3)
            .crossfadeout(0.3)
        )
        text_clips.append(clip)
        t += duration

    # 合成
    final = CompositeVideoClip([bg] + text_clips, size=(WIDTH, HEIGHT))
    final = final.set_duration(total_duration)

    # BGM追加
    if bgm_path and Path(bgm_path).exists():
        bgm = AudioFileClip(str(bgm_path)).volumex(0.3)
        if bgm.duration < total_duration:
            from moviepy.editor import afx
            bgm = bgm.audio_loop(duration=total_duration)
        bgm = bgm.subclip(0, total_duration)
        final = final.set_audio(bgm)

    # 出力
    name = output_filename or f"{script.title[:20].replace(' ', '_')}.mp4"
    output_path = OUTPUT_DIR / name
    final.write_videofile(
        str(output_path),
        fps=FPS,
        codec="libx264",
        audio_codec="aac",
        temp_audiofile=str(OUTPUT_DIR / "temp_audio.m4a"),
        remove_temp=True,
        logger=None,
    )

    logger.info("動画生成完了: %s", output_path)
    return output_path

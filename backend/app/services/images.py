"""图片处理：上传压缩 + 占位图生成。

为什么不用前端压缩：手机端 canvas 压缩在不同浏览器差异大，
放到服务端用 Pillow 统一处理，行为可预期，也顺便纠正手机拍照的 EXIF 旋转。
"""

from __future__ import annotations

import hashlib
import io
import math
import uuid
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps

from ..config import settings

# ---------------------------------------------------------------------------
# 字体
# ---------------------------------------------------------------------------

#: 中文字体候选（按优先级）。Windows 开发机与 Linux 服务器都能命中至少一个。
_FONT_CANDIDATES: tuple[str, ...] = (
    "C:/Windows/Fonts/msyhbd.ttc",  # 微软雅黑 Bold
    "C:/Windows/Fonts/msyh.ttc",  # 微软雅黑
    "C:/Windows/Fonts/simhei.ttf",  # 黑体
    "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",  # 文泉驿正黑（阿里云装 fonts-wqy-zenhei）
    "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
)

_font_cache: dict[tuple[int, bool], ImageFont.FreeTypeFont | ImageFont.ImageFont] = {}


def load_font(size: int, bold: bool = True) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """按尺寸取字体；找不到中文字体时退化为 Pillow 默认字体（中文会画不出来，启动时会告警）。"""
    key = (size, bold)
    if key in _font_cache:
        return _font_cache[key]

    candidates = _FONT_CANDIDATES if bold else tuple(
        c.replace("msyhbd.ttc", "msyh.ttc").replace("wqy-zenhei.ttc", "wqy-microhei.ttc")
        for c in _FONT_CANDIDATES
    )
    for path in candidates:
        if Path(path).exists():
            try:
                font = ImageFont.truetype(path, size)
                _font_cache[key] = font
                return font
            except OSError:
                continue

    font = ImageFont.load_default()
    _font_cache[key] = font
    return font


def has_cjk_font() -> bool:
    """启动自检用：能不能找到中文字体。"""
    for path in _FONT_CANDIDATES:
        if path.startswith(("C:/Windows", "/usr/share")) and Path(path).exists():
            try:
                ImageFont.truetype(path, 20)
                return True
            except OSError:
                continue
    return False


# ---------------------------------------------------------------------------
# 路径 / 命名
# ---------------------------------------------------------------------------


def upload_root() -> Path:
    root = settings.upload_path
    (root / "dishes").mkdir(parents=True, exist_ok=True)
    (root / "thumbs").mkdir(parents=True, exist_ok=True)
    (root / "placeholder").mkdir(parents=True, exist_ok=True)
    return root


def url_for(root: Path, file_path: Path) -> str:
    rel = file_path.relative_to(root).as_posix()
    return f"{settings.upload_url_prefix.rstrip('/')}/{rel}"


# ---------------------------------------------------------------------------
# 上传压缩
# ---------------------------------------------------------------------------

ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP", "BMP", "GIF", "MPO", "TIFF"}
MAX_UPLOAD_BYTES = 12 * 1024 * 1024  # 12MB


class ImageProcessError(Exception):
    """图片非法（不是图片 / 太大 / 格式不支持）。"""


def _flatten(img: Image.Image, background: tuple[int, int, int] = (255, 255, 255)) -> Image.Image:
    """把带透明通道的图铺到白底上，否则存 JPEG 会变黑。"""
    if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
        rgba = img.convert("RGBA")
        canvas = Image.new("RGB", rgba.size, background)
        canvas.paste(rgba, mask=rgba.split()[-1])
        return canvas
    return img.convert("RGB")


def _resize_to_max(img: Image.Image, max_side: int) -> Image.Image:
    w, h = img.size
    longest = max(w, h)
    if longest <= max_side:
        return img
    scale = max_side / float(longest)
    return img.resize((max(1, round(w * scale)), max(1, round(h * scale))), Image.LANCZOS)


def process_upload(raw: bytes, original_name: str = "") -> dict[str, object]:
    """把上传的原始字节压成「主图 + 缩略图」，返回访问 URL。

    主图：长边 <= IMAGE_MAX_SIDE，JPEG quality=IMAGE_JPEG_QUALITY
    缩略图：长边 <= IMAGE_THUMB_SIDE（列表页用，流量友好）
    """
    if not raw:
        raise ImageProcessError("上传内容为空")
    if len(raw) > MAX_UPLOAD_BYTES:
        raise ImageProcessError(f"图片太大了（上限 {MAX_UPLOAD_BYTES // 1024 // 1024}MB）")

    try:
        img = Image.open(io.BytesIO(raw))
        img.load()
    except Exception as exc:  # noqa: BLE001
        raise ImageProcessError("这不是一张能识别的图片") from exc

    if img.format and img.format.upper() not in ALLOWED_FORMATS:
        raise ImageProcessError(f"暂不支持 {img.format} 格式")
    if img.width < 16 or img.height < 16:
        raise ImageProcessError("图片太小了")

    # 手机拍照的旋转信息在这一步被"烘焙"进像素
    img = ImageOps.exif_transpose(img)
    img = _flatten(img)

    root = upload_root()
    stem = uuid.uuid4().hex[:16]

    main = _resize_to_max(img, settings.image_max_side)
    main_path = root / "dishes" / f"{stem}.jpg"
    main.save(main_path, "JPEG", quality=settings.image_jpeg_quality, optimize=True, progressive=True)

    thumb = _resize_to_max(img, settings.image_thumb_side)
    thumb_path = root / "thumbs" / f"{stem}.jpg"
    thumb.save(thumb_path, "JPEG", quality=min(settings.image_jpeg_quality, 82), optimize=True)

    return {
        "image_url": url_for(root, main_path),
        "thumb_url": url_for(root, thumb_path),
        "width": main.width,
        "height": main.height,
        "bytes": main_path.stat().st_size,
        "original_name": original_name,
    }


def delete_upload(image_url: str) -> bool:
    """删除上传文件（主图 + 对应缩略图）。返回是否删掉了什么。"""
    if not image_url:
        return False
    prefix = settings.upload_url_prefix.rstrip("/") + "/"
    if not image_url.startswith(prefix):
        return False
    rel = image_url[len(prefix) :].lstrip("/")
    if not rel or ".." in rel:
        return False

    root = settings.upload_path
    target = (root / rel).resolve()
    try:
        target.relative_to(root.resolve())
    except ValueError:
        return False

    removed = False
    if target.is_file():
        target.unlink()
        removed = True

    # 主图在 dishes/ 下，缩略图同名在 thumbs/ 下
    if target.parent.name == "dishes":
        thumb = root / "thumbs" / target.name
        if thumb.is_file():
            thumb.unlink()
            removed = True
    return removed


# ---------------------------------------------------------------------------
# 占位图生成
# ---------------------------------------------------------------------------

#: 一组粉色系渐变，按菜名哈希稳定选取，保证同一道菜每次生成颜色一致
_PALETTES: tuple[tuple[tuple[int, int, int], tuple[int, int, int]], ...] = (
    ((255, 214, 224), (255, 236, 214)),  # 粉 → 暖黄
    ((255, 205, 219), (255, 231, 240)),  # 玫瑰粉 → 淡粉
    ((255, 226, 208), (255, 244, 224)),  # 蜜桃 → 米白
    ((252, 213, 232), (226, 222, 255)),  # 樱粉 → 薰衣草
    ((255, 219, 205), (255, 238, 226)),  # 珊瑚 → 奶白
    ((238, 224, 255), (255, 226, 236)),  # 淡紫 → 樱粉
    ((255, 235, 205), (255, 216, 224)),  # 香槟 → 粉
)


def _palette_for(text: str) -> tuple[tuple[int, int, int], tuple[int, int, int]]:
    digest = hashlib.md5(text.encode("utf-8")).digest()
    return _PALETTES[digest[0] % len(_PALETTES)]


def _linear_gradient(
    size: tuple[int, int],
    start: tuple[int, int, int],
    end: tuple[int, int, int],
) -> Image.Image:
    w, h = size
    base = Image.new("RGB", (1, h))
    px = base.load()
    for y in range(h):
        t = y / max(1, h - 1)
        px[0, y] = (
            round(start[0] + (end[0] - start[0]) * t),
            round(start[1] + (end[1] - start[1]) * t),
            round(start[2] + (end[2] - start[2]) * t),
        )
    return base.resize((w, h), Image.BILINEAR)


def _heart_points(cx: float, cy: float, size: float, count: int = 240) -> list[tuple[float, float]]:
    """爱心参数方程，用于手绘一个真正的爱心形状。"""
    pts: list[tuple[float, float]] = []
    scale = size / 34.0
    for i in range(count):
        t = 2 * math.pi * i / count
        x = 16 * math.sin(t) ** 3
        y = 13 * math.cos(t) - 5 * math.cos(2 * t) - 2 * math.cos(3 * t) - math.cos(4 * t)
        pts.append((cx + x * scale, cy - y * scale))
    return pts


def _draw_heart(
    draw: ImageDraw.ImageDraw,
    cx: float,
    cy: float,
    size: float,
    fill: tuple[int, int, int, int],
) -> None:
    draw.polygon(_heart_points(cx, cy, size), fill=fill)


def _fit_font_size(text: str, max_width: int, start: int = 44, min_size: int = 14) -> int:
    size = start
    while size > min_size:
        font = load_font(size)
        box = font.getbbox(text)
        if box[2] - box[0] <= max_width:
            return size
        size -= 2
    return min_size


def _wrap(text: str, max_chars: int, max_lines: int = 2) -> list[str]:
    """按字符数粗暴折行（中文没有词边界，够用了）。"""
    if len(text) <= max_chars:
        return [text]
    lines = [text[i : i + max_chars] for i in range(0, len(text), max_chars)]
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = lines[-1][: max(1, max_chars - 1)] + "…"
    return lines


def make_placeholder(
    title: str,
    subtitle: str = "",
    size: tuple[int, int] = (900, 675),
    out_name: str | None = None,
) -> str:
    """生成一张粉色渐变 + 爱心 + 菜名的占位图，返回可访问 URL。"""
    start, end = _palette_for(title or "爱心小食堂")
    img = _linear_gradient(size, start, end)

    # 背景点缀：右下角两颗半透明爱心 + 左上角一颗小爱心
    overlay = Image.new("RGBA", size, (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    w, h = size
    _draw_heart(od, w * 0.82, h * 0.78, h * 0.42, (255, 255, 255, 70))
    _draw_heart(od, w * 0.66, h * 0.90, h * 0.26, (255, 255, 255, 55))
    _draw_heart(od, w * 0.16, h * 0.20, h * 0.14, (255, 255, 255, 80))
    img = Image.alpha_composite(img.convert("RGBA"), overlay)

    draw = ImageDraw.Draw(img)

    # 中间一个白色实心爱心 + 文字
    cx, cy = w * 0.5, h * 0.40
    _draw_heart(draw, cx, cy, h * 0.17, (255, 255, 255, 235))

    lines = _wrap(title or "爱心小食堂", 7, max_lines=2)
    font_size = min(_fit_font_size(line, int(w * 0.82)) for line in lines)
    font = load_font(font_size)
    line_h = int(font_size * 1.28)
    total_h = line_h * len(lines)
    y = h * 0.60 - total_h / 2
    for line in lines:
        box = draw.textbbox((0, 0), line, font=font)
        tw = box[2] - box[0]
        # 深一点的粉做文字色，保证在白底爱心/浅粉背景上可读
        draw.text(
            ((w - tw) / 2, y - box[1]),
            line,
            font=font,
            fill=(186, 74, 112),
        )
        y += line_h

    if subtitle:
        sub_font = load_font(max(16, int(font_size * 0.42)), bold=False)
        sub = subtitle[:22]
        box = draw.textbbox((0, 0), sub, font=sub_font)
        tw = box[2] - box[0]
        draw.text(
            ((w - tw) / 2, y + 6 - box[1]),
            sub,
            font=sub_font,
            fill=(178, 116, 138),
        )

    root = upload_root()
    if out_name:
        main_path = root / "placeholder" / out_name
        main_path.parent.mkdir(parents=True, exist_ok=True)
    else:
        stem = uuid.uuid4().hex[:16]
        main_path = root / "placeholder" / f"{stem}.jpg"

    thumb = _resize_to_max(img.convert("RGB"), settings.image_thumb_side)
    main_path.parent.mkdir(parents=True, exist_ok=True)
    img.convert("RGB").save(
        main_path, "JPEG", quality=settings.image_jpeg_quality, optimize=True
    )

    thumb_path = root / "thumbs" / main_path.name
    thumb.save(thumb_path, "JPEG", quality=82, optimize=True)

    return url_for(root, main_path)

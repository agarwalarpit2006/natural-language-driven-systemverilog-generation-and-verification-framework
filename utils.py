# =============================================================
# utils.py  —  Shared helpers
# =============================================================

import os
import re
import logging
import datetime


def get_logger(name: str = "sv_gen") -> logging.Logger:
    logger = logging.getLogger(name)
    if not logger.handlers:
        h = logging.StreamHandler()
        h.setFormatter(logging.Formatter("[%(asctime)s] %(levelname)s  %(message)s", "%H:%M:%S"))
        logger.addHandler(h)
        logger.setLevel(logging.DEBUG)
    return logger

log = get_logger()


def ensure_output_dir(path: str = "output") -> str:
    os.makedirs(path, exist_ok=True)
    return path


def write_file(path: str, content: str) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def read_file(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def sv_width_str(width: int) -> str:
    return f"[{width - 1}:0] " if width > 1 else ""


def sv_value(val: int, width: int) -> str:
    if width <= 1:
        return str(val & 1)
    hex_digits = (width + 3) // 4
    return f"{width}'h{val:0{hex_digits}X}"


def to_sv_identifier(s: str) -> str:
    s = re.sub(r"[^\w]", "_", s.strip())
    s = re.sub(r"_+", "_", s)
    if s and s[0].isdigit():
        s = "m_" + s
    return s or "sig"


def timestamped_filename(base: str, ext: str, directory: str = "output") -> str:
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    return os.path.join(directory, f"{base}_{ts}.{ext}")

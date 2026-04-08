"""应用级日志（与 app.py 同级目录下的 log 文件）。"""
import logging

from lvm.constants import APP_DIR

LOG = logging.getLogger("video_manager")


def setup_logging() -> None:
    log_file = APP_DIR / "local-video-manager.log"
    if LOG.handlers:
        return
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    fh = logging.FileHandler(log_file, encoding="utf-8")
    fh.setFormatter(fmt)
    sh = logging.StreamHandler()
    sh.setFormatter(fmt)
    LOG.setLevel(logging.INFO)
    LOG.addHandler(fh)
    LOG.addHandler(sh)
    LOG.propagate = False

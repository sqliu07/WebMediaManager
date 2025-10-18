import logging
import os
from datetime import datetime
from pathlib import Path

def setup_logger(name="MediaManager"):
    # 创建 log 目录
    log_dir = Path("log")
    log_dir.mkdir(exist_ok=True)

    # 日志文件名：2025-10-18_23-59-59.log
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    log_file = log_dir / f"{timestamp}.log"

    # 日志格式
    log_format = "%(asctime)s [%(levelname)s] %(message)s"
    date_format = "%Y-%m-%d %H:%M:%S"

    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)  # 可改为 INFO、WARNING 等级

    # 防止重复添加 handler
    if not logger.handlers:
        # 控制台输出
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(logging.Formatter(log_format, date_format))

        # 文件输出
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(logging.Formatter(log_format, date_format))

        logger.addHandler(console_handler)
        logger.addHandler(file_handler)

    return logger

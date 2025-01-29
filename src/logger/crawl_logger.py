import logging
import os
import sys
from logging.handlers import RotatingFileHandler


class CsvFormatter(logging.Formatter):
    def format(self, record):
        created = self.formatTime(record, "%Y-%m-%d %H:%M:%S")
        return f"{created},{record.pathname},{record.lineno},{record.name},{record.levelname},{record.getMessage()}"


class CsvFilter(logging.Filter):
    def filter(self, record):
        return record.levelno >= logging.INFO


class CustomLogger:
    def __init__(
        self, logger_name="crawl_logger", log_dir="logs", log_file_name="log.csv"
    ):
        self.logger = logging.getLogger(logger_name)
        self.logger.setLevel(logging.DEBUG)

        # Create logs directory if it doesn't exist
        self.log_dir = log_dir
        self.log_file = os.path.join(log_dir, log_file_name)
        os.makedirs(self.log_dir, exist_ok=True)

        # Setup rotating file handler
        max_bytes = 1024 * 1024 * 250  # 250 MB
        backup_count = 7

        try:
            csv_handler = RotatingFileHandler(
                self.log_file, maxBytes=max_bytes, backupCount=backup_count
            )
            csv_handler.setLevel(logging.DEBUG)
            csv_handler.setFormatter(CsvFormatter())
            csv_handler.addFilter(CsvFilter())
            self.logger.addHandler(csv_handler)
        except Exception as e:
            # Handle exceptions (e.g., logging them)
            print(f"Failed to setup file handler: {e}")

        # Setup console handler (uncomment if needed)
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.DEBUG)
        console_formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )
        console_handler.setFormatter(console_formatter)
        self.logger.addHandler(console_handler)


# Usage
logger = CustomLogger().logger
logger.debug("Logger has been initialized.")


# TODO rewrite logger using singleton and thread lock OR use async logging
# import logging
# import os
# import sys
# from logging.handlers import RotatingFileHandler
# from threading import Lock

# class CsvFormatter(logging.Formatter):
#     def format(self, record):
#         created = self.formatTime(record, "%Y-%m-%d %H:%M:%S")
#         return f"{created},{record.pathname},{record.lineno},{record.name},{record.levelname},{record.getMessage()}"

# class CsvFilter(logging.Filter):
#     def filter(self, record):
#         return record.levelno >= logging.INFO

# class SingletonMeta(type):
#     """
#     A thread-safe implementation of Singleton.
#     """
#     _instances = {}
#     _lock = Lock()

#     def __call__(cls, *args, **kwargs):
#         with cls._lock:
#             if cls not in cls._instances:
#                 instance = super().__call__(*args, **kwargs)
#                 cls._instances[cls] = instance
#         return cls._instances[cls]

# class CustomLogger(metaclass=SingletonMeta):
#     def __init__(self, logger_name="chatbot_logger", log_dir="logs", log_file_name="log.csv"):
#         if not hasattr(self, 'logger'):
#             self.logger = logging.getLogger(logger_name)
#             self.logger.setLevel(logging.DEBUG)  # Default level can be enhanced through configurations

#             # Create logs directory if it doesn't exist
#             self.log_dir = log_dir
#             self.log_file = os.path.join(log_dir, log_file_name)
#             os.makedirs(self.log_dir, exist_ok=True)

#             # Setup rotating file handler
#             max_bytes = 1024 * 1024 * 250  # 250 MB
#             backup_count = 7

#             try:
#                 csv_handler = RotatingFileHandler(self.log_file, maxBytes=max_bytes, backupCount=backup_count)
#                 csv_handler.setLevel(logging.DEBUG)
#                 csv_handler.setFormatter(CsvFormatter())
#                 csv_handler.addFilter(CsvFilter())
#                 self.logger.addHandler(csv_handler)
#             except Exception as e:
#                 print(f"Failed to setup file handler: {e}")

#             # Setup console handler (uncomment if needed)
#             console_handler = logging.StreamHandler(sys.stdout)
#             console_handler.setLevel(logging.DEBUG)
#             console_formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
#             console_handler.setFormatter(console_formatter)
#             self.logger.addHandler(console_handler)

# # Usage
# logger = CustomLogger().logger
# logger.info("Logger has been initialized.")

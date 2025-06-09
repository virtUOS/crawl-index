import logging
import os
import sys
from logging.handlers import RotatingFileHandler


class ColoredFormatter(logging.Formatter):
    """Custom formatter with colors for different log levels"""

    COLORS = {
        logging.DEBUG: "\033[0;36m",  # Cyan
        logging.INFO: "\033[0;32m",  # Green
        logging.WARNING: "\033[0;33m",  # Yellow
        logging.ERROR: "\033[0;31m",  # Red
        logging.CRITICAL: "\033[0;37;41m",  # White on Red
        "RESET": "\033[0m",  # Reset
    }

    def format(self, record):
        # Add color to level name
        levelname_color = self.COLORS.get(record.levelno, "")
        record.levelname = f"{levelname_color}{record.levelname}{self.COLORS['RESET']}"

        # Add color to message
        msg_color = self.COLORS.get(record.levelno, "")
        record.msg = f"{msg_color}{record.msg}{self.COLORS['RESET']}"

        return super().format(record)


class CsvFormatter(logging.Formatter):
    def format(self, record):
        created = self.formatTime(record, "%Y-%m-%d %H:%M:%S")
        return f"{created},{record.pathname},{record.lineno},{record.name},{record.levelname},{record.getMessage()}"


class CsvFilter(logging.Filter):
    def filter(self, record):
        # Save only INFO and above levels:
        return record.levelno >= logging.INFO


# Create a logger
logger = logging.getLogger("chatbot_logger")
logger.setLevel(logging.DEBUG)  # Set the logging level

# Define the logs directory and files
log_dir = "logs"
log_file = os.path.join(log_dir, "log.csv")
error_log_file = os.path.join(log_dir, "error.log")

# Create the logs directory if it doesn't exist
if not os.path.exists(log_dir):
    os.makedirs(log_dir)

# Create a rotating CSV file handler for general logs
max_bytes = 1024 * 1024 * 250  # 250 MB
backup_count = 7

csv_handler = RotatingFileHandler(
    log_file, maxBytes=max_bytes, backupCount=backup_count
)
csv_handler.setLevel(logging.DEBUG)
csv_formatter = CsvFormatter()
csv_handler.setFormatter(csv_formatter)
csv_handler.addFilter(CsvFilter())
logger.addHandler(csv_handler)

# Create a rotating file handler for error logs
error_handler = RotatingFileHandler(
    error_log_file, maxBytes=max_bytes, backupCount=backup_count
)
error_handler.setLevel(logging.WARNING)
error_formatter = logging.Formatter(
    "%(asctime)s - %(name)s - %(levelname)s - %(message)s [File: %(pathname)s, Line: %(lineno)d]"
)
error_handler.setFormatter(error_formatter)
logger.addHandler(error_handler)

# Create a console handler for debugging
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setLevel(logging.DEBUG)
colored_formatter = ColoredFormatter(
    "%(asctime)s - %(name)s - %(levelname)s - %(message)s [File: %(pathname)s, Line: %(lineno)d]"
)
console_handler.setFormatter(colored_formatter)
logger.addHandler(console_handler)

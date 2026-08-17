import sys
from loguru import logger
from config import LOG_FILE

def configure_logger():
    """
    Configures loguru to write to both console (stdout) if available, 
    and a rotating log file. Safe for pythonw.exe execution where sys.stdout is None.
    """
    # Remove default handler
    logger.remove()

    # Add console handler only if sys.stdout exists (interactive terminal mode)
    if sys.stdout is not None:
        try:
            logger.add(
                sys.stdout, 
                format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
                level="INFO",
                colorize=True
            )
        except Exception:
            pass

    # Add file handler with rotation and retention (Always active)
    logger.add(
        LOG_FILE,
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
        level="DEBUG",
        rotation="10 MB",    # Rotate file when it reaches 10MB
        retention="30 days", # Keep logs for 30 days
        compression="zip",   # Compress rotated logs
        encoding="utf-8"
    )

    return logger

# Create a default logger instance to be imported by other modules
app_logger = configure_logger()

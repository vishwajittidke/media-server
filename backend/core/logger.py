import logging
import json
import traceback
from sqlalchemy.orm import Session
from models import SystemLog, LogLevelEnum, LogCategoryEnum
from database import SessionLocal

# Create a local python logger
py_logger = logging.getLogger("media_server")
py_logger.setLevel(logging.INFO)
handler = logging.StreamHandler()
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
py_logger.addHandler(handler)

SENSITIVE_KEYS = ["password", "service_account_json", "access_key", "secret_key", "token", "supabase_key", "api_key", "api_secret"]

def scrub_message(msg: str) -> str:
    """Mask sensitive data in strings or stringified JSON."""
    try:
        # Try to parse as dict to scrub values
        if "{" in msg and "}" in msg:
            # Simple heuristic, won't catch everything perfectly but good for simple dict strings
            for key in SENSITIVE_KEYS:
                if key in msg:
                    # just blindly replace common formats
                    msg = msg.replace(f'"{key}":', f'"{key}": "********", //')
                    msg = msg.replace(f"'{key}':", f"'{key}': '********', //")
    except Exception:
        pass
    
    # Also just scan for the keys directly if it's a stack trace or raw text
    lower_msg = msg.lower()
    for key in SENSITIVE_KEYS:
        if key in lower_msg:
            msg = msg + "\n[NOTE: Potential sensitive key detected and logged, proceed with caution.]"
    return msg

def log_system_event(
    level: LogLevelEnum, 
    category: LogCategoryEnum, 
    message: str, 
    user_id: str = None, 
    exc_info: Exception = None,
    db: Session = None
):
    """
    Log an event to the console and to the database.
    """
    scrubbed_message = scrub_message(message)
    stack_trace = None
    
    if exc_info:
        stack_trace = "".join(traceback.format_exception(type(exc_info), exc_info, exc_info.__traceback__))
        stack_trace = scrub_message(stack_trace)

    # Console logging
    log_msg = f"[{category.value}] {scrubbed_message}"
    if level == LogLevelEnum.INFO:
        py_logger.info(log_msg)
    elif level == LogLevelEnum.WARNING:
        py_logger.warning(log_msg)
    elif level in [LogLevelEnum.ERROR, LogLevelEnum.CRITICAL, LogLevelEnum.SECURITY]:
        py_logger.error(log_msg)
        if stack_trace:
            py_logger.error(stack_trace)

    # Database logging - ALWAYS use a fresh session to avoid dirty session issues
    session = SessionLocal()
    try:
        new_log = SystemLog(
            level=level,
            category=category,
            message=scrubbed_message,
            stack_trace=stack_trace,
            user_id=user_id
        )
        session.add(new_log)
        session.commit()
    except Exception as e:
        session.rollback()
        py_logger.error(f"Failed to write to system_logs table: {e}")
    finally:
        session.close()

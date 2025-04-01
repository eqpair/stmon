from datetime import datetime, time
import logging

logger = logging.getLogger(__name__)

def is_market_time() -> bool:
    now = datetime.now()
    current_time = now.time()
    weekday = now.weekday()
    
    is_weekday = 0 <= weekday <= 4
    is_work_hours = time(8, 30) <= current_time <= time(16, 30)
    
    return is_weekday and is_work_hours
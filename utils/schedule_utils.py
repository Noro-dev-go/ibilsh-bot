from datetime import datetime, timedelta

def get_next_fridays(start_date=None, weeks=10):
    if start_date is None:
        start_date = datetime.now()

    days_ahead = 4 - start_date.weekday()  # 0 - пн, ..., 4 - пт
    if days_ahead < 0:
        days_ahead += 7

    first_friday = start_date + timedelta(days=days_ahead)

    if start_date.weekday() <= 4:  
        first_friday += timedelta(weeks=1)

    return [first_friday + timedelta(weeks=i) for i in range(weeks)]
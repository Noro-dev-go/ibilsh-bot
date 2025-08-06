from datetime import date


TEST_DATE = None #date(2025, 7, 19)


def get_today() -> date:
    return TEST_DATE if TEST_DATE else date.today()
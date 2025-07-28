from datetime import date


TEST_DATE = None #date(2026, 8, 7)


def get_today() -> date:
    return TEST_DATE if TEST_DATE else date.today()
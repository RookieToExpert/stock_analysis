"""Explain incomplete return windows without padding prices or using future status."""
from datetime import date


def calendar_gap_reason(data, calendar):
    dates = [r['date'] for r in data.get('daily', [])
             if calendar['start'] <= r['date'] <= calendar['end']]
    if sorted(dates) == calendar['dates']:
        return None
    if len(dates) != len(set(dates)):
        return 'duplicate_daily_dates'
    basic = data.get('basic') or []
    if len(basic) == 1:
        for field, boundary, reason in (
            ('ipoDate', calendar['start'], 'listed_after_window_start'),
            ('outDate', calendar['end'], 'delisted_before_window_end'),
        ):
            value = basic[0].get(field)
            try:
                date.fromisoformat(value)
            except (ValueError, TypeError):
                continue
            if (field == 'ipoDate' and value > boundary) or (field == 'outDate' and value <= boundary):
                return reason
    return 'incomplete_calendar_unexplained'

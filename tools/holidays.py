# German nationwide public holidays (gesetzliche Feiertage in ALLEN Bundeslaendern)
# covering the data range 2025-12-29 .. 2026-10-11.
NATIONWIDE_HOLIDAYS = {
    '2026-01-01': 'Neujahr',
    '2026-04-03': 'Karfreitag',
    '2026-04-06': 'Ostermontag',
    '2026-05-01': 'Tag der Arbeit',
    '2026-05-14': 'Christi Himmelfahrt',
    '2026-05-25': 'Pfingstmontag',
    '2026-10-03': 'Tag der Deutschen Einheit',
    '2026-12-25': '1. Weihnachtstag',
    '2026-12-26': '2. Weihnachtstag',
    '2027-01-01': 'Neujahr',
    '2027-03-26': 'Karfreitag',
    '2027-03-29': 'Ostermontag',
    '2027-05-01': 'Tag der Arbeit',
    '2027-05-06': 'Christi Himmelfahrt',
    '2027-05-17': 'Pfingstmontag',
}

# School holiday windows where MANY (not necessarily all) German states have school breaks
# simultaneously, which tends to depress chat volume. Approximate, inclusive date ranges
# for 2025/2026 school year (source: general knowledge of German Schulferien calendars,
# which vary slightly per Bundesland but cluster around these periods).
SCHOOL_HOLIDAY_RANGES = [
    ('2025-12-22', '2026-01-06', 'Weihnachtsferien (viele Bundeslaender)'),
    ('2026-02-02', '2026-02-18', 'Winterferien (einige Bundeslaender, zeitlich versetzt)'),
    ('2026-03-30', '2026-04-11', 'Osterferien (viele Bundeslaender)'),
    ('2026-05-26', '2026-05-29', 'Pfingstferien (einige Bundeslaender)'),
    ('2026-07-20', '2026-08-28', 'Sommerferien (viele Bundeslaender, versetzter Beginn/Ende)'),
    ('2026-10-05', '2026-10-17', 'Herbstferien (viele Bundeslaender)'),
    ('2026-12-21', '2027-01-06', 'Weihnachtsferien (viele Bundeslaender)'),
    ('2027-03-22', '2027-04-03', 'Osterferien (viele Bundeslaender)'),
]

from datetime import date, timedelta

def _daterange(a, b):
    d0 = date.fromisoformat(a); d1 = date.fromisoformat(b)
    d = d0
    while d <= d1:
        yield d.isoformat()
        d += timedelta(days=1)

SCHOOL_HOLIDAY_DAYS = {}
for start, end, label in SCHOOL_HOLIDAY_RANGES:
    for d in _daterange(start, end):
        SCHOOL_HOLIDAY_DAYS[d] = label

def day_context(d):
    """Return a dict describing holiday/school-break context for a given ISO date string."""
    ctx = {}
    if d in NATIONWIDE_HOLIDAYS:
        ctx['holiday'] = NATIONWIDE_HOLIDAYS[d]
    if d in SCHOOL_HOLIDAY_DAYS:
        ctx['school_holiday'] = SCHOOL_HOLIDAY_DAYS[d]
    return ctx

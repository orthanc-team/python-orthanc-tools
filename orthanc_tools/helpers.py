import time
import datetime
import random
import re


def wait_until(somepredicate, timeout, period=0.1, *args, **kwargs):
    if timeout is None:
        while True:
            if somepredicate(*args, **kwargs):
                return True
            time.sleep(period)
        return False
    else:
        mustend = time.time() + timeout
        while time.time() < mustend:
            if somepredicate(*args, **kwargs):
                return True
            time.sleep(period)
        return False


def get_random_dicom_date(date_from: datetime.date, date_to: datetime.date = datetime.date.today()) -> str:
    delta = date_to - date_from
    rand_date = date_from + datetime.timedelta(days=random.randint(0, delta.days))
    return '{0:4}{1:02}{2:02}'.format(rand_date.year, rand_date.month, rand_date.day)


def to_dicom_date(date: datetime.date) -> str:
    return '{0:4}{1:02}{2:02}'.format(date.year, date.month, date.day)

def from_dicom_date(dicom_date: str) -> datetime.date:
    if dicom_date is None or len(dicom_date) == 0:
        return None

    m = re.match('(?P<year>[0-9]{4})(?P<month>[0-9]{2})(?P<day>[0-9]{2})', dicom_date)
    if m is None:
        raise ValueError("Not a valid DICOM date: '{0}'".format(dicom_date))

    return datetime.date(int(m.group('year')), int(m.group('month')), int(m.group('day')))

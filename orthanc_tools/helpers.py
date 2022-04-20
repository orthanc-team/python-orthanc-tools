import time
import datetime
import random


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

import os
import time
import logging
import json
from dataclasses import dataclass, field
from typing import Optional, List, Dict
from datetime import datetime
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)


@dataclass(init=False)
class RunningPeriod:
    from_hour: int
    to_hour: int
    weekday: int  # 0=Sunday, 1=Monday, ..., 6=Saturday
    timezone: ZoneInfo = ZoneInfo("Etc/UTC")

    def __init__(self, weekday: int, period: str, timezone: ZoneInfo):
        hours = period.split("-")
        if len(hours) != 2:
            raise ValueError(f"Invalid schedule: invalid period format: {period}")

        self.from_hour = int(hours[0])
        self.to_hour = int(hours[1])

        if self.from_hour < 0 or self.from_hour > 24:
            raise ValueError(f"Invalid schedule: from_hour: {self.from_hour}")
        if self.to_hour < 0 or self.to_hour > 24:
            raise ValueError(f"Invalid schedule: to_hour: {self.to_hour}")

        if self.to_hour <= self.from_hour:
            raise ValueError(f"Invalid schedule: to_hour <= from_hour: {self.to_hour} <= {self.from_hour}")
        
        self.timezone = timezone
        self.weekday = weekday

    def __str__(self):
        return f"{self.day_to_string(self.weekday)}: [{self.from_hour}-{self.to_hour}]"

    @classmethod
    def day_from_string(cls, weekday: str) -> int:
        weekday_map = {
            "Monday": 0,
            "Tuesday": 1,
            "Wednesday": 2,
            "Thursday": 3,
            "Friday": 4,
            "Saturday": 5,
            "Sunday": 6,
        }
        if weekday not in weekday_map:
            raise ValueError(f"Invalid schedule: unknown 'day': {weekday}")
        
        return weekday_map[weekday]

    @classmethod
    def day_to_string(cls, weekday: int) -> str:
        weekday_map = {
            0: "Monday",
            1: "Tuesday",
            2: "Wednesday",
            3: "Thursday",
            4: "Friday",
            5: "Saturday",
            6: "Sunday",
        }
        if weekday not in weekday_map:
            raise ValueError(f"Invalid schedule: unknown 'day': {weekday}")
        
        return weekday_map[weekday]

    def is_in_period(self) -> bool:
        now = datetime.now(self.timezone)
        if now.weekday() != self.weekday:
            return False
        return self.from_hour <= now.hour < self.to_hour


# sample schedule:
# {
#   "Monday-Friday": ["0-6", "20-24"],
#   "Saturday-Sunday": ["0-24"]
# }
@dataclass()
class RunningPeriods:
    periods: List[RunningPeriod] = field(default_factory=list)
    timezone: ZoneInfo = ZoneInfo("Etc/UTC")

    def __str__(self):
        str_periods = []
        for p in self.periods:
            str_periods.append(str(p))
        return f"tz = {self.timezone} --> " + ", ".join(str_periods)

    def load(self, schedule_configuration: Dict[str, List[str]]) -> None:
        for weekday, periods in schedule_configuration.items():
            weekdays = []
            if "-" in weekday:
                from_day = RunningPeriod.day_from_string(weekday.split('-')[0].strip())
                to_day = RunningPeriod.day_from_string(weekday.split('-')[1].strip())

                if from_day >= to_day:
                    raise ValueError(f"Invalid schedule: from_day >= to_day: {from_day} >= {to_day} ({weekday})")

                weekdays = range(from_day, to_day)
            else:
                weekdays = [RunningPeriod.day_from_string(weekday)]

            for wd in weekdays:
                for period in periods:
                    self.periods.append(RunningPeriod(wd, period, self.timezone))

    def is_in_period(self) -> bool:
        if not self.periods:
            return True  # if no config: always run
        return any(period.is_in_period() for period in self.periods)


class Scheduler:
    """
    Helper class to run a task only at certain time of the day
    """
    _running_periods: RunningPeriods

    def __init__(self, 
                 night_start_hour: int = 19, 
                 night_end_hour: int = 7, 
                 run_only_at_night_and_weekend: bool = False, 
                 run_schedule: Optional[Dict[str, List[str]]] = None,
                 timezone: ZoneInfo = ZoneInfo("Etc/UTC")
                 ):
        self._running_periods = RunningPeriods(timezone=timezone)

        if run_schedule is not None:
            self._running_periods.load(schedule_configuration=run_schedule)
        elif run_only_at_night_and_weekend:
            json_schedule = {
                "Monday": [f"0-{night_end_hour}", f"{night_start_hour}-24"],
                "Tuesday": [f"0-{night_end_hour}", f"{night_start_hour}-24"],
                "Wednesday": [f"0-{night_end_hour}", f"{night_start_hour}-24"],
                "Thursday": [f"0-{night_end_hour}", f"{night_start_hour}-24"],
                "Friday": [f"0-{night_end_hour}", f"{night_start_hour}-24"],
                "Saturday": ["0-24"],
                "Sunday": ["0-24"]
            }
            self._running_periods.load(schedule_configuration=json_schedule)

    def wait_right_time_to_run(self):
        while not self._running_periods.is_in_period():
            logger.info("waiting 10 min for the right scheduled time to come")
            time.sleep(600)


    def __str__(self):
        return str(self._running_periods)


    @classmethod
    def add_parser_arguments(cls, parser):
        parser.add_argument('--run_only_at_night_and_weekend', default=False, action='store_true', help='enables script only at night or weekend')
        parser.add_argument('--night_start_hour', type=int, default=19, help='Night start hour')
        parser.add_argument('--night_end_hour', type=int, default=6, help='Night start hour')
        parser.add_argument('--run_schedule', type=str, default=None, help='Run on schedule sample: {"Monday": ["0-6", "20-24"], .., "Sunday": ["0-24"]}')
        parser.add_argument('--timezone', type=str, default="Utc/UTC", help='Timezone for the schedule')

    @classmethod
    def create_from_args_and_env_var(cls, args):
        tz = os.environ.get("TZ", args.timezone)

        night_start_hour = int(os.environ.get("NIGHT_START_HOUR", str(args.night_start_hour)))
        night_end_hour = int(os.environ.get("NIGHT_END_HOUR", str(args.night_end_hour)))
        if os.environ.get("RUN_ONLY_AT_NIGHT_AND_WEEKEND", None) is not None:
            run_only_at_night_and_weekend = os.environ.get("RUN_ONLY_AT_NIGHT_AND_WEEKEND") == "true"
        else:
            run_only_at_night_and_weekend = args.run_only_at_night_and_weekend
        run_schedule = json.loads(os.environ.get("RUN_SCHEDULE", str(args.run_schedule)))

        return Scheduler(
            night_start_hour=night_start_hour,
            night_end_hour=night_end_hour,
            run_only_at_night_and_weekend=run_only_at_night_and_weekend,
            run_schedule=run_schedule,
            timezone=ZoneInfo(tz)
        )

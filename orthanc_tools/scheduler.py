import os
import time
import logging

class Scheduler:
    """
    Helper class to run a task only at certain time of the day
    """

    def __init__(self, night_start_hour: int = 19, night_end_hour: int = 7, run_only_at_night_and_weekend: bool = False):
        self._night_start_hour = night_start_hour
        self._night_end_hour = night_end_hour
        self._run_only_at_night_and_weekend = run_only_at_night_and_weekend

    def wait_right_time_to_run(self, logger):
        if self._run_only_at_night_and_weekend:
            is_right_time = False
            while not is_right_time:
                now = time.localtime()
                if now.tm_wday <= 4 and self._night_end_hour <= now.tm_hour < self._night_start_hour:
                    is_right_time = False
                    logger.info("waiting 10 min for the night or week-end to come")
                    time.sleep(600)
                else:
                    is_right_time = True


    @classmethod
    def add_parser_arguments(cls, parser):
        parser.add_argument('--run_only_at_night_and_weekend', default=False, action='store_true', help='enables script only at night')
        parser.add_argument('--night_start_hour', type=int, default=19, help='Night start hour')
        parser.add_argument('--night_end_hour', type=int, default=6, help='Night start hour')

    @classmethod
    def create_from_args_and_env_var(cls, args):
        night_start_hour = int(os.environ.get("NIGHT_START_HOUR", str(args.night_start_hour)))
        night_end_hour = int(os.environ.get("NIGHT_END_HOUR", str(args.night_end_hour)))
        if os.environ.get("RUN_ONLY_AT_NIGHT_AND_WEEKEND", None) is not None:
            run_only_at_night_and_weekend = os.environ.get("RUN_ONLY_AT_NIGHT_AND_WEEKEND") == "true"
        else:
            run_only_at_night_and_weekend = args.run_only_at_night_and_weekend

        return Scheduler(
            night_start_hour=night_start_hour,
            night_end_hour=night_end_hour,
            run_only_at_night_and_weekend=run_only_at_night_and_weekend
        )

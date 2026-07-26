import argparse
from unittest.mock import patch

from orthanc_tools.helpers.scheduler import RunningPeriods, Scheduler, ZoneInfo


def scheduler_args(**overrides):
    values = {
        "night_start_hour": 19,
        "night_end_hour": 6,
        "run_only_at_night_and_weekend": False,
        "run_schedule": None,
        "timezone": "Etc/UTC",
    }
    values.update(overrides)
    return argparse.Namespace(**values)


def test_day_ranges_include_both_endpoints():
    periods = RunningPeriods(timezone=ZoneInfo("Etc/UTC"))

    periods.load({
        "Monday-Friday": ["0-1"],
        "Saturday-Sunday": ["0-24"],
    })

    assert [period.weekday for period in periods.periods] == list(range(7))


def test_create_from_defaults_allows_running_without_a_schedule():
    with patch.dict("os.environ", {}, clear=True):
        scheduler = Scheduler.create_from_args_and_env_var(scheduler_args())

    assert scheduler._running_periods.periods == []
    assert scheduler._running_periods.is_in_period()
    assert str(scheduler._running_periods.timezone) == "Etc/UTC"


def test_create_from_json_cli_schedule_uses_requested_timezone():
    args = scheduler_args(
        run_schedule='{"Monday-Sunday": ["0-24"]}',
        timezone="Europe/Budapest",
    )

    with patch.dict("os.environ", {}, clear=True):
        scheduler = Scheduler.create_from_args_and_env_var(args)

    assert len(scheduler._running_periods.periods) == 7
    assert str(scheduler._running_periods.timezone) == "Europe/Budapest"


def test_environment_schedule_overrides_cli_schedule():
    args = scheduler_args(run_schedule='{"Monday": ["0-1"]}')

    with patch.dict(
        "os.environ",
        {
            "RUN_SCHEDULE": '{"Sunday": ["0-24"]}',
            "TZ": "Europe/Budapest",
        },
        clear=True,
    ):
        scheduler = Scheduler.create_from_args_and_env_var(args)

    assert [period.weekday for period in scheduler._running_periods.periods] == [6]
    assert str(scheduler._running_periods.timezone) == "Europe/Budapest"

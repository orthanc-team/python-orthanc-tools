import time
from .timer import Timer


class TimeOut(Timer):
    """
    Helper to checks if an elapsed time has been reached.
    """

    def __init__(self, timeout):
        """

        :param timeout: duration (in seconds) until the TimeOut object expires
        """
        self._timeout = timeout
        Timer.__init__(self)

    def is_expired(self):
        """
        Checks if the TimeOut has expired.

        example:
        # wait max 60 seconds until my system has started and check every seconds
        timeout = TimeOut(60)
        while not self._isStarted() and not timeout.is_expired():
            time.sleep(1)

        :return: True if expired, False otherwise
        """
        return self.get_elapsed_seconds() > self._timeout

    def wait_until_expired(self):
        """
        Waits until the TimeOut has expired.

        example:
        while True:
            timeout = TimeOut(self._pollingIntervalInSeconds)
            self._performLengthyOperation()
            timeout.waitExpired()
        """
        remaining = self._timeout - self.get_elapsed_seconds()
        if remaining >= 0:
            time.sleep(remaining)

    @staticmethod
    def wait_until_condition(condition, timeout, evaluate_interval = 1):
        """
        evaluate a condition (lambda) multiple times until it is statisfied or a timeout occurs
        :param condition: the lambda expression to evaluate
        :param timeout: the max time to wait (in seconds) until the condition is satisfied
        :param evaluate_interval: the interval (in seconds) between to evaluation of the condition
        :return: true if the condition is satisfed before the timeout expired, false otherwise
        """
        timeout = TimeOut(timeout)
        satisfied = False
        while not satisfied and not timeout.is_expired():
            satisfied = condition()
            if not satisfied:
                time.sleep(evaluate_interval)

        if not satisfied:  # if not satisfied after timeout, let's try a last time
            return condition()
        else:
            return True

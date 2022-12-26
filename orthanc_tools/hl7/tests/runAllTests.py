import unittest
import os

scriptFolder = os.path.abspath(os.path.dirname(__file__))

if __name__ == '__main__':

    testSuite = unittest.defaultTestLoader.discover(scriptFolder, pattern = 'test_*.py')
    testRunner = unittest.TextTestRunner()
    testRunner.verbosity = 2
    result = testRunner.run(testSuite)

    exit((len(result.errors) != 0) or (len(result.failures) != 0))

import unittest

from orthanc_tools import Cloner


class TestInstantiate(unittest.TestCase):

    def test_instantiate_cloner(self):
        # check it does not raise an exception
        cloner = Cloner(source=OrthancApiClient('http://localhost:8042'),
                        destination=source=OrthancApiClient('http://localhost:8042'))


if __name__ == '__main__':
    unittest.main()


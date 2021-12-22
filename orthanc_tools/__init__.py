from .orthanc_cloner import OrthancCloner
from .orthanc_folder_importer import *
from .orthanc_monitor import OrthancMonitor


# Set default logging handler to avoid "No handler found" warnings.
import logging
from logging import NullHandler

logger = logging.getLogger('orthanc_tools')
logger.addHandler(NullHandler())


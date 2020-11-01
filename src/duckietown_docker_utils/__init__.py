__version__ = "6.0.47"

import logging

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
logger.info(__version__)


from .monitoring import *
from .docker_run import *
from .constants import *

__version__ = "6.0.67"

import logging

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
logger.debug(f"duckietown_docker_utils version {__version__} path {__file__}")


from .monitoring import *
from .docker_run import *
from .constants import *

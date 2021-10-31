__version__ = "6.0.97"

import logging

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
import os

path = os.path.dirname(os.path.dirname(__file__))

logger.debug(f"duckietown_docker_utils version {__version__} path {path}")

from .monitoring import *
from .docker_run import *
from .constants import *
from .cli import *

__version__ = "6.0.19"

import logging

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
logger.info(__version__)


from .dt_push import *
from .monitoring import *
from .docker_run import *
from .constants import *

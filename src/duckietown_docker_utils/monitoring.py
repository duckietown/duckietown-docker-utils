import datetime
import os
import re
import sys
import time
import traceback

from docker.errors import APIError, NotFound

from . import logger
from .constants import DEPTH_VAR

__all__ = ["continuously_monitor"]
escape = re.compile("\x1b\[[\d;]*?m")


def is_updating(a: bytes) -> bool:
    possible = [b"pushing", b"pulling", b"%["]
    return any(a.startswith(_) for _ in possible)


def remove_escapes(s):
    return escape.sub("", s)


def continuously_monitor(client, container_name: str, log: str = None):
    depth = int(os.environ.get(DEPTH_VAR, "0"))

    if log is None:
        log = f"{container_name}.log"

        logger.debug(f"Monitoring container {container_name}; logs at {log}")
    last_log_timestamp = None
    while True:
        try:
            container = client.containers.get(container_name)
        except Exception as e:
            # msg = 'Cannot get container %s: %s' % (container_name, e)
            # logger.info(msg)
            break
            # logger.info('Will wait.')
            # time.sleep(5)
            # continue

        # logger.info("status: %s" % container.status)
        if container.status == "exited":
            # msg = "The container exited."
            # logger.info(msg)

            with open(log, "ab") as f:
                for c in container.logs(stdout=True, stderr=True, stream=True, since=last_log_timestamp):
                    # last_log_timestamp = datetime.datetime.now()

                    sys.stderr.buffer.write(c)

                    f.write(c)
                    if b"\n" in c:
                        sys.stderr.buffer.flush()
                        f.flush()

            return  # XXX
        try:

            with open(log, "ab") as f:
                building = b""

                for c in container.logs(
                    stdout=True, stderr=True, stream=True, follow=True, since=last_log_timestamp,
                ):
                    f.write(c)
                    f.flush()

                    building += c

                    if b"\n" in c:

                        if depth == 0:
                            if is_updating(building):
                                building = b"\r" + building.replace(b"\r\n", b"")

                        sys.stderr.buffer.write(building)
                        sys.stderr.buffer.flush()

                        building = b""

                    last_log_timestamp = datetime.datetime.now()

            time.sleep(1)
        except KeyboardInterrupt:
            logger.info("Received CTRL-C. Stopping container...")
            try:
                logger.info(f"Stopping container {container_name}")
                container.stop()
                logger.info(f"Removing container {container_name}")
                container.remove()
                logger.info(f"Container {container_name} removed.")
            except NotFound:
                pass
            except APIError as e:
                # if e.errno == 409:
                #
                pass
            break
        except BaseException:
            logger.error(traceback.format_exc())
            logger.info("Will try to re-attach to container.")
            time.sleep(3)
    # logger.debug('monitoring graceful exit')

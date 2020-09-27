import datetime
import sys
import time
import traceback

from zuper_commons.text import remove_escapes

from . import logger


# Everything after this point needs to be checked


from docker.errors import NotFound, APIError

def continuously_monitor(client, container_name: str, log: str = None):
    if log is None:
        log = f'{container_name}.log'

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

        logger.info("status: %s" % container.status)
        if container.status == "exited":
            msg = "The container exited."
            logger.info(msg)

            with open(log, "a") as f:
                for c in container.logs(stdout=True, stderr=True, stream=True, since=last_log_timestamp):
                    last_log_timestamp = datetime.datetime.now()
                    log_line = c.decode("utf-8")
                    sys.stderr.write(log_line)
                    f.write(remove_escapes(log_line))

            msg = f"Logs saved at {log}"
            logger.info(msg)

            # return container.exit_code
            return  # XXX
        try:
            with open(log, "a") as f:
                for c in container.logs(
                    stdout=True, stderr=True, stream=True, follow=True, since=last_log_timestamp,
                ):
                    log_line = c.decode("utf-8")
                    sys.stderr.write(log_line)
                    f.write(remove_escapes(log_line))
                    last_log_timestamp = datetime.datetime.now()

            time.sleep(3)
        except KeyboardInterrupt:
            logger.info("Received CTRL-C. Stopping container...")
            try:
                container.stop()
                logger.info("Removing container")
                container.remove()
                logger.info("Container removed.")
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

import argparse
import sys

from docker import DockerClient

from . import logger
from .docker_run import generic_docker_run

__all__ = ["dt_docker_run_main"]


def dt_docker_run_main(args=None):
    import logging

    logging.basicConfig()
    parser = argparse.ArgumentParser(prog="dt-docker-run", usage="TODO")
    parser.add_argument("--image", required=True)
    parsed, rest = parser.parse_known_args(args)
    logger.info(f"rest: {rest}")
    # print(f"out rest: {rest}")
    #
    # sys.stderr.flush()
    # sys.stdout.flush()
    # time.sleep(2)
    if parsed.image is None:
        logger.error("Need to specify --image")
        sys.exit(1)
    logname = "a.log"
    container_name = None

    client = DockerClient.from_env()
    gdr = generic_docker_run(
        client,
        as_root=False,
        image=parsed.image,
        commands=rest,
        shell=False,
        docker_secret=None,
        docker_username=None,
        dt1_token=None,
        development=True,
        container_name=container_name,
        pull=False,
        read_only=False,
        detach=True,
        logname=logname,
        share_tmp=False,
        # working_dir='/tmp',
        # entrypoint="xvfb-run",
        # entrypoint="/project/launch1.sh",
        entrypoint=None,
    )
    if gdr.retcode:
        logger.error(gdr.message)

    sys.exit(gdr.retcode)

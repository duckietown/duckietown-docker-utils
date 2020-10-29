import argparse
import logging
import sys
import time
import traceback

from docker import DockerClient
from progressbar import ProgressBar

from . import logger

__all__ = ["dt_push_main"]


def dt_push_main(args=None):
    logging.basicConfig()
    parser = argparse.ArgumentParser()
    # parser.add_argument("--image", required=True)
    parsed, rest = parser.parse_known_args(args=args)

    # noinspection PyBroadException
    try:
        if len(rest) != 1:
            raise Exception("need exactly one argument")

        go(rest[0])
    except SystemExit:
        raise
    except BaseException:
        logger.error(traceback.format_exc())
        sys.exit(3)


def go(image_name: str):
    client = DockerClient.from_env()
    image = client.images.get(image_name)
    RepoTags = image.attrs["RepoTags"]
    RepoDigests = image.attrs["RepoDigests"]
    logger.debug(f"RepoTags {RepoTags}")
    logger.debug(f"RepoDigests {RepoDigests}")

    if RepoDigests:
        logger.info(f"RepoDigests already present; skipping pushing: {RepoDigests}")
        return

    while True:
        try:
            logger.info(f"Pushing {image_name}")
            push_image(client, image_name, progress=True)
        except:
            logger.error(traceback.format_exc())
            logger.error("retrying in 5 seconds")
            time.sleep(5)
        else:
            break
    # for line in client.images.push(image_name, stream=True):
    #     process_docker_api_line(line.decode())


def push_image(client: DockerClient, image_name: str, progress: bool):
    layers = set()
    pushed = set()
    pbar = ProgressBar() if progress else None
    for line in client.images.push(image_name, stream=True, decode=True):
        if "id" not in line or "status" not in line:
            continue
        layer_id = line["id"]
        layers.add(layer_id)
        if line["status"] in ["Layer already exists", "Pushed"]:
            pushed.add(layer_id)
        # update progress bar
        if progress:
            percentage = max(0.0, min(1.0, len(pushed) / max(1.0, len(layers)))) * 100.0
            pbar.update(percentage)
    if progress:
        pbar.finish()

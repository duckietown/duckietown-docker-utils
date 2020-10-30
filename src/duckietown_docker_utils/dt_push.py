import argparse
import sys
import time
import traceback

from docker import DockerClient
from progressbar import Bar, ETA, Percentage, ProgressBar

from . import logger

__all__ = ["dt_push_main", "docker_push_optimized", "push_image", "pull_image", "docker_push_retry"]


def dt_push_main(args=None):
    parser = argparse.ArgumentParser()
    # parser.add_argument("--image", required=True)
    parsed, rest = parser.parse_known_args(args=args)

    # noinspection PyBroadException
    try:
        if len(rest) != 1:
            raise Exception("need exactly one argument")

        image = rest[0]
        logger.info(f"pushing image {image}")
        docker_push_optimized(image)
    except SystemExit:
        raise
    except BaseException:
        logger.error(traceback.format_exc())
        sys.exit(3)


def docker_push_retry(client: DockerClient, image_name):
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


def docker_push_optimized(image_name: str) -> str:
    """ Returns the *complete tag* for the image  "a/b:@sha256:...". Without tags. """
    client = DockerClient.from_env()
    image = client.images.get(image_name)
    image_name_no_tag, _, _ = image_name.partition(":")
    # XXX: apparently docker does not store 'docker.io'
    image_name_no_tag = image_name_no_tag.replace("docker.io/", "")
    RepoTags = image.attrs["RepoTags"]
    RepoTags = [_ for _ in RepoTags if _.startswith(image_name_no_tag)]
    RepoDigests = image.attrs["RepoDigests"]
    RepoDigests = [_ for _ in RepoDigests if _.startswith(image_name_no_tag)]
    # logger.debug(f"RepoTags {RepoTags}")
    # logger.debug(f"RepoDigests {RepoDigests}")

    if RepoDigests:
        logger.debug(f"RepoDigests already present; skipping pushing: {RepoDigests}")
        return RepoDigests[0]
    docker_push_retry(client, image_name)

    image = client.images.get(image_name)
    RepoTags = image.attrs["RepoTags"]
    RepoTags = [_ for _ in RepoTags if _.startswith(image_name_no_tag)]
    RepoDigests = image.attrs["RepoDigests"]
    RepoDigests = [_ for _ in RepoDigests if _.startswith(image_name_no_tag)]

    if not RepoDigests:
        msg = f"cannot find compatible digests\nstarts with {image_name_no_tag} \nattrs: {image.attrs}"
        raise Exception(msg)
    # logger.debug(f"Updated RepoTags {RepoTags}")
    # logger.debug(f"Updated RepoDigests {RepoDigests}")

    return RepoDigests[0]
    # for line in client.images.push(image_name, stream=True):
    #     process_docker_api_line(line.decode())


def push_image(client: DockerClient, image_name: str, progress: bool):
    layers = set()
    pushed = set()
    _, _, image_name_short = image_name.rpartition("/")
    widgets = [f"push {image_name_short} ", Percentage(), " ", Bar(), " ", ETA()]
    pbar = ProgressBar(maxval=100.0, widgets=widgets) if progress else None
    pbar.start()
    sys.stderr.flush()
    for line in client.images.push(image_name, stream=True, decode=True):
        # update progress bar
        if pbar:
            percentage = max(0.0, min(1.0, len(pushed) / max(1.0, len(layers)))) * 100.0
            pbar.update(percentage)
            sys.stderr.flush()
        if "id" not in line or "status" not in line:
            continue
        layer_id = line["id"]
        layers.add(layer_id)
        if line["status"] in ["Layer already exists", "Pushed"]:
            pushed.add(layer_id)

    if pbar:
        pbar.finish()
        sys.stderr.flush()


def pull_image(client: DockerClient, image_name: str, progress: bool):
    if "@" in image_name:
        rest, _, sha = image_name.rpartition("@")
    else:
        rest = image_name
        sha = None
    # logger.info(f'rest: {rest}')
    if ":" in rest:
        name, _, tag = rest.rpartition(":")
    else:
        tag = None
        name = rest

    logger.info(f"{image_name!r}\nname {name!r}\ntag {tag!r}\nsha {sha!r}")
    total_layers = set()
    completed_layers = set()
    _, _, image_name_short = image_name.rpartition("/")
    widgets = [f"pull {image_name_short} ", Percentage(), " ", Bar(), " ", ETA()]
    pbar = ProgressBar(maxval=100.0, widgets=widgets) if progress else None
    pbar.start()
    sys.stderr.flush()
    for step in client.api.pull(name, tag, stream=True, decode=True):
        if "status" not in step or "id" not in step:
            continue
        total_layers.add(step["id"])
        if step["status"] in ["Download complete", "Pull complete"]:
            completed_layers.add(step["id"])
        # compute progress
        if len(total_layers) > 0:
            progress = int(100 * len(completed_layers) / len(total_layers))
            pbar.update(progress)
            sys.stderr.flush()
    pbar.update(100)
    sys.stderr.flush()

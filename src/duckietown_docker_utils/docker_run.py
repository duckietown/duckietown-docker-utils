import getpass
import grp
import json
import os
import platform
import sys
import traceback
from dataclasses import dataclass
from tempfile import TemporaryDirectory
from typing import Dict, List, Optional

from docker import DockerClient
from docker.errors import NotFound
from docker.models.containers import Container

from . import logger
from .constants import CONFIG_DOCKER_PASSWORD, CONFIG_DOCKER_USERNAME, DT1_TOKEN_CONFIG_KEY, IMPORTANT_ENVS
from .monitoring import continuously_monitor


def replace_important_env_vars(s: str) -> str:
    for vname, vdefault in IMPORTANT_ENVS.items():
        vref = "${%s}" % vname
        if vref in s:
            value = os.environ.get(vname, vdefault)
            s = s.replace(vref, value)
    return s


@dataclass
class GenericDockerRunOutput:
    retcode: int
    message: str


def generic_docker_run(
    client: DockerClient,
    as_root: bool,
    image: str,
    development: bool,
    pull: bool,
    docker_username: Optional[str],
    docker_secret: Optional[str],
    commands: List[str],
    shell: bool,
    entrypoint: Optional[str],
    dt1_token: Optional[str],
    container_name: str,
    logname: str,
) -> GenericDockerRunOutput:
    image = replace_important_env_vars(image)
    logger.debug(f"using image: {image}")
    logger.debug(f"development: {development}")
    pwd = os.getcwd()

    pwd1 = os.path.realpath(pwd)
    user = getpass.getuser()

    volumes2: Dict[str, dict] = {}
    envs = {}
    for k, default in IMPORTANT_ENVS.items():
        envs[k] = os.environ.get(k, default)

    contents = {
        CONFIG_DOCKER_USERNAME: docker_username,
        CONFIG_DOCKER_PASSWORD: docker_secret,
        DT1_TOKEN_CONFIG_KEY: dt1_token,
    }
    FAKE_HOME_GUEST = "/home"
    with TemporaryDirectory() as tmpdir:
        fake_home_host = os.path.join(tmpdir, "fake-home")
        os.makedirs(fake_home_host)
        credentials = os.path.join(tmpdir, "credentials")
        # os.makedirs(credentials)
        with open(credentials, "w") as f:
            f.write(json.dumps(contents))
        guest_credentials = "/credentials"
        volumes2[credentials] = {"bind": guest_credentials, "mode": "ro"}

        uid1 = os.getuid()

        if sys.platform == "darwin":
            flag = ":delegated"
        else:
            flag = ""

        if as_root:
            pass
        else:
            envs["USER"] = user
            envs["USERID"] = uid1

            # home = os.path.expanduser("~")

            volumes2[fake_home_host] = {"bind": FAKE_HOME_GUEST, "mode": "rw"}
            envs["HOME"] = FAKE_HOME_GUEST

        PWD = "/pwd"
        # volumes[f'{fake_home}/.docker'] = f'{home}/.docker', False
        volumes2[pwd1] = {"bind": PWD, "mode": "ro"}
        volumes2[f"/var/run/docker.sock"] = {"bind": "/var/run/docker.sock", "mode": "rw"}
        volumes2["/tmp"] = {"bind": "/tmp", "mode": "rw"}
        if development:
            dev_volumes = get_developer_volumes()
            if not dev_volumes:
                logger.warning("development active but no mounts found")
            volumes2.update(dev_volumes)

        name, _, tag = image.rpartition(":")

        if pull:
            logger.info("Updating container %s" % image)

            logger.info("This might take some time.")
            client.images.pull(name, tag)
        #
        try:
            container = client.containers.get(container_name)
        except:
            pass
        else:
            logger.error(f"stopping previous {container_name}")
            container.stop()
            logger.error(f"removing {container_name}")
            container.remove()

        logger.info(f"Starting container {container_name} with {image}")

        detach = True

        # add all the groups
        on_mac = "Darwin" in platform.system()
        if on_mac:
            group_add = []
        else:
            group_add = [g.gr_gid for g in grp.getgrall() if getpass.getuser() in g.gr_mem]

        interactive = False
        if shell:
            interactive = True
            detach = False
            commands = ["/bin/bash", "-l"]

        prefix = container_name + "_children"

        envs["CONTAINER_PREFIX"] = prefix

        params = dict(
            working_dir=PWD,
            user=f"{uid1}",
            group_add=group_add,
            command=commands,
            entrypoint=entrypoint,
            tty=interactive,
            volumes=volumes2,
            environment=envs,
            network_mode="host",
            detach=detach,
            name=container_name,
        )
        logger.info("Parameters:\n%s" % json.dumps(params, indent=4))
        if detach:
            params["remove"] = False
            container = client.containers.run(image, **params)

            continuously_monitor(client, container_name, log=logname)
            # logger.info(f'status: {container.status}')
            try:
                res = container.wait()
            except NotFound:
                message = "Interrupted"
                cleanup(client, prefix)
                return GenericDockerRunOutput(retcode=0, message=message)
                # not found; for example, CTRL-C

            #  {'Error': None, 'StatusCode': 32
            StatusCode = res["StatusCode"]
            Error = res["Error"]
            if StatusCode:
                logger.error(f"StatusCode: {StatusCode} Error: {Error}")
            else:
                logger.debug(f"StatusCode: {StatusCode} Error: {Error}")
            if Error is None:
                Error = f"Container exited with code {StatusCode}"

            cleanup(client, prefix)
            return GenericDockerRunOutput(retcode=StatusCode, message=Error)

        else:
            params["remove"] = True
            client.containers.run(image, **params)
            cleanup(client, prefix)
            return GenericDockerRunOutput(0, "")


def cleanup(client: DockerClient, prefix: str):
    logger.info(f"cleaning up containers with prefix {prefix}")
    containers = client.containers.list()
    container: Container
    for container in containers:
        n = container.name
        if n.startswith(prefix):
            msg = f"Will cleanup child container {n}"
            logger.info(msg)
            try:
                logger.info(f"stopping {n}")
                container.stop()
            except:
                logger.error(traceback.format_exc())
            logger.info(f"removing {n}")
            container.remove()


def get_developer_volumes(dirname: str = None) -> Dict[str, dict]:
    if dirname is None:
        V = "DT_ENV_DEVELOPER"
        dirname = os.environ.get(V, None)
        if not dirname:
            logger.debug(f"Did not find {V} - not mounting inside")
            return {}

    import yaml
    import glob

    res = {}
    files = list(glob.glob(os.path.join(dirname, "*.mount.yaml")))
    if not files:
        logger.warning(f"Did not find any mount.yaml files.")
        return {}
    for name in files:
        with open(name) as f:
            data = f.read()
        contents = yaml.load(data, Loader=yaml.Loader)
        # assume list
        for entry in contents:
            host = entry["host"]
            guest = entry["guest"]
            host = os.path.expandvars(host)

            # local = os.path.join(val, local)
            exists = os.path.exists(host)
            logger.info(f"{exists} {host} -> {guest}")
            if exists:
                res[host] = {"bind": guest, "mode": "ro"}

    return res


def get_args_for_env(envs: Dict[str, str]) -> List[str]:
    args = []
    for k, v in envs.items():
        args.append("-e")
        args.append(f"{k}={v}")

    return args


if __name__ == "__main__":
    envs = get_developer_volumes()

    volumes = [f'{k}:{v["bind"]}:{v["mode"]}' for k, v in envs.items()]
    print("\n- ".join(volumes))

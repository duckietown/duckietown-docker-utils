import getpass
import grp
import json
import os
import platform
import sys
from dataclasses import dataclass
from tempfile import TemporaryDirectory
from typing import Dict, List, Optional

from docker.errors import NotFound
from zuper_commons.types import ZValueError

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
    client,
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
    logger.debug(f"using image {image}")
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
        credentials = os.path.join(tmpdir, "credentials")
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
            logger.error("stopping previous %s" % container_name)
            container.stop()
            logger.error("removing")
            container.remove()

        logger.info("Starting container %s with %s" % (container_name, image))

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
                return GenericDockerRunOutput(retcode=0, message=message)
                # not found; for example, CTRL-C

            #  {'Error': None, 'StatusCode': 32
            StatusCode = res["StatusCode"]
            Error = res["Error"]

            logger.info(f"StatusCode: {StatusCode} Error: {Error}")
            if Error is None:
                Error = f"Container exited with code {StatusCode}"
            return GenericDockerRunOutput(retcode=StatusCode, message=Error)

        else:
            params["remove"] = True
            client.containers.run(image, **params)
            return GenericDockerRunOutput(0, "")


def get_developer_volumes() -> Dict[str, dict]:
    V = "DT_ENV_DEVELOPER"
    val = os.environ.get(V, None)
    if not val:
        return {}

    prefix1 = "/usr/local/lib/python3.8/dist-packages/"

    wda = [
        (f"{val}/src/duckietown-world/src", ["duckietown_world"]),
        (f"{val}/src/duckietown-challenges/src", ["duckietown_challenges"]),
        (f"{val}/src/duckietown-challenges-cli/src", ["duckietown_challenges_cli"]),
        (f"{val}/src/duckietown-challenges-runner/src", ["duckietown_challenges_runner"]),
        (f"{val}/src/duckietown-docker-utils/src", ["duckietown_docker_utils"]),
        (f"{val}/src/duckietown-world/src", ["duckietown_world"]),
        (f"{val}/src/duckietown-shell/src", ["dt_shell"]),
        (f"{val}/src/duckietown-tokens/src", ["duckietown_tokens"]),
        (f"{val}/src/gym-duckietown/src", ["gym_duckietown"]),
        (f"{val}/src/aido-agents/src", ["aido_agents"]),
        (f"{val}/src/aido-analyze/src", ["aido_analyze"]),
        (f"{val}/src/aido-protocols/src", ["aido_schemas"]),
        (f"{val}/src/aido-utils/src", ["aido_utils"]),
    ]

    res = {}
    for local, inside_packages in wda:
        local = os.path.join(val, local)
        exists = os.path.exists(local)
        logger.info(f"{exists} {local}")
        if exists:
            for pn in inside_packages:
                d = os.path.join(local, pn)
                if not os.path.exists(d):
                    msg = f"Expect {d}"

                    raise ZValueError(msg)

                t1 = os.path.join(prefix1, pn)
                # t2 = os.path.join(prefix2, pn)
                res[d] = {"bind": t1, "mode": "ro"}
                # res[d] =  {'bind': t2, 'mode': 'ro'}

    return res


def get_args_for_env(envs: Dict[str, str]) -> List[str]:
    args = []
    for k, v in envs.items():
        args.append("-e")
        args.append(f"{k}={v}")

    return args

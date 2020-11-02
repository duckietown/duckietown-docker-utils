import datetime
import getpass
import grp
import json
import os
import platform
import random
import shutil
import subprocess
import sys
import time
import traceback
from dataclasses import dataclass
from tempfile import TemporaryDirectory
from typing import Dict, List, Optional

from docker import DockerClient
from docker.errors import ContainerError, NotFound
from docker.models.containers import Container
from duckietown_docker_utils.terminal_size import get_screen_columns
from progressbar import Bar, ETA, Percentage, ProgressBar

from . import logger
from .constants import CONFIG_DOCKER_PASSWORD, CONFIG_DOCKER_USERNAME, DT1_TOKEN_CONFIG_KEY, IMPORTANT_ENVS
from .monitoring import continuously_monitor

__all__ = ["GenericDockerRunOutput", "generic_docker_run", "get_developer_volumes"]


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
    detach: bool = True,
    read_only: bool = True,
) -> GenericDockerRunOutput:

    image = replace_important_env_vars(image)
    # logger.debug(f"using image: {image}")
    # logger.debug(f"development: {development}")
    pwd = os.getcwd()

    pwd1 = os.path.realpath(pwd)
    user = getpass.getuser()

    try:
        repo_root = subprocess.check_output(["git", "rev-parse", "--show-toplevel"]).decode().strip()
    except Exception as e:
        msg = f"Cannot get repo_root from {pwd1}: \n{e}"

        pwd_to_share = pwd
    else:
        logger.info(f"repo_root = {repo_root}")
        pwd_to_share = repo_root

    volumes2: Dict[str, dict] = {}
    envs = {}
    for k, default in IMPORTANT_ENVS.items():
        envs[k] = os.environ.get(k, default)

    contents = {
        CONFIG_DOCKER_USERNAME: docker_username,
        CONFIG_DOCKER_PASSWORD: docker_secret,
        DT1_TOKEN_CONFIG_KEY: dt1_token,
    }
    FAKE_HOME_GUEST = "/fake-home"
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

        # PWD = "/pwd"
        PWD = pwd1
        # volumes[f'{fake_home}/.docker'] = f'{home}/.docker', False
        volumes2[pwd_to_share] = {"bind": pwd_to_share, "mode": "ro" if read_only else "rw"}
        volumes2[f"/var/run/docker.sock"] = {"bind": "/var/run/docker.sock", "mode": "rw"}
        volumes2["/tmp"] = {"bind": "/tmp", "mode": "rw"}

        gitconfig = os.path.expanduser("~/.gitconfig")
        if os.path.exists(gitconfig):
            shutil.copy(gitconfig, os.path.join(fake_home_host, ".gitconfig"))
        if development:
            dev_volumes = get_developer_volumes()
            if not dev_volumes:
                logger.warning("development active but no mounts found")

            else:
                DED = os.environ.get("DT_ENV_DEVELOPER")
                if os.path.exists(DED):
                    dev_volumes[DED] = {"bind": DED, "mode": "ro"}
                    envs["DT_MOUNT"] = "1"
                else:
                    logger.error(f"could not find {DED}")

            volumes2.update(dev_volumes)

        envs["PROGRESSBAR_LINE_BREAKS"] = "1"
        envs["PROGRESSBAR_ENABLE_COLORS"] = "1"
        # if "COLUMNS" in os.environ:
        #     envs["COLUMNS"] = os.environ["COLUMNS"]
        envs["COLUMNS"] = str(get_screen_columns())

        name, _, tag = image.rpartition(":")

        if pull:
            do_it = should_pull(image, 60 * 10)

            if do_it:
                pull_image(client, image, progress=True)

        #
        try:
            container = client.containers.get(container_name)
        except:
            pass
        else:
            # logger.error(f"stopping previous {container_name}")
            container.stop()
            # logger.error(f"removing {container_name}")
            container.remove()

        # logger.info(f"Starting container {container_name} with {image}")

        # add all the groups
        on_mac = "Darwin" in platform.system()
        if on_mac:
            group_add = []
        else:
            group_add = [g.gr_gid for g in grp.getgrall() if getpass.getuser() in g.gr_mem]

        interactive = True
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
        # logger.error("Parameters:\n%s" % json.dumps(params, indent=4))
        # return
        if detach:
            params["remove"] = False
            container = client.containers.run(image, **params)

            continuously_monitor(client, container_name, log=logname)
            # logger.info(f'status: {container.status}')
            try:
                res = container.wait()
            except NotFound:
                message = "Interrupted"
                cleanup(client, container_name=container_name, prefix=prefix)
                return GenericDockerRunOutput(retcode=0, message=message)
                # not found; for example, CTRL-C

            #  {'Error': None, 'StatusCode': 32
            StatusCode = res["StatusCode"]
            Error = res["Error"]
            if StatusCode:
                logger.error(f"StatusCode: {StatusCode} Error: {Error}")
            else:
                pass
                # logger.debug(f"StatusCode: {StatusCode} Error: {Error}")
            if Error is None:
                Error = f"Container exited with code {StatusCode}"

            cleanup(client, container_name=container_name, prefix=prefix)
            return GenericDockerRunOutput(retcode=StatusCode, message=Error)

        else:
            params["remove"] = True
            # params['detach'] = False
            try:
                logger.info("starting run")

                logger.info(json.dumps(params))
                for line in client.containers.run(image, **params, stream=True, stderr=True):
                    sys.stderr.write(line.decode())
            except ContainerError as e:
                # msg = 'Container run failed'
                # msg += f'\n exit status: {e.exit_status}'
                sys.stderr.write(e.stderr.decode() + "\n")
                # msg += '\n' + indent(e.stderr.decode(), 'stderr > ')
                sys.exit(e.exit_status)
                # raise Exception(msg)
            finally:
                cleanup(client, container_name=None, prefix=prefix)
            return GenericDockerRunOutput(0, "")

    #


def cleanup(client: DockerClient, container_name: Optional[str], prefix: str):
    cleanup_children(client, prefix)
    if container_name:
        try:
            c = client.containers.get(container_name)
        except NotFound:
            pass
        else:
            c.remove()


import sqlite3


def should_pull(image_name: str, period: float):
    while True:
        try:
            return should_pull_(image_name, period)
        except sqlite3.OperationalError:

            s = random.uniform(0.1, 2)
            logger.warning(f"db locked, trying again in {s:.1f}s")
            time.sleep(s)


def should_pull_(image_name: str, period: float) -> bool:
    fn = "/tmp/pulls.sqlite"
    conn = sqlite3.connect(fn)
    c = conn.cursor()

    sql = """

        CREATE TABLE IF NOT EXISTS pulls (
            image_name text not null primary key,
            last_pull timestamp  not null
        );

            """
    c.execute(sql)
    conn.commit()
    sql = """
        select last_pull from pulls where image_name = ?
    """
    c.execute(sql, (image_name,))
    data = c.fetchone()
    n = datetime.datetime.now()

    if not data:
        sql = """
                insert into pulls (image_name, last_pull) values (?, ?);
            """
        c.execute(sql, (image_name, n))
        conn.commit()
        conn.close()
        return True
    else:
        (last,) = data
        # 3 '2020-10-29 22:31:12.531695'
        datelast = datetime.datetime.strptime(last, "%Y-%m-%d %H:%M:%S.%f")

        diff = n - datelast
        s = diff.total_seconds()
        if s > period:
            sql = """
                update  pulls set last_pull = ? where image_name = ?;
            """
            c.execute(sql, (n, image_name))
            conn.commit()
            conn.close()

            logger.debug(f"Need to pull {image_name} because passed {int(s)} > {period} seconds.")
            return True
        else:
            logger.debug(f"No need to pull {image_name}; passed only {int(s)}  < {period} seconds.")
            conn.close()


def cleanup_children(client, prefix):
    # logger.info(f"cleaning up containers with prefix {prefix}")
    containers = client.containers.list(ignore_removed=True)
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
        # if len(total_layers) > 0:
        progress = int(100 * len(completed_layers) / max(1, len(total_layers)))
        pbar.update(progress)
        sys.stderr.flush()
    pbar.update(100)
    sys.stderr.flush()

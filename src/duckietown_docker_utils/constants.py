DT1_TOKEN_CONFIG_KEY = "token_dt1"
CONFIG_DOCKER_USERNAME = "docker_username"
CONFIG_DOCKER_CREDENTIALS = "docker_credentials"
CONFIG_DUCKIETOWN_VERSION = "duckietown_version"

CONFIG_DOCKER_PASSWORD = "docker_password"

ENV_REGISTRY = "DOCKER_REGISTRY"

ENV_IGNORE_DIRTY = "DT_IGNORE_DIRTY"
ENV_IGNORE_UNTAGGED = "DT_IGNORE_UNTAGGED"

ENV_DT_BUILD_HOST = "DT_DOCKER_BUILD_HOST"

# These are passed to the called container.
# If the value is None, no variable is passed if one is not present.
IMPORTANT_ENVS = {
    ENV_REGISTRY: "docker.io",
    "PIP_INDEX_URL": "https://pypi.org/simple",
    "DTSERVER": "https://challenges.duckietown.org/v4",
    ENV_IGNORE_UNTAGGED: None,
    ENV_IGNORE_DIRTY: None,
}


DEPTH_VAR = "DOCKER_DEPTH"
CREDENTIALS_FILE = "/credentials"

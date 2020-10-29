from setuptools import setup


def get_version(filename: str):
    import ast

    version = None
    with open(filename) as f:
        for line in f:
            if line.startswith("__version__"):
                version = ast.parse(line).body[0].value.s
                break
        else:
            raise ValueError("No version found in %r." % filename)
    if version is None:
        raise ValueError(filename)
    return version


version = get_version(filename="src/duckietown_docker_utils/__init__.py")

install_requires = ["requirements-parser", "packaging", "pytz", "whichcraft", "progressbar"]

line = "daffy"

setup(
    name=f"duckietown-docker-utils-{line}",
    version=version,
    keywords="",
    package_dir={"": "src"},
    packages=["duckietown_docker_utils"],
    install_requires=install_requires,
    entry_points={"console_scripts": ["dt-docker-push=duckietown_docker_utils.dt_push:dt_push_main",],},
)

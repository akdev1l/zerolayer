#!/usr/bin/env python3
from pathlib import Path
from rich.console import Console  # type: ignore
from rich.table import Table  # type: ignore
from typing_extensions import Annotated
import subprocess as sp
import json
import shutil
import typer  # type: ignore
import logging
import os
import datetime
import math
import hashlib
import inquirer  # type: ignore

app = typer.Typer()
app_state = {"dry_run": False}

IMAGE_DIR = Path(os.environ.get("ZEROLAYER_IMAGE_DIR", "/var/cache/zerolayer"))
CONTAINERFILE_PATH = Path(
    os.environ.get("ZEROLAYER_CONTAINERFILE_DIR", "/etc/zerolayer/")
)

CYAN_COLOR = "\033[96m"
BLUE_COLOR = "\033[94m"
DEFAULT_TEXT_COLOR = "\033[0m"

DEFAULT_PREFIX = f"{CYAN_COLOR}[ZEROLAYER]{DEFAULT_TEXT_COLOR}"
DRY_RUN_PREFIX = f"{BLUE_COLOR}[DRY_RUN]{DEFAULT_TEXT_COLOR}"
CURRENT_ENVIRONMENT_NAME = "current"
GENERIC_COOL_NAME_FOR_IMAGES: str = "boot_env"
IMAGE_ARCHIVE_EXTENSION = "tar.gz"


def get_valid_image_files(cache_dir: Path, no_current: bool = True) -> list[Path]:
    valid_files = []
    for path in Path(cache_dir).iterdir():
        full_file_name = path.name.split(".")
        if GENERIC_COOL_NAME_FOR_IMAGES in full_file_name[0]:
            if (
                no_current and full_file_name[1] == CURRENT_ENVIRONMENT_NAME
            ) or path.is_dir():
                continue

            valid_files.append(path)
    return valid_files


def generate_hash_from_date(s: str):
    return int(hashlib.sha256(s.encode("utf-8")).hexdigest(), 16) % 10**8


def convert_size(size_bytes):
    if size_bytes == 0:
        return "0B"
    size_name = ("B", "KB", "MB", "GB")
    i = int(math.floor(math.log(size_bytes, 1024)))
    p = math.pow(1024, i)
    s = round(size_bytes / p, 2)
    return "%s %s" % (s, size_name[i])


def get_current_image() -> str:
    out = sp.run("rpm-ostree status --json", shell=True, stdout=sp.PIPE).stdout
    return json.loads(out)["deployments"][0]["container-image-reference"]


@app.command(name="list")
def list_environments(
    cache_dir: Path = IMAGE_DIR,
    max_shown: int = 0,
    ignore_current: Annotated[
        bool, typer.Option("--ignore-current", help="Ignores the Current selected environment")
    ] = False,
) -> None:
    """
    List all available environments + optionally the latest (current) one in a table.
    """
    if not Path(cache_dir).exists():
        logging.fatal(f"{DEFAULT_PREFIX} Failed to find image directory")
        return

    table_list = Table("Filename", "Hash", "Size", "Creation Time")
    envs_found = 0

    for path in Path(cache_dir).iterdir():
        if envs_found == max_shown and max_shown != 0:
            break
        full_file_name = path.name.split(".")
        if GENERIC_COOL_NAME_FOR_IMAGES in full_file_name[0]:
            if path.is_dir():
                continue

            if ignore_current and full_file_name[1] == CURRENT_ENVIRONMENT_NAME:
                envs_found += 1
                continue

            table_list.add_row(
                path.name,
                full_file_name[1],
                convert_size(path.stat().st_size),
                str(datetime.datetime.fromtimestamp(path.stat().st_mtime)),
            )

            envs_found += 1

    if envs_found == 0:
        logging.warning(f"{DEFAULT_PREFIX} Could not find any valid environments")
        return

    Console().print(table_list)


@app.command()
def clear(
    cache_dir: Path = IMAGE_DIR,
    all: Annotated[bool, typer.Option(help="Selects all environments")] = False,
    no_confirm: Annotated[bool, typer.Option("--no-confirm")] = False,
    list_size: Annotated[
        int, typer.Option(help="List size for selecting environment")
    ] = 0,
):
    """
    Delete selected (or all) environments in selected cache directory
    """
    if app_state["dry_run"]:
        logging.info(
            f"{DRY_RUN_PREFIX} Delete everything (or selected image) from {cache_dir}"
        )
        return

    if not Path(cache_dir).exists():
        logging.fatal(f"{DEFAULT_PREFIX} Failed to find image directory")
        return

    valid_files: list[Path] = get_valid_image_files(cache_dir)
    if valid_files == []:
        logging.warning(f"{DEFAULT_PREFIX} Could not find any environment")
        return

    if all:
        logging.warning(
            f"{DEFAULT_PREFIX} Affected environments:\n\t"
            + "\n\t".join([file.name for file in valid_files])
            + "\n"
        )

        are_you_sure: bool = False
        if no_confirm:
            are_you_sure = True
        else:
            are_you_sure = typer.confirm(
                "Are you sure you want to delete all environments?", abort=True
            )

        if not are_you_sure:
            raise typer.Abort()

        for path in valid_files:
            if path.is_dir():
                shutil.rmtree(path)
            path.unlink()
        return

    list_environments(cache_dir, list_size, ignore_current=True)
    if list_size > 0:
        logging.warning(f"{DEFAULT_PREFIX} Results truncated to {list_size} results.")

    try:
        selected_env = inquirer.prompt(
            [
                inquirer.List(
                    "environment",
                    message="Which environment do you want to delete?",
                    choices=[str(x.name.split(".")[1]) for x in valid_files],
                )
            ]
        )["environment"]
    except (TypeError, KeyboardInterrupt):
        raise typer.Abort()

    if selected_env is None:
        raise typer.Abort()

    r_you_sure: bool = False
    if no_confirm:
        r_you_sure = True
    else:
        r_you_sure = typer.confirm(
            "Are you sure you want to delete the selected environment?", abort=True
        )

    if not r_you_sure:
        raise typer.Abort()

    logging.warning(f"{DEFAULT_PREFIX} Deleting selected environment")

    for file in valid_files:
        if file.name.split(".")[1] == selected_env:
            try:
                file.unlink()
            except OSError:
                logging.fatal(f"{DEFAULT_PREFIX} Failed deleting selected environment")
                exit(1)
            logging.warning(f"{DEFAULT_PREFIX} Environment deleted successfully")
            return

    logging.fatal(f"{DEFAULT_PREFIX} Could not delete selected environment")
    raise typer.Exit(1)


@app.command()
def build(
    containerfile_path: Path = CONTAINERFILE_PATH,
    cache_dir: Path = IMAGE_DIR,
    build_arg: Annotated[list[str], typer.Option()] = [],
):
    """
    Build a boot environment from CONTAINERFILE_PATH

    BUILD_ARG works just like podman --build-args works, you can use it multiple times for multiple arguments
    """
    if app_state["dry_run"]:
        logging.info(f'{DRY_RUN_PREFIX} Create "{cache_dir}" and parent directories')
        logging.info(
            f"{DRY_RUN_PREFIX} Create oci archive in {cache_dir} using {containerfile_path}"
        )
        logging.info(f"{DRY_RUN_PREFIX} Unlinking current environment")
        logging.info(f"{DRY_RUN_PREFIX} Symlinking generated file to current")
        return

    if not cache_dir.exists():
        logging.warning(
            f'{DEFAULT_PREFIX} Creating "{cache_dir}" and parent directories'
        )
        try:
            cache_dir.mkdir(parents=True)
        except PermissionError:
            logging.fatal(
                f"Could not create {cache_dir} due to permission errors. Are you not root?"
            )
            raise typer.Exit(1)
        except OSError:
            logging.fatal(f"Failed creating {cache_dir}")
            raise typer.Exit(1)

    TARGET_FILE_NAME = f"{cache_dir.resolve()}/{GENERIC_COOL_NAME_FOR_IMAGES}.{generate_hash_from_date(str(datetime.datetime.now()))}.{IMAGE_ARCHIVE_EXTENSION}"

    logging.warning(f"{DEFAULT_PREFIX} Creating oci archive in {cache_dir}")

    build_args: list[str] = []
    if build_arg != []:
        build_args = ["--build-arg=" + arg for arg in build_arg]

    try:
        build_cmd = sp.run(
            [
                "podman",
                "build",
            ]
            + build_args
            + ["-t", f"oci-archive:{TARGET_FILE_NAME}", containerfile_path]
        )
    except FileNotFoundError:
        logging.fatal(
            f"{DEFAULT_PREFIX} Failed to run Podman for building, do you have it in your PATH?"
        )
        raise typer.Exit(1)

    if build_cmd.returncode != 0:
        logging.fatal(
            f"{DEFAULT_PREFIX} Failed building, check journalctl for other logs"
        )
        raise typer.Exit(1)

    logging.warning(f"{DEFAULT_PREFIX} Unlinking current environment")
    for file in Path(cache_dir).iterdir():
        full_file_name = file.name.split(".")
        if (
            GENERIC_COOL_NAME_FOR_IMAGES in full_file_name[0]
            and full_file_name[1] == CURRENT_ENVIRONMENT_NAME
        ):
            file.unlink(missing_ok=True)

    logging.warning(f"{DEFAULT_PREFIX} Symlinking generated file to current")
    Path(
        f"{cache_dir}/{GENERIC_COOL_NAME_FOR_IMAGES}.{CURRENT_ENVIRONMENT_NAME}.{IMAGE_ARCHIVE_EXTENSION}"
    ).symlink_to(TARGET_FILE_NAME)


@app.command()
def rebase(
    cache_dir: Path = IMAGE_DIR,
    no_confirm: Annotated[bool, typer.Option("--no-confirm")] = False,
    image_hash: str = "",
) -> None:
    """
    Rebase your system over to the chosen boot environment
    """
    if app_state["dry_run"]:
        logging.info(f"{DRY_RUN_PREFIX} Rebase to selected image or current (default)")
        switch(cache_dir, "EXAMPLE")
        return

    valid_files: list[Path] = get_valid_image_files(cache_dir, no_current=False)
    if valid_files == []:
        logging.warning(f"{DEFAULT_PREFIX} Could not find any environment")
        return

    if no_confirm:
        selected_env = CURRENT_ENVIRONMENT_NAME
    else:
        try:
            selected_env = inquirer.prompt(
                [
                    inquirer.List(
                        "environment",
                        message="Which environment do you want to rebase to?",
                        choices=[str(x.name.split(".")[1]) for x in valid_files],
                    )
                ]
            )["environment"]
        except (TypeError, KeyboardInterrupt):
            raise typer.Abort()

        if selected_env is None:
            raise typer.Abort()

    logging.warning(f"{DEFAULT_PREFIX} Rebasing to {selected_env}")
    try:
        rpm_ostree_call = sp.run(
            [
                "rpm-ostree",
                "rebase",
                f"ostree-unverified-image:oci-archive:{cache_dir}/{GENERIC_COOL_NAME_FOR_IMAGES}.{selected_env}.{IMAGE_ARCHIVE_EXTENSION}",
            ]
        )
    except FileNotFoundError:
        logging.fatal(
            f"{DEFAULT_PREFIX} Failed finding rpm-ostree, most likely a PATH error."
        )
        raise typer.Exit(1)

    if rpm_ostree_call.returncode != 0:
        logging.fatal(
            f"{DEFAULT_PREFIX} Failed rebasing to selected image. Consult journalctl for more logs"
        )
        raise typer.Exit(1)

    if selected_env != CURRENT_ENVIRONMENT_NAME:
        switch(cache_dir, selected_env)


@app.command()
def init(
    url: Annotated[
        str, typer.Option(help="URL that will be cloned to TARGET_DIR")
    ] = "https://github.com/ublue-os/startingpoint",
    target_dir: Path = CONTAINERFILE_PATH,
    no_confirm: Annotated[bool, typer.Option("--no-confirm")] = False,
):
    """
    Initialize a source directory for Zerolayer
    """
    if app_state["dry_run"]:
        logging.info(f"{DRY_RUN_PREFIX} Delete everything from {target_dir}")
        logging.info(f"{DRY_RUN_PREFIX} Clone {url} to {target_dir}")
        return

    if target_dir.exists() and len(os.listdir(target_dir)) > 0:
        are_you_sure: bool = False
        if no_confirm:
            are_you_sure = True
        else:
            are_you_sure = typer.confirm(
                f"Are you sure you want to delete everything from {target_dir}",
                abort=True,
            )

        if not are_you_sure:
            return

        deleted_files = [str(file) for file in target_dir.iterdir()]

        shutil.rmtree(target_dir)

        logging.warning(
            f"{DEFAULT_PREFIX} Affected files:\n\t" + "\n\t".join(deleted_files) + "\n"
        )

    try:
        gitclone = sp.run(["git", "clone", url, str(target_dir)])
    except FileNotFoundError:
        logging.fatal(f"{DEFAULT_PREFIX} Could not run Git, is it in your PATH?")
        exit(1)

    if gitclone.returncode != 0:
        logging.fatal(f"{DEFAULT_PREFIX} Failed to initialize in {target_dir}")
        exit(1)

    logging.warning(f"{DEFAULT_PREFIX} Initialized successfully in {target_dir}")


@app.command()
def switch(cache_dir: Annotated[Path, typer.Option("--cache-dir", "-c")] = IMAGE_DIR, image_hash: str = ""):
    """
    Switch the current environment symlink over to selected image
    """
    if app_state["dry_run"]:
        logging.info(f"{DRY_RUN_PREFIX} Unlink old current environment")
        logging.info(f"{DRY_RUN_PREFIX} Link selected environment to current")
        return

    valid_files: list[Path] = get_valid_image_files(cache_dir)
    if valid_files == []:
        logging.warning(f"{DEFAULT_PREFIX} Could not find any environment")
        return

    if image_hash != "":
        selected_hash = image_hash
    else:
        list_environments(cache_dir, 0, ignore_current=True)
        try:
            selected_hash = inquirer.prompt(
                [
                    inquirer.List(
                        "environment",
                        message="Which environment do you want to switch to?",
                        choices=[str(x.name.split(".")[1]) for x in valid_files],
                    )
                ]
            )["environment"]
        except (TypeError, KeyboardInterrupt):
            raise typer.Abort()

        if selected_hash is None:
            raise typer.Abort()

    CURRENT_ENV_FILE = Path(
        f"{cache_dir}/{GENERIC_COOL_NAME_FOR_IMAGES}.{CURRENT_ENVIRONMENT_NAME}.{IMAGE_ARCHIVE_EXTENSION}"
    )

    if CURRENT_ENV_FILE.exists():
        logging.warning(f"{DEFAULT_PREFIX} Unlinking old current symlink")
        CURRENT_ENV_FILE.unlink()

    found_env = False
    target_env: Path = Path()
    for file in valid_files:
        if file.name.split(".")[1] == selected_hash:
            found_env = True
            target_env = file

    if not found_env:
        logging.fatal(f"{DEFAULT_PREFIX} Failed to find environment")
        raise typer.Exit(1)

    CURRENT_ENV_FILE.symlink_to(target_env)
    proper_final_hash = target_env.name.split(".")[1]
    logging.warning(
        f"{DEFAULT_PREFIX} Switched current environment to {proper_final_hash}"
    )


@app.callback()
def app_config(
    quiet: Annotated[bool, typer.Option("--quiet", "-q", help="Minimal logging")] = False,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Only log what the program would do"),
    ] = False,
):
    logging.basicConfig(format="", level=logging.NOTSET)

    if quiet:
        logging.getLogger().setLevel(logging.CRITICAL)

    app_state["dry_run"] = dry_run


def main():
    app()


if __name__ == "__main__":
    main()

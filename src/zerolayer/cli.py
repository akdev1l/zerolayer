#!/usr/bin/env python3
import subprocess as sp
from pathlib import Path
import json
import typer
import logging
import os
import datetime
import math

app = typer.Typer()
app_state = {"dry_run": False}

IMAGE_DIR = Path(os.environ.get("ZEROLAYER_IMAGE_DIR", "/var/cache/zerolayer"))
CONTAINERFILE_PATH = Path(os.environ.get(
    "ZEROLAYER_CONTAINERFILE_DIR", "/etc/zerolayer/Containerfile"))

DEFAULT_PREFIX = "[ZEROLAYER]"
DRY_RUN_PREFIX = "[DRY_RUN]"
IMAGE_ARCHIVE_PATH = Path(f"{IMAGE_DIR}/current_image.tar.gz")
CLEANUP_CMD = ["rm", "-rf", f"{IMAGE_DIR}/*"]
CURRENT_ENVIRONMENT_NAME = "current"


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


@app.command()
def list_images(cache_dir: Path = IMAGE_DIR) -> None:
    if not Path(cache_dir).exists():
        logging.fatal("Failed to find image directory")
        return

    were_envs_found = False
    # e.g.: boot_env.1.tar.gz boot_env.2.tar.gz boot_env.current.tar.gz
    GENERIC_COOL_NAME_FOR_IMAGES: str = "boot_env"
    for path in Path(cache_dir).iterdir():
        full_file_name = path.name.split(".")
        if GENERIC_COOL_NAME_FOR_IMAGES in full_file_name[0]:
            if not full_file_name[1].isnumeric() and not full_file_name[1] == CURRENT_ENVIRONMENT_NAME:
                logging.fatal(f"Invalid naming scheme for file {path.name}")
                return
            
            logging.warning(f"Environment {full_file_name[1]}:\n\tSize: {convert_size(path.stat().st_size)}\n\tCreation Time: {datetime.datetime.fromtimestamp(path.stat().st_mtime)}")
            were_envs_found = True

    if not were_envs_found:
        logging.warning("Could not find any valid environments")

@app.command()
def build_image(
        containerfile: Path = CONTAINERFILE_PATH,
        cache_dir: Path = IMAGE_DIR,
        delete_cache: bool = False):
    if app_state["dry_run"]:
        logging.info(f"{DRY_RUN_PREFIX} Create \"{cache_dir}\" and parent directories")
        logging.info(f"{DRY_RUN_PREFIX} Delete everything from {cache_dir}")
        logging.info(f"{DRY_RUN_PREFIX} Create oci archive in {cache_dir} using {containerfile}")
        exit(0)

    if not cache_dir.exists():
        logging.warning(f"{DEFAULT_PREFIX} Creating \"{cache_dir}\" and parent directories")
        try:
            cache_dir.mkdir(parents=True)
        except PermissionError:
            logging.fatal(f"Could not create {cache_dir} due to permission errors. Are you not root?")
            exit(1)

    if delete_cache:
        logging.warning(
            f"{DEFAULT_PREFIX} Deleting everything from {cache_dir}")
        sp.run(CLEANUP_CMD)

    logging.warning(
        f"{DEFAULT_PREFIX} Creating oci archive in {cache_dir}")
    sp.run(["buildah",
            "bud",
            "-t",
            f"oci-archive:{cache_dir}",
            containerfile])


@app.command()
def rebase_to_image() -> None:
    FULL_IMAGE: str = f"ostree-unverified-image:oci-archive:{IMAGE_ARCHIVE_PATH}"
    
    if (app_state["dry_run"]):
        logging.info(f"{DRY_RUN_PREFIX} Rebase to {FULL_IMAGE}")
        return
    
    logging.warning(f"{DEFAULT_PREFIX} Rebasing to {FULL_IMAGE}")
    if (get_current_image() != FULL_IMAGE):
        sp.run(["rpm-ostree", "rebase", FULL_IMAGE])


@app.callback()
def app_config(quiet: bool = False, dry_run: bool = False):
    logging.basicConfig(format="", level=logging.NOTSET)

    if quiet:
        logging.getLogger().setLevel(logging.CRITICAL)

    app_state["dry_run"] = dry_run


@app.command()
def all(rebase: bool = True) -> int:
    build_image(CONTAINERFILE_PATH, IMAGE_DIR)
    if (rebase):
        rebase_to_image()

    return 0


def main():
    app()


if __name__ == "__main__":
    main()

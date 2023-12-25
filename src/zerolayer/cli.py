#!/usr/bin/env python3
import subprocess as sp
from pathlib import Path
import json
import typer
import logging
import os
import datetime
import math
from typing import List
from rich.prompt import Prompt

app = typer.Typer()
app_state = {"dry_run": False}

IMAGE_DIR = Path(os.environ.get("ZEROLAYER_IMAGE_DIR", "/var/cache/zerolayer"))
CONTAINERFILE_PATH = Path(os.environ.get(
    "ZEROLAYER_CONTAINERFILE_DIR", "/etc/zerolayer/Containerfile"))

DEFAULT_PREFIX = "[ZEROLAYER]"
DRY_RUN_PREFIX = "[DRY_RUN]"
IMAGE_ARCHIVE_PATH = Path(f"{IMAGE_DIR}/current_image.tar.gz")
CURRENT_ENVIRONMENT_NAME = "current"
GENERIC_COOL_NAME_FOR_IMAGES: str = "boot_env"


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
def list_environments(cache_dir: Path = IMAGE_DIR, max_shown: int = 0) -> None:
    if not Path(cache_dir).exists():
        logging.fatal("Failed to find image directory")
        return

    envs_found = 0
    # e.g.: boot_env.1.tar.gz boot_env.2.tar.gz boot_env.current.tar.gz
    for path in Path(cache_dir).iterdir():
        if envs_found == max_shown and max_shown != 0:
                return
        full_file_name = path.name.split(".")
        if GENERIC_COOL_NAME_FOR_IMAGES in full_file_name[0]:
            if not full_file_name[1].isnumeric() and not full_file_name[1] == CURRENT_ENVIRONMENT_NAME:
                logging.fatal(f"Invalid naming scheme for file {path.name}")
                return
            
            logging.warning(f"Environment {full_file_name[1]}:\n\tSize: {convert_size(path.stat().st_size)}\n\tCreation Time: {datetime.datetime.fromtimestamp(path.stat().st_mtime)}")
            
            envs_found += 1

    if envs_found == 0:
        logging.warning("Could not find any valid environments")


@app.command()
def clear(cache_dir: Path = IMAGE_DIR, all: bool = False, no_confirm: bool = False):
    if app_state["dry_run"] and no_confirm is False:
        logging.info(f"{DRY_RUN_PREFIX} Delete everything from {cache_dir}")
        exit(0)

    if not Path(cache_dir).exists():
        logging.fatal("Failed to find image directory")
        return

    valid_files: List[Path] = [] 
    for path in Path(cache_dir).iterdir():
        full_file_name = path.name.split(".")
        if GENERIC_COOL_NAME_FOR_IMAGES in full_file_name[0]:
            if not full_file_name[1].isnumeric() and not full_file_name[1] == CURRENT_ENVIRONMENT_NAME:
                continue
    
            valid_files.append(path)

    if valid_files == []:
        logging.warning("Could not find any environment")
        return

    if all:
        logging.warning("Affected environments:\n\t" + "\n\t".join([file.name for file in valid_files]) + "\n")
        
        are_you_sure: bool = False 
        if no_confirm:
            are_you_sure = True
        else:
            are_you_sure = typer.confirm("Are you sure you want to delete all environments?", abort=True)
   
        if not are_you_sure:
            raise typer.Abort()

        for path in valid_files:
            path.unlink()
        return

    ENV_LIST = 3
    list_environments(cache_dir, ENV_LIST)
    print(f"Results truncated to {ENV_LIST} results.")

    selected_env: str = Prompt.ask("\nWhich environment do you want to delete?")

    deleting_message = "Are you sure you want to delete the selected environment?"

    if selected_env == CURRENT_ENVIRONMENT_NAME:
        deleting_message = "Are you sure you want to delete the current environment symlink? This will not delete the actual file"
         
    r_you_sure: bool = False 
    if no_confirm:
        r_you_sure = True
    else:
        r_you_sure = typer.confirm(deleting_message, abort=True)
   
    if not r_you_sure:
        raise typer.Abort()

    logging.warning("Deleting selected environment")
    
    for file in valid_files:
        if file.name.split(".")[1] == selected_env:
            try:
                file.unlink()
            except OSError:
                logging.fatal("Failed deleting selected environment")
                exit(1)
            logging.warning("Environment deleted successfully")
            return
    
    logging.warning("Could not delete selected environment")
    exit(1)



@app.command()
def build(
        containerfile: Path = CONTAINERFILE_PATH,
        cache_dir: Path = IMAGE_DIR
    ):
    if app_state["dry_run"]:
        logging.info(f"{DRY_RUN_PREFIX} Create \"{cache_dir}\" and parent directories")
        logging.info(f"{DRY_RUN_PREFIX} Create oci archive in {cache_dir} using {containerfile}")
        exit(0)

    if not cache_dir.exists():
        logging.warning(f"{DEFAULT_PREFIX} Creating \"{cache_dir}\" and parent directories")
        try:
            cache_dir.mkdir(parents=True)
        except PermissionError:
            logging.fatal(f"Could not create {cache_dir} due to permission errors. Are you not root?")
            exit(1)

    logging.warning(
        f"{DEFAULT_PREFIX} Creating oci archive in {cache_dir}")
    sp.run(["buildah",
            "bud",
            "-t",
            f"oci-archive:{cache_dir}",
            containerfile])


@app.command()
def rebase() -> None:
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


def main():
    app()


if __name__ == "__main__":
    main()

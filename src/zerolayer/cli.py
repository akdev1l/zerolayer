#!/usr/bin/env python3
from pathlib import Path
from rich.prompt import Prompt
from rich.console import Console
from rich.table import Table
import subprocess as sp
import json
import shutil
import typer
import logging
import os
import datetime
import math
import hashlib

app = typer.Typer()
app_state = {"dry_run": False}

IMAGE_DIR = Path(os.environ.get("ZEROLAYER_IMAGE_DIR", "/var/cache/zerolayer"))
CONTAINERFILE_PATH = Path(os.environ.get(
    "ZEROLAYER_CONTAINERFILE_DIR", "/etc/zerolayer/Containerfile"))

DEFAULT_PREFIX = "[ZEROLAYER]"
DRY_RUN_PREFIX = "[DRY_RUN]"
CURRENT_ENVIRONMENT_NAME = "current"
GENERIC_COOL_NAME_FOR_IMAGES: str = "boot_env"


def generate_hash_from_date(s: str):
    return int(hashlib.sha256(s.encode('utf-8')).hexdigest(), 16) % 10**8


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
def list_environments(cache_dir: Path = IMAGE_DIR, max_shown: int = 0, ignore_current: bool = False) -> None:
    if not Path(cache_dir).exists():
        logging.fatal("Failed to find image directory")
        return

    table_list = Table("Filename", "Hash", "Size", "Creation Time")
    envs_found = 0
    # e.g.: boot_env.1HASH.tar.gz boot_env.2HASH.tar.gz boot_env.current.tar.gz
    for path in Path(cache_dir).iterdir():
        if envs_found == max_shown and max_shown != 0:
                return
        full_file_name = path.name.split(".")
        if GENERIC_COOL_NAME_FOR_IMAGES in full_file_name[0]:
            if not full_file_name[1].isnumeric() and not full_file_name[1] == CURRENT_ENVIRONMENT_NAME:
                logging.fatal(f"Invalid naming scheme for file {path.name}")
                return
            
            if ignore_current and full_file_name[1] == CURRENT_ENVIRONMENT_NAME:
                envs_found += 1
                continue
            
            table_list.add_row(path.name, full_file_name[1], convert_size(path.stat().st_size), str(datetime.datetime.fromtimestamp(path.stat().st_mtime)))

            envs_found += 1
    
    if envs_found == 0:
        logging.warning("Could not find any valid environments")
        return
    
    Console().print(table_list)


@app.command()
def clear(cache_dir: Path = IMAGE_DIR, all: bool = False, no_confirm: bool = False, list_size: int = 0):
    if app_state["dry_run"] and no_confirm is False:
        logging.info(f"{DRY_RUN_PREFIX} Delete everything from {cache_dir}")
        exit(0)

    if not Path(cache_dir).exists():
        logging.fatal("Failed to find image directory")
        return

    valid_files: list[Path] = [] 
    for path in Path(cache_dir).iterdir():
        full_file_name = path.name.split(".")
        if GENERIC_COOL_NAME_FOR_IMAGES in full_file_name[0]:
            if full_file_name[1] == CURRENT_ENVIRONMENT_NAME:
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


    list_environments(cache_dir, list_size, ignore_current=True)
    if list_size > 0:
        logging.warning(f"Results truncated to {list_size} results.")

    selected_env: str = Prompt.ask("\nWhich environment do you want to delete?", choices=[str(x.name.split(".")[1]) for x in valid_files])

    r_you_sure: bool = False 
    if no_confirm:
        r_you_sure = True
    else:
        r_you_sure = typer.confirm("Are you sure you want to delete the selected environment?", abort=True)
   
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
        logging.info(f"{DRY_RUN_PREFIX} Unlinking current environment")
        logging.info(f"{DRY_RUN_PREFIX} Symlinking generated file to current")
        return 

    if not cache_dir.exists():
        logging.warning(f"{DEFAULT_PREFIX} Creating \"{cache_dir}\" and parent directories")
        try:
            cache_dir.mkdir(parents=True)
        except PermissionError:
            logging.fatal(f"Could not create {cache_dir} due to permission errors. Are you not root?")
            exit(1)
        except OSError:
            logging.fatal(f"Failed creating {cache_dir}")
            exit(1)

    TARGET_FILE_NAME = f"{cache_dir.resolve()}/{GENERIC_COOL_NAME_FOR_IMAGES}.{generate_hash_from_date(str(datetime.datetime.now()))}.tar"

    logging.warning(
        f"{DEFAULT_PREFIX} Creating oci archive in {cache_dir}")
    sp.run(["buildah",
            "bud",
            "-o",
            f"type=tar,dest={TARGET_FILE_NAME}",
            containerfile])

    logging.warning(f"{DEFAULT_PREFIX} Unlinking current environment")
    for file in Path(cache_dir).iterdir():
        full_file_name = file.name.split(".")
        if GENERIC_COOL_NAME_FOR_IMAGES in full_file_name[0] and full_file_name[1] == CURRENT_ENVIRONMENT_NAME:
            file.unlink()

    logging.warning(f"{DEFAULT_PREFIX} Symlinking generated file to current")
    Path(f"{cache_dir}/{GENERIC_COOL_NAME_FOR_IMAGES}.{CURRENT_ENVIRONMENT_NAME}.tar").symlink_to(TARGET_FILE_NAME)


@app.command()
def rebase(cache_dir: Path = IMAGE_DIR) -> None:
    FULL_IMAGE: str = f"ostree-unverified-image:oci-archive:{cache_dir}/{GENERIC_COOL_NAME_FOR_IMAGES}.{CURRENT_ENVIRONMENT_NAME}.tar"
    
    if app_state["dry_run"]:
        logging.info(f"{DRY_RUN_PREFIX} Rebase to {FULL_IMAGE}")
        return
    
    logging.warning(f"{DEFAULT_PREFIX} Rebasing to {FULL_IMAGE}")
    if get_current_image() != FULL_IMAGE:
        sp.run(["rpm-ostree", "rebase", FULL_IMAGE])


@app.command()
def init(
        url: str = "https://github.com/ublue-os/startingpoint", 
        target_dir: Path = CONTAINERFILE_PATH.parents[0], 
        no_confirm: bool = False
):
    if app_state["dry_run"]:
        logging.info(f"{DRY_RUN_PREFIX} Delete everything from {target_dir}")
        logging.info(f"{DRY_RUN_PREFIX} Clone {url} to {target_dir}")
        return

    if target_dir.exists() and len(os.listdir(target_dir)) > 0:
        are_you_sure: bool = False 
        if no_confirm:
            are_you_sure = True
        else:
            are_you_sure = typer.confirm(f"Are you sure you want to delete everything from {target_dir}", abort=True)

        if not are_you_sure:
            return

        deleted_files = [str(file) for file in target_dir.iterdir()]
        
        shutil.rmtree(target_dir)

        logging.warning(f"{DEFAULT_PREFIX} Affected files:\n\t" + "\n\t".join(deleted_files) + "\n")
    
    try:
        gitclone = sp.run(["git","clone",url,str(target_dir)])
    except FileNotFoundError:
        logging.fatal(f"{DEFAULT_PREFIX} Could not run Git, is it in your PATH?")
        exit(1)
    
    if gitclone.returncode != 0:
        logging.fatal(f"{DEFAULT_PREFIX} Failed to initialize in {target_dir}")
        exit(1)

    logging.warning(f"{DEFAULT_PREFIX} Initialized successfully in {target_dir}")


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

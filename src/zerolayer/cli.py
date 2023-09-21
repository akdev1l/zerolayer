#!/usr/bin/env python3
import subprocess as sp
from pathlib import Path
import json
import typer
import logging
import os

app = typer.Typer()
app_state = {"dry_run": False}

IMAGE_DIR = Path(os.environ.get("ZEROLAYER_IMAGE_DIR", "/var/cache/zerolayer"))
CONTAINERFILE_DIR = Path(os.environ.get(
    "ZEROLAYER_CONTAINERFILE_DIR", "/etc/zerolayer"))

DEFAULT_PREFIX = "[ZEROLAYER]"
DRY_RUN_PREFIX = "[DRY_RUN]"
IMAGE_ARCHIVE_PATH = Path(f"{IMAGE_DIR}/current_image.tar.gz")
CLEANUP_CMD = ["rm", "-rf", f"{IMAGE_DIR}/*"]


def get_current_image() -> str:
    out = sp.run("rpm-ostree status --json", shell=True, stdout=sp.PIPE).stdout
    return json.loads(out)["deployments"][0]["container-image-reference"]


@app.command()
def build_image(
        containerfile: Path = CONTAINERFILE_DIR,
        output_dir: Path = IMAGE_DIR):
    if (app_state["dry_run"]):
        logging.info(f"{DRY_RUN_PREFIX} Create \"{
                     IMAGE_DIR}\" and parent directories")
    else:
        logging.warning(f"{DEFAULT_PREFIX} Creating \"{
            IMAGE_DIR}\" and parent directories")
        if (not output_dir.exists()):
            try:
                output_dir.mkdir(parents=True)
            except PermissionError:
                logging.fatal(f"Could not create {
                              output_dir} due to permission errors. Are you not root?")  # noqa: E501
                exit(1)

    if (app_state["dry_run"]):
        logging.info(f"{DRY_RUN_PREFIX} Delete everything from {IMAGE_DIR}")
    else:
        logging.warning(
            f"{DEFAULT_PREFIX} Deleting everything from {IMAGE_DIR}")
        sp.run(CLEANUP_CMD)

    if (app_state["dry_run"]):
        logging.info(f"{DRY_RUN_PREFIX} Create oci archive in {output_dir}")
    else:
        logging.warning(
            f"{DEFAULT_PREFIX} Creating oci archive in {output_dir}")
        sp.run(["buildah",
                "bud",
                "-t",
                f"oci-archive:{output_dir}",
                containerfile])


@app.command()
def rebase_to_image():
    FULL_IMAGE: str = f"ostree-unverified-image:oci-archive:{IMAGE_ARCHIVE_PATH}"  # noqa: E501
    if (app_state["dry_run"]):
        logging.info(f"{DRY_RUN_PREFIX} Rebase to {FULL_IMAGE}")
    else:
        logging.warning(f"{DEFAULT_PREFIX} Rebasing to {FULL_IMAGE}")
        if (get_current_image() != FULL_IMAGE):
            sp.run(["rpm-ostree", "rebase", FULL_IMAGE])


@app.callback()
def config(quiet: bool = False, dry_run: bool = False):
    logging.basicConfig(format="", level=logging.NOTSET)
    if quiet:
        logging.getLogger().setLevel(logging.CRITICAL)
    app_state["dry_run"] = dry_run


@app.command()
def all(rebase: bool = True) -> int:
    build_image(CONTAINERFILE_DIR, IMAGE_DIR)
    if (rebase):
        rebase_to_image()

    return 0


def main():
    app()


if __name__ == "__main__":
    main()

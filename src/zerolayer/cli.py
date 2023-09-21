#!/usr/bin/env python3
import subprocess as sp
from pathlib import Path
import json
import os


def get_current_image() -> str:
    out = sp.run("rpm-ostree status --json", shell=True, stdout=sp.PIPE).stdout
    return json.loads(out)["deployments"][0]["container-image-reference"]


def main() -> int:
    IMAGE_DIR = Path("/var/cache/zerolayer")
    CURRENT_IMAGE_PATH = Path(f"{IMAGE_DIR}/current_image.tar.gz")
    CLEANUP_CMD = ["rm", "-rf", f"{IMAGE_DIR}/*"]
    ZEROLAYER_CONTAINERFILE_VAR = "ZERO_CONTAINERFILE_NAME"

    if (not IMAGE_DIR.exists()):
        IMAGE_DIR.mkdir(parents=True)

    sp.run(CLEANUP_CMD)

    containerfile = os.environ.get(ZEROLAYER_CONTAINERFILE_VAR, "Containerfile")  # noqa: E501
    sp.run(["buildah",
            "bud",
            "-t",
            f"oci-archive:{CURRENT_IMAGE_PATH}",
            f"/etc/zerolayer/{containerfile}"])

    FULL_IMAGE: str = f"ostree-unverified-image:oci-archive:{CURRENT_IMAGE_PATH}"  # noqa: E501
    if (get_current_image() != FULL_IMAGE):
        sp.run(["rpm-ostree", "rebase", FULL_IMAGE])
    else:
        sp.run(["rpm-ostree", "update"])

    sp.run(CLEANUP_CMD)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

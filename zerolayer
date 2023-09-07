#!/usr/bin/env python3

from subprocess import run

def main():
    img_dir = "/var/run/image"

    # Preemptive cleanup to avoid build errors
    cleanup_cmd = ["rm", "-rf", img_dir]
    run(cleanup_cmd)

    podman_build = [
        "buildah",
        "bud",
        "-t",
        "oci:/var/run/image",
        "/etc/zerolayer"
    ]
    run(podman_build)
    
    # Post build cleanup
    run(cleanup_cmd)

if __name__ == "__main__":
    main()

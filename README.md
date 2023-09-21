# zerolayer - local native OCI/OSTree customizations

Zerolayer is anutility that allows the user to build a custom OCI image that is bootable by ostree and allows us to rebase to such image therefore allowing to us to customize the system without using `rpm-ostree install` or to depend in a registry to do so.

The workflow is simple:

1. Keep a `Containerfile` in `/etc/zerolayer/Containerfile`
2. Every 24 hours the `zerolayer.timer` will trigger which will build the Containerfile (as if `podman build` had been issued in `/etc/zerolayer`)
3. It will then upgrade/rebase to this image

After this workflow is complete and the user reboots their machine they will be booted into the newly built image archive.

## Using the CLI interface

You can interact with this by using the command-line interface's options.

Both steps of making and rebasing to an image are separate commands, you can use `all` to run everything at once. `--dry-run` and `--quiet` options are for QoL and testing.

## Installing

Use our justfile for installing the project.

```
just install
```

Testing and development utilities are also included in it.

# zerolayer - local native OCI/OSTree customizations

NOTE: This is a proof of concept at this time.

Zerolayer is the name of an imaginary utility that allows to build a custom OCI image that is bootable by ostree and allows us to rebase to such image therefore allowing to us to customize the system without using `rpm-ostree install`.

The workflow is simple:

1. Keep a `Containerfile` in `/etc/zerolayer/Containerfile`
2. Every 24 hours the `zerolayer.timer` will trigger which will build the Containerfile (as if `podman build` had been issued in `/etc/zerolayer`)
3. It will spin off a local container registry temporarily that allows to push image into `localhost:8888/zerolayer/custom:latest`
4. It will then upgrade/rebase to this image

After this workflow is complete and the user reboots their machine they will be booted into the newly built image. Please note that container registry will only run when an upgrade happens.

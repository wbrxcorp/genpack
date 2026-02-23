# stub — Multi-Distribution Installer and kexec Boot Loader for VMs

[GitHub: genpack-artifacts/stub](https://github.com/genpack-artifacts/stub)

## Overview

stub is one of the artifacts built with the genpack toolchain. It serves as a **disposable boot environment for installing other Linux distributions on QEMU/KVM virtual machines**.

While it operates as a genpack image, its ultimate purpose is to bring up an OS other than genpack. It is a two-stage provisioning tool that acts as an installer on first boot and as a boot loader using kexec on subsequent boots.

## Usage

Used in combination with the [vm](https://github.com/shimarin/vm) command.

```bash
# 1. Create a virtual disk for data (8GiB)
vm allocate debian12.img 8

# 2. Start a VM with stub as the system image and debian12.img as the data disk
vm run -d debian12.img stub-$(uname -m).squashfs

# 3. After auto-login inside the VM, run the script for the desired distribution
./debian12.sh

# 4. After installation completes, reboot — from then on, Debian 12 boots directly
```

## How It Works

```
stub boots (genpack image, console auto-login)
  |
  +-- Distribution install scripts are available under /root/
  |
  +-- User runs a script
  |     1. Create a filesystem on /dev/vdb (data virtual disk)
  |     2. Bootstrap the distribution using debootstrap / rpmbootstrap
  |     3. Configure SSH, networking, hostname, locale, etc.
  |     4. Generate initramfs with dracut
  |     5. Reboot
  |
  +-- On next boot: genpack-init's kexec plugin (00kexec.py)
        Detects a kernel on the data disk
        -> Transitions directly to the installed OS kernel via kexec
        -> stub's job is done; the installed OS boots from now on
```

## Supported Distributions

### Debian / Ubuntu (using debootstrap)

| Script | Distribution |
|---|---|
| `debian12.sh` | Debian 12 (Bookworm) |
| `debian13.sh` | Debian 13 (Trixie) |
| `ubuntu2004.sh` | Ubuntu 20.04 (Focal) |
| `ubuntu2204.sh` | Ubuntu 22.04 (Jammy) |
| `ubuntu2404.sh` | Ubuntu 24.04 (Noble) |
| `ubuntu2604.sh` | Ubuntu 26.04 (Resolute) |

### RHEL / RPM-based (using rpmbootstrap)

| Script | Distribution |
|---|---|
| `centos6.sh` | CentOS 6 |
| `centos7.sh` | CentOS 7 |
| `centos8stream.sh` | CentOS Stream 8 |
| `centos9stream.sh` | CentOS Stream 9 |
| `centos10stream.sh` | CentOS Stream 10 |
| `almalinux9.sh` | AlmaLinux 9 |
| `rocky8.sh` | Rocky Linux 8 |
| `miraclelinux8.sh` | MIRACLE LINUX 8 |
| `fedora42.sh` | Fedora 42 |

### Other

| Script | Distribution |
|---|---|
| `gentoo.sh` | Gentoo Linux (built from a stage3 tarball) |

## Key Components

### kexec Boot Plugin (`files/usr/lib/genpack-init/00kexec.py`)

A Python script that runs as a genpack-init plugin on every boot. It checks whether an installed OS kernel and initramfs exist on the data disk (`/dev/vdb`) or on virtiofs. If found, it loads and transitions to that kernel using kexec.

This allows stub to function as a transparent boot loader after the initial installation, making the VM boot flow look like:

```
QEMU start -> stub kernel -> genpack-init -> kexec -> installed OS kernel -> OS boot
```

### Distribution Install Scripts (`files/root/*.sh`)

Each script follows a common pattern:

1. Wait for network connectivity with `systemd-networkd-wait-online`
2. Create a filesystem on the data disk (XFS / Btrfs)
3. Bootstrap the base system with `debootstrap` or `rpmbootstrap`
4. Configure hostname, networking, SSH, and timezone
5. Deploy SSH public keys, LLMNRD (Link-Local Name Resolution), and the QEMU guest agent
6. Generate initramfs with dracut (including virtiofs / encryption support)
7. Reboot

The system is ready for remote management via SSH immediately after installation.

### Auto-Login (`files/build.d/autologin.sh`)

Sets up root auto-login on both hvc0 (virtio console) and ttyS0 (serial console). When connecting via `vm console`, a shell is available immediately without a login prompt.

### LLMNRD (`files/build.d/build-llmnrd.sh`)

Statically builds the Link-Local Multicast Name Resolution Daemon from source. It is deployed to the installed OS, enabling hostname resolution without a DNS server.

## Included Packages

| Package | Purpose |
|---|---|
| `genpack/paravirt` | Paravirtualized kernel and base system |
| `sys-kernel/gentoo-kernel` | Minimal kernel built from source |
| `sys-apps/kexec-tools` | Used to transition to the OS kernel |
| `dev-util/debootstrap` | Bootstrapping Debian / Ubuntu systems |
| `dev-util/rpmbootstrap` | Bootstrapping RPM-based systems |
| `sys-fs/cryptsetup` | Disk encryption support |
| `sys-devel/binutils` | Binary utilities |

## Kernel Minimization

Since stub is a disposable boot environment that does not require broad hardware support, 1,757 kernel options are disabled in `kernel/config.d/unset.config`.

Major features disabled include:
- Hibernation / Suspend / Power management
- Most of XEN / NUMA / SGX / EFI
- All debugging, profiling, and tracing features
- Unnecessary kernel compression algorithms
- Kernel signature verification (`KEXEC_SIG` — disabled to allow flexible kexec usage)

## Supported Architectures

| Architecture | Kernel Configuration | Output File |
|---|---|---|
| x86_64 | unset.config only | `stub-x86_64.squashfs` |
| aarch64 | savedconfig + unset.config | `stub-aarch64.squashfs` |
| riscv64 | savedconfig + unset.config | `stub-riscv64.squashfs` |

## Design Rationale

stub is a unique entity within the genpack ecosystem. Although it is built and booted as a genpack image, its purpose is to bring up an OS other than genpack. By leveraging genpack-init's plugin mechanism (pybind11 + Python) and the vm command's virtual disk management, it provides a unified environment for provisioning many different distribution VMs using a common procedure in QEMU/KVM environments.

## Source References

This document was written based on the following repository snapshots:

- [genpack-artifacts/stub @ b2aa5c3](https://github.com/genpack-artifacts/stub/tree/b2aa5c3e07173fcea3247b5c3aeddb5afe2d273f)

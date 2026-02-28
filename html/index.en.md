# genpack — A Gentoo-Based Immutable System Image Build Toolchain

## Introduction

genpack is a suite of tools for declaratively building, distributing, and booting purpose-built **immutable system images** based on Gentoo Linux. Rather than the traditional approach of installing an OS and then customizing it, genpack follows an image factory model where **an entire OS image is built from a blueprint (JSON5)**.

What Docker achieved for application containers, genpack aims to achieve at the **entire OS level** — and across **bare metal, virtual machines, and embedded devices**.

## Toolchain Architecture

```
  Design / Definition        Build                  Distribution / Runtime
 ┌───────────────┐    ┌───────────────┐    ┌───────────────────────┐
 │genpack-overlay │    │    genpack     │    │    genpack-install     │
 │ (Gentoo over-  │───▶│  (Image        │───▶│  (Disk write / ISO /   │
 │  lay: profiles │    │   builder)     │    │   self-update)         │
 │  and ebuilds)  │    └──────┬────────┘    └───────────────────────┘
 └───────────────┘           │                       │
                             │ .squashfs / .img      │
 ┌───────────────┐           ▼                       ▼
 │ genpack-       │    ┌───────────────┐    ┌───────────────────────┐
 │ artifacts      │    │  genpack-init  │    │          vm            │
 │ (Image          │───▶│ (Boot-time     │    │  (Run as a VM on       │
 │  definitions)  │    │  provisioning) │    │   QEMU/KVM)            │
 └───────────────┘    └───────────────┘    └───────────────────────┘
```

### Component Overview

| Component | Language | Role | Repository |
|---|---|---|---|
| **genpack** | Python + C++ | Generates SquashFS images from JSON5 configuration | [wbrxcorp/genpack](https://github.com/wbrxcorp/genpack) |
| **genpack-overlay** | Gentoo ebuild/profile | Package definitions, profile hierarchy, and initialization scripts | [wbrxcorp/genpack-overlay](https://github.com/wbrxcorp/genpack-overlay) |
| **genpack-init** | C++ + Python (pybind11) | Configures the system at every boot based on system.ini | [wbrxcorp/genpack-init](https://github.com/wbrxcorp/genpack-init) |
| **genpack-install** | C++ | Deploys images to disk/ISO/ZIP, handles self-updates | [wbrxcorp/genpack-install](https://github.com/wbrxcorp/genpack-install) |
| **vm** | C++ | Runs and manages genpack images as QEMU/KVM virtual machines | [shimarin/vm](https://github.com/shimarin/vm) |
| **genpack-artifacts** | JSON5 + shell scripts | A collection of concrete image definitions | [genpack-artifacts](https://github.com/genpack-artifacts) (GitHub Organization) |

---

## genpack — The Image Builder

[GitHub: wbrxcorp/genpack](https://github.com/wbrxcorp/genpack)

genpack is the core build engine of the toolchain. It takes a declarative configuration file called `genpack.json5` as input and produces an optimized SquashFS image using Gentoo Linux's stage3 and Portage.

### How It Builds: Layered Architecture

genpack uses a **two-layer (lower/upper) build structure**.

1. **Lower layer**: A complete build environment based on Gentoo stage3, where all packages are compiled and installed inside a `systemd-nspawn` container
2. **Upper layer**: Selectively copies only runtime-necessary files from the lower layer, then performs finishing steps such as user creation, service enablement, and custom file placement
3. **Packing**: Compresses the upper layer into a SquashFS archive to produce the final image

This design ensures that compilers, header files, and other build-only artifacts remain in the lower layer and never make it into the final image. A minimal runtime image is the natural result.

### Declarative Configuration

```json5
{
  name: "nextcloud",
  profile: "paravirt",
  packages: [
    "www-apps/nextcloud",
    "dev-db/mysql",
    "dev-lang/php",
    "net-misc/redis"
  ],
  services: ["apache2", "mysqld", "redis"],
  users: [{ name: "nextcloud", uid: 1000 }],
  use: {
    "dev-lang/php": "+mysql +curl +gd +xml +zip"
  },
  compression: "xz"
}
```

Everything — package lists, enabled services, user definitions, USE flags, and kernel configuration — is consolidated in this single file. This eliminates manual system construction and delivers **fully reproducible builds**.

### Key Commands

| Command | Function |
|---|---|
| `genpack build` | Full build (lower -> upper -> pack) |
| `genpack lower` | Build/rebuild the lower layer |
| `genpack upper` | Build/rebuild the upper layer |
| `genpack pack` | Generate the SquashFS image |
| `genpack bash [command...]` | Interactive shell / command execution inside the lower layer |
| `genpack archive` | Create a tar.gz archive of the configuration |

### Supported Architectures

x86_64, aarch64 (ARM64), i686, and riscv64 are supported. Architecture-specific settings can be managed in the `arch` section of `genpack.json5`.

---

## genpack-overlay — The Gentoo Overlay

[GitHub: wbrxcorp/genpack-overlay](https://github.com/wbrxcorp/genpack-overlay)

genpack-overlay is a Gentoo overlay that extends the Portage package management system. It provides metapackages that serve as building blocks for genpack images, along with a profile hierarchy that abstracts away differences between deployment targets.

### Profile Hierarchy

```
genpack/base (common to all environments: kernel, init, base tools)
  ├── genpack/systemimg (bare metal: hardware detection, storage tools)
  │     └── systemimg/baremetal (BIOS/UEFI, device drivers)
  ├── genpack/paravirt (virtualized: QEMU guest agent, virtio)
  ├── genpack/gnome (GNOME desktop)
  └── genpack/weston (Wayland compositor)
```

Image definitions simply specify `profile: "paravirt"` or `profile: "gnome/baremetal"`, and the appropriate base environment is automatically selected.

### Package Scripts

Each package can install initialization scripts under `/usr/lib/genpack/package-scripts/`. This is where package-specific setup tasks are defined — things like MySQL data directory initialization, Docker storage configuration, and SSH host key generation.

---

## genpack-init — The Boot-Time Provisioning System

[GitHub: wbrxcorp/genpack-init](https://github.com/wbrxcorp/genpack-init)

genpack-init is a hybrid C++ and Python (pybind11) initialization system. It starts as PID 1 and, **at every boot**, reads `system.ini` from the boot partition and executes a series of Python scripts to configure the system.

### Boot Sequence

1. Starts as PID 1
2. Reads `/run/initramfs/boot/system.ini` (located on a FAT partition)
3. Calls the `configure(ini)` function in each module under `/usr/lib/genpack-init/*.py`
4. Applies hostname, network, storage, service configuration, and more
5. Hands off to the real init (`/sbin/init` = systemd) via exec

### Native Capabilities Exposed to Python

Through pybind11, genpack-init exposes the following low-level operations to Python scripts:

- **Disk operations**: Partition information retrieval, parted, mkfs, mount/umount
- **Platform detection**: Raspberry Pi / QEMU identification
- **Filesystem operations**: chown, chmod, chgrp
- **Kernel modules**: coldplug (automatic loading via modalias)
- **systemd services**: enable/disable

### The system.ini-Driven Architecture

The most important design feature of genpack-init is that **the entire system behavior can be customized through a single `system.ini` file on a FAT partition**.

```
Storage layout:
┌──────────────────────────────────────────────────┐
│ Partition 1: FAT32 (boot)                        │
│  ├── EFI/                 (bootloader)           │
│  ├── system.img           (SquashFS OS image)    │
│  └── system.ini  ← the only file users edit      │
├──────────────────────────────────────────────────┤
│ Partition 2: Data [optional]                     │
└──────────────────────────────────────────────────┘
```

### Root Filesystem Construction: Flexible Persistence via overlayfs

The genpack image's initramfs detects at boot time whether a data partition exists on the boot storage (or, in the case of QEMU, a dedicated data virtual disk) and dynamically determines the upper layer of the overlayfs root filesystem:

- **Data partition present** -> The upper layer uses persistent storage. File changes made at runtime survive reboots.
- **No data partition** -> The upper layer uses tmpfs. Runtime changes are lost on reboot, and the system starts fresh every time (transient mode).

This mechanism allows a single image to exhibit different behaviors depending on the deployment configuration. A setup without a data partition enables "reset every time" operation suitable for kiosk terminals or demo environments, while a setup with a data partition supports persistent operation suitable for servers. In either case, genpack-init reads system.ini at every boot to configure the system, so changes to system.ini always take effect at the next boot.

### Benefits of system.ini

- **Anyone can change the configuration**: FAT32 can be read and written from Windows, macOS, and Linux alike. The INI format can be edited in Notepad. No Linux expertise required.
- **Complete separation of OS immutability and configuration mutability**: The SquashFS image is read-only; all configuration lives in system.ini. Settings never scatter across /etc.
- **Configuration applied at every boot**: genpack-init reads system.ini and configures the system at every boot. Changes to system.ini are guaranteed to take effect at the next startup.
- **Multi-purpose deployment from a single image**: The same image can be deployed for different purposes using different system.ini files.
- **Recovery through physical access**: Even if a network misconfiguration locks you out, you can pull the storage device and fix system.ini on the FAT partition.
- **OS updates independent of configuration**: Replacing the image leaves system.ini untouched. The perennial problem of config file overwrites during updates simply does not exist.

---

## genpack-install — The Image Deployment Tool

[GitHub: wbrxcorp/genpack-install](https://github.com/wbrxcorp/genpack-install)

genpack-install writes generated system images to physical storage and makes them bootable.

### Operating Modes

| Mode | Purpose |
|---|---|
| `--disk=<device>` | Install to a physical disk (partitioning + bootloader setup) |
| Self-update | Atomically replace the image on a running system |
| `--cdrom=<file>` | Create a bootable ISO 9660 image |
| `--zip=<file>` | Create a ZIP archive |

### Multi-Architecture Boot Support

Generates and installs GRUB bootloaders for BIOS / UEFI (x86_64, i386, ARM64, RISC-V) / Raspberry Pi boot methods. El Torito CD/ISO booting is also supported.

### Atomic Self-Update

Image updates on a running system are performed through atomic rename operations:

```
system     → system.cur  (back up the current image)
system.new → system      (activate the new image)
system.cur → system.old  (keep the previous generation = rollback possible)
```

---

## vm — The Virtual Machine Management Tool

[GitHub: shimarin/vm](https://github.com/shimarin/vm)

vm is a command-line tool for running and managing genpack system images as virtual machines on QEMU/KVM.

### Key Commands

| Command | Function |
|---|---|
| `vm run <image>` | Boot a VM from a system image |
| `vm service` | Run VMs as services based on vm.ini |
| `vm console <name>` | Connect to a VM's serial console |
| `vm stop <name>` | Graceful shutdown via the QMP protocol |
| `vm list` | List running VMs |
| `vm ssh user@vm` | SSH into a VM over vsock |
| `vm usb` | Enumerate USB devices (with XPath query support) |

### Key Features

- **Networking**: User mode / bridge / TAP / MACVTAP / SR-IOV / VDE / multicast
- **Display**: SPICE / VNC / egl-headless
- **GPU**: virtio-gpu 2D / QXL / OpenGL / Vulkan passthrough
- **Device passthrough**: USB (XPath filtering) / PCI (VFIO)
- **File sharing**: virtiofs / 9pfs
- **Communication**: SSH/SCP over vsock

---

## genpack-artifacts — The Image Definition Collection

[GitHub Organization: genpack-artifacts](https://github.com/genpack-artifacts)

genpack-artifacts is a collection of concrete system image definitions built using the genpack toolchain. Each artifact is managed as a separate repository.

### Artifact Structure

Every artifact follows a uniform directory layout:

```
artifact-name/
├── genpack.json5          # Declarative image definition
├── files/                 # Files merged into the root filesystem
│   ├── build.d/           # Scripts executed at build time
│   ├── etc/               # Configuration files
│   └── boot/              # Boot configuration (grub.cfg, etc.)
├── kernel/                # Kernel customization (optional)
│   └── config.d/          # Kernel config fragments
└── savedconfig/           # Portage savedconfig (per-architecture)
```

### Example Artifacts

| Category | Artifact | Purpose |
|---|---|---|
| **Desktop** | [gnome](https://github.com/genpack-artifacts/gnome), [streamer](https://github.com/genpack-artifacts/streamer) | GNOME desktop, OBS streaming workstation |
| **ML/AI** | [torch](https://github.com/genpack-artifacts/torch) | PyTorch + ROCm/CUDA machine learning environment |
| **Cloud** | [nextcloud](https://github.com/genpack-artifacts/nextcloud), [owncloud](https://github.com/genpack-artifacts/owncloud) | Self-hosted cloud storage |
| **Project Management** | [redmine](https://github.com/genpack-artifacts/redmine) | Redmine project management |
| **Networking** | [vpnhub](https://github.com/genpack-artifacts/vpnhub), [walbrix](https://github.com/genpack-artifacts/walbrix) | VPN gateway, network appliance |
| **Security** | [suricata](https://github.com/genpack-artifacts/suricata), [borg](https://github.com/genpack-artifacts/borg) | IDS, backup server |
| **Embedded** | [camera](https://github.com/genpack-artifacts/camera) | Motion-detection camera system |
| **Utility** | [rescue](https://github.com/genpack-artifacts/rescue), [stub](https://github.com/genpack-artifacts/stub) | System recovery, minimal build environment |

From a minimal configuration (rescue: a dozen or so packages) to a full desktop (gnome: hundreds of packages), everything is defined using the same `genpack.json5` + `files/` pattern.

---

## Design Philosophy

### 1. Declarative Image Definition (Infrastructure as Code)

Every image is declaratively defined in `genpack.json5`. Packages, USE flags, users, services, and kernel configuration are all consolidated in a single file, eliminating manual steps and delivering reproducible builds.

### 2. Immutable Image, Flexible Persistence

The final artifact is a read-only SquashFS image. System updates are performed not by modifying the existing environment, but by building a new image and atomically swapping it in. The runtime root filesystem is composed using overlayfs, and whether the upper layer is backed by persistent storage or tmpfs is automatically determined by the presence or absence of a data partition. Without a data partition, the system boots clean every time, making configuration drift impossible by design. With a data partition, persistent operation suitable for server workloads is supported.

### 3. Complete Separation of OS and User Configuration

The OS image (SquashFS) is immutable; user configuration (system.ini) is a text file on a FAT partition. Because the two are completely separate, OS updates never overwrite configuration, and changing settings requires no Linux expertise.

### 4. Configuration Applied at Every Boot

genpack-init reads system.ini and configures the system not just on the first boot, but at every boot. This means changes to system.ini always take effect at the next startup. Furthermore, in transient mode (no data partition), the overlayfs upper layer is tmpfs, so runtime changes are automatically discarded on reboot — the system always starts from a clean state plus whatever system.ini specifies.

### 5. Minimal Images Through Layered Builds

By separating the lower layer (build environment) from the upper layer (runtime), compilers and headers that are unnecessary at runtime are naturally excluded.

### 6. Why Gentoo

Choosing Gentoo as the base provides:
- **USE flags** for per-package feature control, rigorously eliminating unnecessary dependencies
- **Source builds** that produce binaries optimized for the target
- **Profile hierarchy** for systematically managing differences across deployment targets
- **Portage's overlay mechanism** for naturally integrating custom packages

### 7. Multi-Architecture, Multi-Target

The toolchain provides cross-cutting support for x86_64 / aarch64 / i686 / riscv64 architectures and BIOS / UEFI / Raspberry Pi boot methods.

---

## End-to-End Workflow

```
1. Design: Write genpack.json5
   ↓
2. Build: genpack build
   ├── Lower layer: Compile with stage3 + Portage (systemd-nspawn)
   ├── Upper layer: Extract runtime files only + customize
   └── Pack: SquashFS compression → system-x86_64.squashfs
   ↓
3. Deploy (choose one)
   ├── genpack-install --disk=/dev/sdX  (physical disk)
   ├── genpack-install --cdrom=out.iso  (ISO image)
   └── vm run system-x86_64.squashfs   (virtual machine)
   ↓
4. Boot: genpack-init reads system.ini and configures the system
   ↓
5. Operate: Edit system.ini and reboot = configuration change
            Self-update with a new image = OS update
```

---

## What Makes genpack Unique

Many tools with similar goals exist — NixOS, Yocto, Buildroot, mkosi, OSTree, among others — but genpack occupies a unique position aimed at **"distributing highly optimized Linux images as appliances that non-technical users can operate."**

At its core is a combination of ideas: an intentionally primitive configuration interface (INI files on FAT32), configuration applied at every boot with automatic persistence mode selection based on hardware detection, repurposing Gentoo — the quintessential mutable distribution — as raw material for immutable images, and a plugin-based init system via pybind11.

For a detailed comparison with existing tools, see [A Conversation about genpack's Unique Value Proposition](uvp.en.md).

## Source References

This document was written based on the following repository snapshots:

- [wbrxcorp/genpack @ 6aa1e82](https://github.com/wbrxcorp/genpack/tree/6aa1e8244e53499cacb3b15e78ba215c3a6a23a9)
- [wbrxcorp/genpack-overlay @ 45a7e1e](https://github.com/wbrxcorp/genpack-overlay/tree/45a7e1e7440104f6592150261858c4ddd498d15b)
- [wbrxcorp/genpack-init @ 721060c](https://github.com/wbrxcorp/genpack-init/tree/721060c832335b240e6bd6998779235e5185468a)
- [wbrxcorp/genpack-install @ 4246185](https://github.com/wbrxcorp/genpack-install/tree/4246185bb8c5b32f809fa482a28aa5c39caf5b3e)
- [shimarin/vm @ 2297086](https://github.com/shimarin/vm/tree/2297086ffe725a554e4577ad43d2a74e5e34d97a)

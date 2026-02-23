# genpack-overlay Profile Reference

## Overview

genpack-overlay profiles define the base environment for genpack images. When you specify a profile like `profile: "paravirt"` in `genpack.json5`, the packages, USE flags, and keyword settings associated with that profile are automatically applied.

Profiles are structured using Gentoo's Portage profile mechanism and have hierarchical inheritance relationships.

## Profile Hierarchy

All profiles inherit from the `genpack` root profile and are further organized through architecture-specific layers.

```
genpack (Root: base configuration common to all environments)
├── genpack/paravirt (for virtual machines)
├── genpack/systemimg (for disk images)
│   └── genpack/systemimg/baremetal (for physical machines)
├── genpack/weston (Wayland desktop)
└── genpack/gnome (GNOME desktop)
```

When actually selecting a profile, the architecture layer is automatically inserted:

```
genpack.json5: profile: "paravirt"
  → genpack/amd64/paravirt  (for x86_64)
  → genpack/arm64/paravirt  (for aarch64)
```

## Available Profiles

### paravirt

**Purpose**: For QEMU/KVM virtual machines

Mutually exclusive with `systemimg`. Includes packages optimized for virtualization (guest agents, virtio support) and excludes physical hardware drivers.

**Added Packages** (genpack/paravirt metapackage):

| Package | Purpose |
|---|---|
| `genpack/base` | Base system (described below) |
| `app-emulation/qemu-guest-agent` | QEMU guest agent |
| `sys-libs/liburing` | Asynchronous I/O support |
| `net-misc/socat` | Multi-purpose relay tool |

**USE Flags**:

```
media-libs/mesa video_cards_zink video_cards_lavapipe
```

Virtual machines use software rendering (lavapipe) and Zink (OpenGL on Vulkan).

### systemimg

**Purpose**: For disk image-based installation (format written by genpack-install)

Mutually exclusive with `paravirt`. Includes packages necessary for disk writing and bootloader installation by genpack-install.

**Added Packages** (genpack/systemimg metapackage):

| Package | Purpose |
|---|---|
| `genpack/base` | Base system |
| `genpack/genpack-install` | Disk writing and self-update tool |
| `sys-apps/kbd` | Keyboard utilities |

**USE Flags**:

```
sys-libs/zlib minizip
```

### baremetal (systemimg/baremetal)

**Purpose**: For physical machines (inherits from `systemimg`)

Specified with `profile: "baremetal"`. Adds tools necessary for physical hardware detection and management.

**Added Packages** (enabled by the `baremetal` USE flag in `genpack/systemimg`):

| Package | Purpose |
|---|---|
| `sys-kernel/linux-firmware` | Hardware firmware |
| `sys-fs/lsscsi` | SCSI device enumeration |
| `sys-apps/lshw` | Hardware information display |
| `sys-apps/hwloc` | Hardware topology |
| `sys-apps/usbutils` | USB device management |
| `sys-apps/pciutils` | PCI device management |
| `sys-apps/dmidecode` | DMI/SMBIOS information |
| `sys-apps/lm-sensors` | Hardware monitoring |
| `sys-apps/usb_modeswitch` | USB mode switching |
| `sys-power/cpupower` | CPU frequency management |
| `sys-apps/smartmontools` | S.M.A.R.T. monitoring |
| `sys-apps/nvme-cli` | NVMe management |
| `sys-apps/hdparm` | Disk parameters |
| `sys-apps/ethtool` | Network configuration |

x86_64 specific:

| Package | Purpose |
|---|---|
| `app-misc/beep` | Beep sound |
| `sys-apps/msr-tools` | MSR register access |
| `sys-apps/memtest86+` | Memory testing |

### gnome/baremetal

**Purpose**: Physical machine + GNOME desktop

Specified with `profile: "gnome/baremetal"`. Includes the GNOME desktop environment in addition to all baremetal packages.

**Added Packages** (genpack/gnome metapackage):

| Package | Purpose |
|---|---|
| `gnome-base/gnome` | GNOME desktop environment suite |
| `media-fonts/noto-cjk` | CJK fonts |
| `media-fonts/noto-emoji` | Emoji fonts |
| `x11-apps/mesa-progs` | OpenGL test tools |
| `dev-util/vulkan-tools` | Vulkan test tools |
| `net-libs/libnsl` | NIS support library |
| `app-misc/evtest` | Input event testing |
| `net-misc/gnome-remote-desktop` | Remote desktop |
| `app-i18n/mozc` | Japanese input (enabled by default) |

**Inherited From**: Includes the `gentoo:targets/desktop/gnome` profile, so comprehensive USE flags required for GNOME are automatically configured.

### weston/paravirt

**Purpose**: Virtual machine + Wayland (Weston) desktop

Specified with `profile: "weston/paravirt"`. Provides a lightweight desktop environment based on the Weston compositor.

**Added Packages** (genpack/weston metapackage):

| Package | Purpose |
|---|---|
| `dev-libs/weston` | Wayland compositor |
| `app-misc/wayland-utils` | Wayland utilities |
| `app-i18n/mozc` | Japanese input |
| `app-i18n/fcitx-gtk` | Input method framework |
| `gui-apps/wl-clipboard` | Wayland clipboard |
| `gui-apps/tuigreet` | Login greeter (enabled by default) |
| `media-fonts/noto-cjk` | CJK fonts |
| `media-fonts/noto-emoji` | Emoji fonts |
| `x11-apps/mesa-progs` | OpenGL test tools |
| `dev-util/vulkan-tools` | Vulkan test tools |

**Global USE Flags**:

```
USE="wayland -X"
```

Disables X11 and prioritizes Wayland.

**Package-specific USE Flags** (74 items, major ones):

```
sys-apps/systemd policykit
media-libs/mesa X vulkan vaapi
app-i18n/mozc fcitx5
dev-qt/qtbase opengl vulkan
```

USE flags are configured for numerous applications including Chrome, VS Code, Ghostty, GIMP, Evolution, LibreOffice, and VLC.

**Virtual Machine Video Driver**:

```
VIDEO_CARDS="-intel -nouveau -radeon -radeonsi virgl"
```

### raspberrypi

**Purpose**: For Raspberry Pi (arm64 only)

Specified with `profile: "raspberrypi"` (exclusive to arm64 architecture). Inherits from `baremetal` and adds Raspberry Pi-specific kernel and firmware.

**Added Packages**:

| Package | Purpose |
|---|---|
| `sys-kernel/raspberrypi-image` | Raspberry Pi kernel |
| `sys-firmware/raspberrypi-wifi-ucode` | Wi-Fi firmware |

## Root Profile (genpack)

Common configuration inherited by all profiles.

**Packages**:

| Package | Purpose |
|---|---|
| `genpack/genpack-progs` | genpack build utilities (always included) |
| `genpack/base` | Base system |

**Global USE Flags**:

```
sys-libs/glibc audit
sys-kernel/installkernel dracut
sys-fs/squashfs-tools lz4 lzma lzo xattr zstd
app-crypt/libb2 -openmp
dev-lang/perl minimal
app-editors/vim minimal
```

**Package Masks**:

```
>=dev-lang/python-3.14
```

## Base System (genpack/base)

Base packages included across all profiles.

**Always Included Packages**:

| Category | Packages |
|---|---|
| Kernel | `gentoo-kernel-bin` or `gentoo-kernel` (with initramfs) |
| Initialization | `dracut-genpack`, `genpack-init`, `gentoo-systemd-integration` |
| Basic tools | `timezone-data`, `net-tools`, `gzip`, `unzip`, `grep`, `coreutils`, `procps`, `which` |
| Network | `rsync`, `iputils`, `iproute2` |
| Runtime | `python`, `requests`, `ca-certificates` |

**Packages Controlled by USE Flags** (all enabled by default):

| USE Flag | Package | Purpose |
|---|---|---|
| `sshd` | `net-misc/openssh` | SSH server |
| `vi` | `app-editors/vim` | Text editor |
| `strace` | `dev-debug/strace` | System call tracing |
| `wireguard` | `net-vpn/wireguard-tools`, `net-vpn/wg-genconf` | VPN |
| `btrfs` | `sys-fs/btrfs-progs` | Btrfs filesystem tools |
| `xfs` | `sys-fs/xfsprogs` | XFS filesystem tools |
| `cron` | `sys-process/cronie` | cron daemon |
| `audit` | `sys-process/audit` | Audit framework |
| `logrotate` | `app-admin/logrotate` | Log rotation |
| `tcpdump` | `net-analyzer/tcpdump` | Packet capture |
| `banner` | (genpack banner display) | Login banner |

## Other Metapackages

Metapackages that can be independently added to the `packages` section in `genpack.json5`, separate from profiles.

### genpack/wireless

Wireless network support:

| Package | Purpose |
|---|---|
| `net-wireless/wpa_supplicant_any80211` | WPA supplicant |
| `net-wireless/iw` | Wireless LAN configuration |
| `net-wireless/wireless-tools` | Wireless tools |
| `net-wireless/bluez` | Bluetooth stack |
| `net-wireless/hostapd` | Access point |

### genpack/devel

Development tools:

| Package | Purpose |
|---|---|
| `sys-devel/binutils` | Binary utilities |
| `sys-devel/gcc` | C/C++ compiler |
| `dev-debug/gdb` | Debugger |

### genpack/devlauncher

Development environment for AI agents (includes `genpack/devel`):

| Package | Purpose |
|---|---|
| `www-client/google-chrome` | Web browser |
| `gui-apps/waypipe` | Wayland remote display |
| `dev-util/claude-code` | AI coding assistant |
| `app-editors/vscode` | Code editor |
| `x11-terms/ghostty` | Terminal emulator |
| `app-containers/docker` | Container runtime |
| Other | jq, fd, bat, pip, pytest, pylint, etc. |

## Profile Selection Guide

| Use Case | Profile | Notes |
|---|---|---|
| QEMU/KVM virtual machines | `paravirt` | Most common |
| Physical machines (servers) | `baremetal` | Includes hardware detection tools |
| Physical machines + GNOME desktop | `gnome/baremetal` | Full desktop |
| Virtual machines + GUI | `weston/paravirt` | Lightweight Wayland desktop |
| Raspberry Pi | `raspberrypi` | arm64 only |
| No profile | (none) | `genpack/base` only. Minimal setup for custom builds from scratch |

## Architecture-Specific Differences

| Architecture | Supported Profiles | Notes |
|---|---|---|
| x86_64 (amd64) | All profiles | With GRUB EFI-32 support |
| aarch64 (arm64) | paravirt, baremetal, raspberrypi | Dedicated Raspberry Pi profile available |
| i686 (x86) | base, systemimg | No desktop profiles |
| riscv64 | base equivalent | Limited support |

## Source References

This document was written based on the following repository snapshots:

- [wbrxcorp/genpack-overlay @ 45a7e1e](https://github.com/wbrxcorp/genpack-overlay/tree/45a7e1e7440104f6592150261858c4ddd498d15b)

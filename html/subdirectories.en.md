# Artifact Directory Structure

## Overview

A genpack artifact (image definition) is organized around `genpack.json5` and consists of multiple subdirectories. Each directory is processed during a specific build phase, defining the image contents from Portage configuration to custom file placement and build script execution.

## Directory Structure Overview

```
artifact-name/
├── genpack.json5          # Declarative image definition (required)
├── files/                 # Files merged into the root filesystem
│   ├── build.d/           # Build-time scripts (not included in the final image)
│   ├── etc/               # Configuration files
│   ├── usr/               # Libraries, binaries, systemd units
│   ├── var/               # Web content, spool, etc.
│   └── root/              # root home directory
├── kernel/                # Kernel configuration
│   └── config.d/          # Kernel config fragments
├── savedconfig/           # Portage savedconfig (per architecture)
├── patches/               # Portage package patches
├── env/                   # Portage package environment settings
└── overlay/               # Local Portage overlay
```

All subdirectories are optional. At minimum, an artifact can be defined with only `genpack.json5`.

## Correspondence with Build Phases

The genpack build process consists of two phases: the Lower layer (compilation environment) and the Upper layer (runtime environment). It is important to understand which phase processes each directory.

| Directory | Phase | Copy Destination | Purpose |
|---|---|---|---|
| `savedconfig/` | Lower | `/etc/portage/savedconfig/` | Custom build settings for packages |
| `patches/` | Lower | `/etc/portage/patches/` | Applying patches to packages |
| `kernel/` | Lower | `/etc/kernel/` | Kernel build configuration |
| `env/` | Lower | `/etc/portage/env/` | Per-package build environment variables |
| `overlay/` | Lower | `/var/db/repos/genpack-local-overlay/` | Custom ebuilds |
| `files/` | Upper | `/` (root) | Custom file placement |

The directories processed in the Lower phase are all related to Portage (the package manager) and are referenced during package compilation. Only `files/` is processed in the Upper phase, placing files directly into the final image.

## files/ — Custom Files and Build Scripts

`files/` is the most important directory for artifact customization. Files placed under this directory are recursively copied into the root filesystem during Upper layer construction.

### Copy Mechanism

During the Upper phase, files are processed as follows:

```bash
cp -rdv /mnt/host/files/. /
```

- `files/etc/systemd/system/myservice.service` → `/etc/systemd/system/myservice.service`
- `files/usr/bin/myscript` → `/usr/bin/myscript`
- `files/root/.bashrc` → `/root/.bashrc`

Symbolic links are preserved, and file permissions are maintained.

### Processing Order

The processing order within the Upper phase is as follows:

1. Selectively copy runtime files from the Lower layer
2. Execute package scripts (from genpack-overlay)
3. Create groups (`groups` in `genpack.json5`)
4. Create users (`users` in `genpack.json5`)
5. **Copy the contents of `files/` to the root**
6. **Execute build scripts in `files/build.d/`**
7. Execute `setup_commands`
8. Enable services (`services` in `genpack.json5`)

This ordering allows build scripts to operate on the assumption that files copied from `files/` and user definitions are already in place.

### files/build.d/ — Build Scripts

Scripts in `files/build.d/` are executed during the Upper phase and **are not included in the final image** (they are excluded during SquashFS generation). Use them for customizations that cannot be achieved through package installation or file copying alone.

#### Execution Order

Scripts are executed in **alphabetical order** by filename. Use numeric prefixes to control the execution order:

```
build.d/
├── 01-setup-database.sh
├── 02-configure-app.sh
└── 03-download-plugins.sh
```

#### Automatic Interpreter Detection

The script interpreter is automatically determined from the file extension and execute permission:

| Condition | Execution Method |
|---|---|
| Has execute permission | Executed directly (follows the shebang) |
| `.sh` extension (no execute permission) | Executed with `/bin/sh` |
| `.py` extension (no execute permission) | Executed with `/usr/bin/python` |
| Other extensions (no execute permission) | Error |

#### Per-User Execution

If you create a subdirectory within `build.d/`, the scripts inside it are executed as the user whose name matches the subdirectory name:

```
build.d/
├── setup-system.sh           # Executed as root
└── user/                     # Executed as the "user" user
    ├── setup-dotfiles.sh
    └── install-extensions.py
```

The subdirectory name must match an existing user on the system. The `HOME` environment variable is set to that user's home directory.

#### Available Environment Variables

| Variable | Description |
|---|---|
| `ARTIFACT` | Value of the `name` field in `genpack.json5` |
| `VARIANT` | Name of the variant being built (only when specified) |

#### Typical Use Cases

**Downloading and installing software:**

```bash
#!/bin/sh
# Download a binary from a GitHub release
ARCH=$(uname -m)
curl -Lo /usr/bin/tool \
  "https://github.com/org/tool/releases/latest/download/tool-${ARCH}"
chmod +x /usr/bin/tool
```

**Editing configuration files:**

```bash
#!/bin/sh
# Disable the Apache SSL module
sed -i 's/-D SSL //' /etc/conf.d/apache2
```

**Database initialization:**

```bash
#!/bin/sh
# Create a MySQL database and user
/etc/init.d/mysql start
mysql -e "CREATE DATABASE IF NOT EXISTS myapp;"
mysql -e "GRANT ALL ON myapp.* TO 'myapp'@'localhost';"
/etc/init.d/mysql stop
```

**Building from source:**

```bash
#!/bin/sh
# Static build of llmnrd
cd /tmp
git clone --depth 1 https://github.com/tklauser/llmnrd
cd llmnrd
make LDFLAGS="-static"
cp llmnrd /usr/bin/
cd / && rm -rf /tmp/llmnrd
```

### Typical files/ Structures

Server artifact:

```
files/
├── build.d/
│   ├── apache-enable-php.sh
│   ├── apache-ssl.sh
│   └── setup-app.sh
├── etc/
│   ├── logrotate.d/
│   │   └── myapp
│   └── systemd/system/
│       └── myapp.service
├── usr/
│   ├── bin/
│   │   └── myapp-helper
│   └── lib/systemd/system/
│       └── myapp-backup.timer
└── var/www/
    └── myapp/
```

Desktop artifact:

```
files/
├── build.d/
│   ├── enable-automatic-login
│   ├── enable-noto-cjk.sh
│   └── enable-pipewire-for-all-users
└── etc/
    ├── polkit-1/rules.d/
    └── xdg/autostart/
```

Embedded artifact:

```
files/
├── build.d/
│   └── setup.sh
└── etc/
    └── sysctl.d/
        └── tuning.conf
```

## kernel/ — Kernel Configuration

This directory is for customizing kernel build settings. It is copied to `/etc/kernel/` during the Lower phase and referenced when building the kernel package.

### config.d/ — Config Fragments

Placing `.config` files under `kernel/config.d/` merges them into the kernel configuration. Use this to enable or disable specific kernel options.

```
kernel/
└── config.d/
    └── unset.config
```

Example of `unset.config` (from the stub artifact, disabling unnecessary features):

```
# CONFIG_HIBERNATION is not set
# CONFIG_SUSPEND is not set
# CONFIG_XEN is not set
# CONFIG_NUMA is not set
# CONFIG_DEBUG_KERNEL is not set
# CONFIG_KEXEC_SIG is not set
```

## savedconfig/ — Portage savedconfig

This directory holds configuration for packages that reference custom configuration files at build time, such as the kernel. It is copied to `/etc/portage/savedconfig/` during the Lower phase.

### Per-Architecture Layout

savedconfig uses separate subdirectories for each architecture. The directory names correspond to Gentoo's CHOST values:

```
savedconfig/
├── aarch64-unknown-linux-gnu/
│   └── sys-kernel/
│       └── gentoo-kernel
├── riscv64-unknown-linux-gnu/
│   └── sys-kernel/
│       └── gentoo-kernel
└── x86_64-pc-linux-gnu/
    └── sys-kernel/
        └── gentoo-kernel
```

This allows architecture-specific kernel configurations to be applied when building images for multiple architectures from the same artifact. Portage references this configuration when the `savedconfig` USE flag is set for the kernel package.

## patches/ — Portage Package Patches

This directory is for applying patches to specific packages. It is copied to `/etc/portage/patches/` during the Lower phase and applied through Portage's user patches feature.

### Directory Structure

```
patches/
└── <category>/<package>/
    └── <patchname>.patch
```

Example:

```
patches/
└── dev-libs/weston/
    └── default-output-and-autolaunch-args.patch
```

In this case, the patch is automatically applied when the `dev-libs/weston` package is built. If a version-specific patch is needed, you can use `<package>-<version>/` as the directory name.

## env/ — Portage Package Environment Settings

This directory is for setting environment variables during the build of specific packages. It is copied to `/etc/portage/env/` during the Lower phase.

### Usage

Create a configuration file and assign it to a package using the `env` field in `genpack.json5`:

env/torch_cuda.conf:

```bash
CUDA_HOME="/opt/cuda"
MAKEOPTS="-j4"
```

genpack.json5:

```json5
{
  env: {
    "sci-libs/pytorch": "torch_cuda.conf"
  }
}
```

## overlay/ — Local Portage Overlay

This directory is for adding custom packages (ebuilds) that are not available in the official repositories or genpack-overlay. It is copied to `/var/db/repos/genpack-local-overlay/` during the Lower phase, and repos.conf and metadata are automatically generated.

### Directory Structure

It follows the standard Gentoo overlay structure:

```
overlay/
└── <category>/<package>/
    ├── Manifest
    └── <package>-<version>.ebuild
```

Example:

```
overlay/
└── media-libs/virglrenderer/
    ├── Manifest
    └── virglrenderer-9999.ebuild
```

genpack automatically generates `metadata/layout.conf`, `profiles/repo_name`, and `repos.conf`, so you do not need to prepare these files manually.

## Rebuild Triggers

Whether a Lower layer rebuild is necessary is determined by the modification timestamps of the following files and directories:

- `genpack.json5` (or `genpack.json`)
- `savedconfig/`
- `patches/`
- `kernel/`
- `env/`
- `overlay/`

**The `files/` directory is not included in the Lower layer rebuild triggers.** Since `files/` is only processed during the Upper phase, changes to `files/` are reflected through an Upper layer rebuild.

## Archive

Running the `genpack archive` command generates a `genpack-<name>.tar.gz` containing `genpack.json5` and all subdirectories (`files/`, `savedconfig/`, `patches/`, `kernel/`, `env/`, `overlay/`). This allows you to distribute artifact definitions.

## Source References

This document was written based on the following repository snapshots:

- [wbrxcorp/genpack @ b71eb6b](https://github.com/wbrxcorp/genpack/tree/b71eb6b025f7cd1ec5ae9220a21f2229c274c7bd)
- [wbrxcorp/genpack-overlay @ 45a7e1e](https://github.com/wbrxcorp/genpack-overlay/tree/45a7e1e7440104f6592150261858c4ddd498d15b)

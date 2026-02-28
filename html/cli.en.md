# genpack CLI Reference

## Overview

`genpack` is the main command of the genpack toolchain. It reads `genpack.json5` (or `genpack.json`) in the current directory and executes processing according to the subcommand.

```bash
genpack [global options] <subcommand>
```

## Global Options

Options common to all subcommands.

| Option | Type | Default | Description |
|---|---|---|---|
| `--debug` | Flag | false | Display DEBUG level logs |
| `--overlay-override <DIR>` | Path | (none) | Local override directory for genpack-overlay |
| `--independent-binpkgs` | Flag | false | Use artifact-specific binary package cache |
| `--deep-depclean` | Flag | false | Perform deep cleanup including build dependencies |
| `--compression <ALG>` | Choice | (follows config) | SquashFS compression: `gzip`, `xz`, `lzo`, `none` |
| `--devel` | Flag | false | Generate development image |
| `--variant <NAME>` | String | (follows config) | Variant name to use |

### --overlay-override

Overrides the genpack-overlay repository (normally auto-fetched from GitHub) with a local directory. Used when developing genpack-overlay itself.

### --independent-binpkgs

By default, a shared binary package cache at `~/.cache/genpack/{arch}/binpkgs/` is used, but specifying this option uses an independent cache per artifact. Use this to avoid interference between artifacts with significantly different USE flags.

## Subcommands

### build

Executes the full build pipeline (lower → upper → pack).

```bash
genpack build
```

This is the default behavior when the subcommand is omitted. Executes the following 3 phases in order:

1. **Lower layer build**: Compile packages with stage3 + Portage
2. **Upper layer build**: Extract and customize runtime files
3. **Pack**: SquashFS compression

On first run, automatically generates `.gitignore` and `.vscode/settings.json` if they don't exist.

### lower

Builds the lower layer (build environment).

```bash
genpack lower
```

Processing flow:

1. Create `work/{arch}/` directory
2. Download Gentoo stage3 tarball (with caching)
3. Download Portage snapshot (with caching)
4. Create ext4 filesystem image (`lower.img`)
5. Extract stage3 and Portage
6. Sync genpack-overlay
7. Configure Portage profile
8. Apply settings from `genpack.json5` (USE flags, keywords, licenses, masks)
9. Resolve circular dependencies (if `circulardep_breaker` exists)
10. Emerge all packages
11. Rebuild kernel modules
12. Cleanup with depclean and eclean
13. Generate file list for upper layer (`lower.files`)

Whether rebuilding the lower layer is needed is determined by timestamps of `genpack.json5` and Portage-related subdirectories (`savedconfig/`, `patches/`, `kernel/`, `env/`, `overlay/`).

### upper

Builds the upper layer (runtime environment).

```bash
genpack upper
```

**Prerequisite**: `lower` execution must be completed.

Processing flow:

1. Create ext4 image for upper layer (`upper.img`)
2. Copy files listed in `lower.files` from lower layer
3. Execute package scripts
4. Create groups and users
5. Copy contents of `files/` directory to root
6. Execute build scripts in `files/build.d/`
7. Execute `setup_commands`
8. Enable systemd services

### pack

Generate SquashFS image from upper layer.

```bash
genpack pack
```

**Prerequisite**: Both `lower` and `upper` execution must be completed.

Processing:

1. Compress upper layer to SquashFS
2. Exclude `build.d/`, log files, and temporary files
3. Generate EFI superfloppy image if EFI files exist

**Output files**:

| File | Condition |
|---|---|
| `{name}-{arch}.squashfs` | Always generated |
| `{name}-{arch}.img` | If EFI bootloader is included |

**Compression methods details**:

| Method | mksquashfs options | Characteristics |
|---|---|---|
| `gzip` | `-Xcompression-level 1` | Default. Fast |
| `xz` | `-comp xz -b 1M` | Smallest size. Time-consuming |
| `lzo` | `-comp lzo` | Fast. Lower compression than gzip |
| `none` | `-no-compression` | No compression |

### bash

Opens an interactive debug shell or runs a specified command in the lower layer.

```bash
genpack bash [command...]
```

When no command is given, launches a bash shell inside a systemd-nspawn container, allowing direct manipulation and inspection of lower layer filesystem. Used for verifying package installation status and debugging.

When a command is given, it is executed non-interactively inside the lower layer's nspawn container. The process exits with an error if the command fails.

### upper-bash

Opens interactive debug shell overlaid on upper layer.

```bash
genpack upper-bash
```

**Prerequisite**: `upper` execution must be completed.

Used to inspect and debug the contents of the final image.

### archive

Creates a distribution archive of artifact definition.

```bash
genpack archive
```

Generates `genpack-{name}.tar.gz` containing `genpack.json5` and all subdirectories (`files/`, `savedconfig/`, `patches/`, `kernel/`, `env/`, `overlay/`).

## Work Directory Structure

`genpack` places build artifacts and cache under the `work/` directory.

```
work/
├── .dirlock                    # Exclusive lock file
├── portage.tar.xz              # Portage snapshot (cache)
├── portage.tar.xz.headers      # Cache validation header
└── {arch}/
    ├── lower.img               # Lower layer filesystem (default 128 GiB)
    ├── lower.files             # File list to copy to upper layer
    ├── upper.img               # Upper layer filesystem (default 20 GiB)
    ├── stage3.tar.xz           # stage3 tarball (cache)
    └── stage3.tar.xz.headers   # Cache validation header
```

## Cache

### Download Cache

stage3 and Portage snapshots are cached under `work/`. Validated by HTTP headers (`Last-Modified`, `ETag`, `Content-Length`), and not re-downloaded if unchanged.

### Binary Package Cache

By default, binary packages are stored in `~/.cache/genpack/{arch}/binpkgs/` as a shared cache. Compiled packages can be reused across different artifacts of the same architecture.

When `--independent-binpkgs` is specified, an independent cache per artifact is used instead of this shared cache.

### genpack-overlay Cache

The genpack-overlay git repository is cached in `~/.cache/genpack/overlay/`.

## Environment Variables

genpack itself does not reference any environment variables, but the following environment variables are set within the container during the build process:

| Variable | Set When | Value |
|---|---|---|
| `ARTIFACT` | Upper layer build | `name` from `genpack.json5` |
| `VARIANT` | Upper layer build | Variant name (only when specified) |

## Default Values

| Setting | Value |
|---|---|
| Lower layer image size | 128 GiB |
| Upper layer image size | 20 GiB |
| genpack-overlay repository | `https://github.com/wbrxcorp/genpack-overlay.git` |
| Gentoo mirror | `http://ftp.iij.ad.jp/pub/linux/gentoo/` |
| Default compression | gzip |

## Typical Usage

```bash
# Full build
genpack build

# Full build (xz compression)
genpack --compression xz build

# Build with variant specified
genpack --variant cuda build

# Step-by-step build
genpack lower
genpack upper
genpack pack

# Debug (lower layer shell)
genpack bash

# Run a command in the lower layer
genpack bash emerge --info

# Debug (upper layer shell)
genpack upper-bash

# Debug (verbose logs)
genpack --debug build

# Build with local genpack-overlay version
genpack --overlay-override ~/projects/genpack-overlay build

# Create archive
genpack archive
```

## Source References

This document was written based on the following repository snapshots:

- [wbrxcorp/genpack @ 6aa1e82](https://github.com/wbrxcorp/genpack/tree/6aa1e8244e53499cacb3b15e78ba215c3a6a23a9)

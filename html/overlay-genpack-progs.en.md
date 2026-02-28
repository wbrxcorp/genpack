# genpack/genpack-progs Package

## Overview

`genpack/genpack-progs` is a package that bundles the support tools used during the genpack image build process. It is implicitly included in all genpack profiles and handles file collection, dependency resolution, metadata generation, and external resource downloading during image builds.

These tools were formerly fetched from an external repository (genpack-progs), but are now inlined in the ebuild's `files/` directory.

## Installed Commands

### Build Core Tools

Core tools that drive the image build process, called directly by genpack itself.

| Command | Description |
|---|---|
| `list-pkg-files` | Recursively resolves Portage package dependencies and generates the file list to include in the image |
| `exec-package-scripts-and-generate-metadata` | Executes package-specific post-install scripts and generates metadata under `/.genpack/` |
| `execute-artifact-build-scripts` | Executes artifact-specific build scripts (`/build`, `/build.d/`) |
| `recursive-touch` | Recursively analyzes ELF binary and script dependencies, updating atime. Also used to output file lists for initramfs |
| `rebuild-kernel-modules-if-necessary` | Runs `emerge @module-rebuild` when kernel module rebuilds are needed |

### Download Utilities

Tools for fetching external resources during builds.

| Command | Description |
|---|---|
| `download` | Downloads a file from a URL and outputs it to stdout. Caches in `/var/cache/download` |
| `get-rpm-download-url` | Resolves download URLs for RPM packages from YUM/DNF repositories |
| `get-github-download-url` | Retrieves download URLs for GitHub release assets |

### Maintenance Tools

Tools for build environment maintenance.

| Command | Description |
|---|---|
| `unmerge-masked-packages` | Detects and unmerges masked packages, then rebuilds @world |
| `remove-binpkg` | Removes Portage binary packages by atom specification. Defaults to dry-run |
| `findelf` | Searches for ELF binaries in a directory tree |
| `with-mysql` | Starts a temporary MySQL server, runs a command, then shuts down |

## Runtime Dependencies

| Package | Description |
|---|---|
| `sys-apps/util-linux` | Basic system utilities |
| `app-portage/gentoolkit` | Portage management tools (`equery` etc.) |
| `dev-util/pkgdev` | Gentoo package development tools |
| `app-arch/zip` | ZIP archiver |
| `dev-debug/strace` | System call tracer |
| `net-analyzer/tcpdump` | Network packet capture |
| `app-editors/nano` | Text editor |
| `app-editors/vim` | Text editor |
| `net-misc/netkit-telnetd` | Telnet daemon |
| `app-misc/figlet` | ASCII art text generator |
| `sys-fs/squashfs-tools[lz4,lzma,lzo,xattr,zstd]` | SquashFS image creation and extraction |
| `app-admin/eclean-kernel` | Automatic cleanup of old kernels |

## Command Details

### list-pkg-files

The core tool for determining which files go into a genpack image. It uses the Portage Python API to recursively resolve dependencies from the `@profile`, `@genpack-runtime` (and optionally `@genpack-devel`) package sets, then outputs the list of target files.

- Packages with the `genpack-ignore` eclass are skipped
- In non-devel mode, man pages, documentation, header files, etc. are excluded
- Saves the package dependency graph to `/.genpack/_pkgs_with_deps.pkl` for reuse by the subsequent `exec-package-scripts-and-generate-metadata`

### exec-package-scripts-and-generate-metadata

Loads the dependency data saved by `list-pkg-files` and executes per-package post-install scripts from `/usr/lib/genpack/package-scripts/<pkgname>/`. Then generates the following metadata files in the `/.genpack/` directory:

- `arch` — System architecture
- `profile` — genpack profile name
- `artifact` — Artifact name
- `variant` — Variant name
- `timestamp.commit` — Portage tree commit timestamp
- `packages` — List of installed packages (including USE flags, descriptions, etc.)

### execute-artifact-build-scripts

Executes the `/build` script and scripts under `/build.d/` at the artifact root.

- `/build` is executed as root if it exists
- Files in `/build.d/` are executed as root in sorted order
- Subdirectories in `/build.d/` execute their scripts as the user matching the directory name
- Non-executable files auto-detect interpreters from extensions (`.sh` → `/bin/sh`, `.py` → `/usr/bin/python`)

### recursive-touch

Inspects ELF binary headers (magic number `\x7fELF`) and uses `lddtree` to recursively resolve shared library dependencies. For scripts, it detects interpreters from shebang lines.

- By default, updates atime of target files (used in the subsequent "collect only recently accessed files" phase)
- `--print-for-initramfs` option outputs file lists for initramfs inclusion

### download

Downloads files from URLs using `curl` as the backend. Results are cached in `/var/cache/download` keyed by SHA1 hash of the URL. On re-download, uses HTTP conditional requests (`-z` flag) to check for modifications.

### get-rpm-download-url

Parses the `repomd.xml` of YUM/DNF repositories to retrieve `primary.xml` metadata and returns the download URL for the latest version of the specified package. Supports gzip, bz2, and xz compression, and caches repository metadata (default TTL: 1 hour).

### get-github-download-url

Uses the GitHub API to fetch the latest release assets and returns the download URL for assets matching a regex pattern. Also supports the special keywords `@tarball` (source tarball) and `@zipball` (source zip).

### with-mysql

A wrapper tool that starts a temporary MySQL server, executes a given command, then shuts down. On first run, it initializes the data directory and loads timezone data. Network connections are disabled; communication is via local socket only. Used for running database migrations during builds.

## genpack-ignore eclass

The `genpack-progs` ebuild inherits the `genpack-ignore` eclass. This causes `list-pkg-files` to skip this package when collecting files for the image. Build tools are used in the build environment (lower layer) but are not included in the final runtime image (upper layer).

## Source References

- [genpack/genpack-progs ebuild](https://github.com/wbrxcorp/genpack-overlay/tree/7bc4ad0/genpack/genpack-progs) (7bc4ad0)

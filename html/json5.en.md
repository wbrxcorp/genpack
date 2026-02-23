# genpack.json5 Specification Reference

## Overview

`genpack.json5` is a declarative definition file for system images built with genpack. It is placed in the root directory of each artifact and consolidates package configuration, Portage settings, user/service definitions, compression methods, and more into a single file.

The format is [JSON5](https://json5.org/), which supports comments, trailing commas, and other conveniences. If `genpack.json5` does not exist, it falls back to `genpack.json`, but if both exist, an error is raised.

## Minimal Configuration

```json5
{
  packages: ["genpack/paravirt"]
}
```

If `name` is omitted, the directory name is used automatically (with a warning).

## Field Reference

### Basic Fields

#### name

- **Type**: string
- **Default**: Base name of the current directory
- **Description**: The name of the artifact. It is passed to scripts as the `ARTIFACT` environment variable during build and is also used as the default output file name.

#### profile

- **Type**: string | null
- **Default**: null
- **Description**: Profile name from genpack-overlay. Internally concatenated with `genpack-overlay:genpack/{arch}/` and set as the Portage profile.

Common profiles:

| Profile | Use Case |
|---|---|
| `paravirt` | For QEMU/KVM virtual machines (virtio, guest agent) |
| `baremetal` | For physical machines (BIOS/UEFI, device drivers) |
| `gnome/baremetal` | Physical machine + GNOME desktop |
| `weston/paravirt` | Virtual machine + Wayland (Weston) |

#### outfile

- **Type**: string
- **Default**: `{name}-{arch}.squashfs`
- **Description**: Output file name. Can also be overridden with the `--outfile` CLI argument.

#### compression

- **Type**: string
- **Default**: `"gzip"`
- **Allowed values**: `"gzip"`, `"xz"`, `"lzo"`, `"none"`
- **Description**: SquashFS compression algorithm. `"xz"` produces the smallest size but takes longer to compress. Can also be overridden with the `--compression` CLI argument.

### Package-Related

#### packages

- **Type**: string[]
- **Default**: `[]`
- **Description**: List of packages to install. Specified in Gentoo package atom format (`category/name`).

Adding a `-` prefix excludes the package from the list when merging with profiles or variants:

```json5
{
  packages: [
    "genpack/paravirt",
    "app-misc/screen",
    "-app-misc/unwanted-package"  // Exclude from merge source
  ]
}
```

#### buildtime_packages

- **Type**: string[]
- **Default**: `[]`
- **Description**: Packages needed only at build time. They are installed in the lower layer but are not copied to the upper layer (final image). Use this for packages required for compilation but not at runtime, such as Go or CMake.

```json5
{
  buildtime_packages: ["dev-lang/go", "dev-build/cmake"]
}
```

#### binpkg_excludes

- **Type**: string | string[]
- **Default**: `[]`
- **Description**: Packages to exclude from the binary package cache (usepkg/buildpkg). Use this for packages where sharing binary caches is inappropriate due to differing configurations, such as the kernel.

### Portage Settings

#### use

- **Type**: object
- **Default**: `{}`
- **Description**: Per-package USE flag settings. Equivalent to `package.use`.

Keys are package atoms (`*/*` for global settings), and values are strings (space-separated) or lists:

```json5
{
  use: {
    "dev-lang/php": "+mysql +curl +gd +xml +zip",
    "media-libs/mesa": "wayland VIDEO_CARDS: virgl",
    "*/*": "python_targets_python3_12"
  }
}
```

USE_EXPAND variables such as `CPU_FLAGS_X86:`, `VIDEO_CARDS:`, `AMDGPU_TARGETS:`, and `APACHE2_MODULES:` are also configured through this field.

#### accept_keywords

- **Type**: object
- **Default**: `{}`
- **Description**: Per-package ACCEPT_KEYWORDS settings. Equivalent to `package.accept_keywords`.

When the value is `null`, it means no keyword restriction (the standard pattern for accepting testing versions):

```json5
{
  accept_keywords: {
    "dev-util/debootstrap": null,      // Accept ~arch
    "app-misc/package": "~amd64",      // Specific keyword
    "app-misc/other": ["~amd64", "**"] // Multiple keywords
  }
}
```

#### mask

- **Type**: string[]
- **Default**: `[]`
- **Description**: Package masks. Equivalent to `package.mask`. Used for purposes such as blocking versions above a certain threshold.

```json5
{
  mask: [">=dev-db/mysql-8"]
}
```

#### license

- **Type**: object
- **Default**: `{}`
- **Description**: Per-package license acceptance settings. Equivalent to `package.license`.

```json5
{
  license: {
    "sys-kernel/linux-firmware": "linux-fw-redistributable",
    "www-client/google-chrome": "google-chrome"
  }
}
```

#### env

- **Type**: object
- **Default**: `{}`
- **Description**: Per-package environment settings. Equivalent to `package.env`. Specify the name of a configuration file in Portage's `env/` directory.

```json5
{
  env: {
    "sci-libs/pytorch": "torch_cuda.conf"
  }
}
```

### Users and Groups

#### users

- **Type**: (string | object)[]
- **Default**: `[]`
- **Description**: Users to create in the upper layer. Specified as either a string (username only) or an object.

```json5
{
  users: [
    "simpleuser",
    {
      name: "advanceduser",
      uid: 1000,
      home: "/home/advanceduser",
      shell: "/bin/bash",
      initial_group: "users",
      additional_groups: ["wheel", "video", "audio"],
      create_home: true,
      empty_password: true
    }
  ]
}
```

Object format properties:

| Property | Type | Default | Description |
|---|---|---|---|
| `name` | string | (required) | Username |
| `uid` | integer | (auto) | User ID |
| `comment` | string | | GECOS field |
| `home` | string | | Home directory |
| `shell` | string | | Login shell |
| `initial_group` | string | | Primary group |
| `additional_groups` | string \| string[] | | Additional groups |
| `create_home` | boolean | true | Whether to create the home directory |
| `empty_password` | boolean | false | Whether to allow an empty password |

#### groups

- **Type**: (string | object)[]
- **Default**: `[]`
- **Description**: Groups to create in the upper layer.

```json5
{
  groups: [
    "customgroup",
    { name: "groupwithgid", gid: 1002 }
  ]
}
```

### Services and Setup

#### services

- **Type**: string[]
- **Default**: `[]`
- **Description**: systemd services to enable. Template units and timer units can also be specified.

```json5
{
  services: [
    "sshd",
    "apache2",
    "fstrim.timer",
    "vsock-proxy@80.socket"
  ]
}
```

#### setup_commands

- **Type**: string[]
- **Default**: `[]`
- **Description**: Shell commands executed inside an nspawn container after the upper layer is built. Use this for customizations that cannot be accomplished by package installation or file copying alone, such as editing files or changing permissions.

```json5
{
  setup_commands: [
    "sed -i 's/-D SSL //' /etc/conf.d/apache2",
    "mkdir -p /var/www/localhost/htdocs"
  ]
}
```

### Build Settings

#### lower-layer-capacity

- **Type**: integer (in GiB)
- **Default**: 128
- **Description**: Disk image size for the lower layer (in GiB). Increase this when the number of packages is very large.

#### independent_binpkgs

- **Type**: boolean
- **Default**: false
- **Description**: Whether to use artifact-specific binary packages instead of the shared binary package cache. Can also be specified with the `--independent-binpkgs` CLI option.

#### circulardep_breaker

- **Type**: object
- **Default**: (none)
- **Description**: Special configuration for resolving circular dependencies in Gentoo. Some packages (such as freetype and harfbuzz) depend on each other, so they are first installed with restricted USE flags and then built normally.

```json5
{
  circulardep_breaker: {
    packages: ["media-libs/freetype", "media-libs/harfbuzz"],
    use: "-truetype -harfbuzz"
  }
}
```

The packages specified in `packages` are first installed with the USE flags specified in `use`, and then rebuilt with the correct flags during the subsequent normal build.

### Conditional Settings

#### arch

- **Type**: object
- **Default**: `{}`
- **Description**: Architecture-specific setting overrides. Keys are architecture names (multiple can be specified with `|`), and values are objects containing fields to be merged.

Only the settings for keys matching the current machine's architecture (`uname -m`) are merged.

```json5
{
  arch: {
    x86_64: {
      packages: ["app-misc/x86-specific"],
      use: {
        "media-video/ffmpeg": "CPU_FLAGS_X86: avx avx2 sse4_2"
      }
    },
    aarch64: {
      accept_keywords: {
        "app-emulation/qemu-guest-agent": null
      }
    }
  }
}
```

Mergeable fields: `packages`, `buildtime_packages`, `accept_keywords`, `use`, `mask`, `license`, `env`, `binpkg_excludes`, `setup_commands`, `services`

#### variants

- **Type**: object
- **Default**: `{}`
- **Description**: Named variant configurations. Used to generate images with different configurations from the same artifact. Selected with the `--variant` CLI argument.

```json5
{
  packages: ["genpack/gnome"],
  services: ["gdm"],
  variants: {
    paravirt: {
      // packages are merged with the parent definition
      packages: ["-x11-drivers/nvidia-drivers"],
      use: {
        "media-libs/mesa": "VIDEO_CARDS: virgl"
      }
    },
    cuda: {
      packages: ["x11-drivers/nvidia-drivers"],
      use: {
        "sci-libs/pytorch": "CUDA_TARGETS: sm_89"
      }
    }
  }
}
```

Within a variant, most top-level fields including `name`, `profile`, and `outfile` can be overridden or merged. Additionally, `arch` can be included within a variant.

#### default_variant

- **Type**: string | null
- **Default**: null
- **Description**: The default variant name used when `--variant` is not specified on the CLI. An error is raised if the specified variant does not exist in `variants`.

## Merge Behavior

Settings in genpack.json5 are merged in the following order:

1. **Base settings**: Top-level fields
2. **Architecture-specific**: Settings for the matching architecture within `arch` are merged
3. **Variant**: Settings for the selected variant within `variants` are merged (including `arch` within the variant)

Behavior of list-type fields during merging:
- `packages`: Elements with a `-` prefix are removed from the existing list. Others are added without duplicates
- `buildtime_packages`, `mask`, `services`: Added without duplicates
- `accept_keywords`, `use`, `license`, `env`: Overwritten on a per-key basis

## Deprecated Field Names

The following hyphenated names are deprecated, and using them will result in an error:

| Deprecated Name | Current Name |
|---|---|
| `buildtime-packages` | `buildtime_packages` |
| `binpkg-exclude` | `binpkg_excludes` |
| `circulardep-breaker` | `circulardep_breaker` |

Within user objects, hyphenated names are still accepted for compatibility:
- `create-home` → `create_home`
- `initial-group` → `initial_group`
- `additional-groups` → `additional_groups`
- `empty-password` → `empty_password`

## Complete Configuration Example

```json5
{
  // Basic information
  name: "nextcloud",
  profile: "paravirt",
  compression: "xz",

  // Packages
  packages: [
    "genpack/paravirt",
    "www-apps/nextcloud",
    "dev-db/mysql",
    "dev-lang/php",
    "net-misc/redis",
    "www-servers/apache"
  ],
  buildtime_packages: [
    "app-arch/rpm2targz"
  ],
  binpkg_excludes: ["sys-kernel/gentoo-kernel"],

  // Portage settings
  use: {
    "dev-lang/php": "mysql curl gd xml zip",
    "www-servers/apache": "APACHE2_MODULES: http2 proxy proxy_fcgi"
  },
  accept_keywords: {
    "net-vpn/frp": null
  },
  license: {
    "net-analyzer/fping": "fping",
    "dev-db/redis": "SSPL-1"
  },

  // Users and services
  users: [
    { name: "nextcloud", uid: 1000 }
  ],
  services: ["apache2", "mysqld", "redis"],

  // Setup
  setup_commands: [
    "sed -i 's/-D SSL //' /etc/conf.d/apache2"
  ],

  // Variants
  variants: {
    selftestable: {
      profile: "weston/paravirt",
      packages: ["www-client/google-chrome"],
      users: [
        { name: "user", uid: 1000, empty_password: true }
      ]
    }
  }
}
```

## Source References

This document was written based on the following repository snapshots:

- [wbrxcorp/genpack @ b71eb6b](https://github.com/wbrxcorp/genpack/tree/b71eb6b025f7cd1ec5ae9220a21f2229c274c7bd)
- [wbrxcorp/genpack-overlay @ 45a7e1e](https://github.com/wbrxcorp/genpack-overlay/tree/45a7e1e7440104f6592150261858c4ddd498d15b)

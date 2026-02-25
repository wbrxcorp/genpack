# genpack/devlauncher Metapackage

## Overview

`genpack/devlauncher` is a metapackage that bundles the tools needed for GUI development work in a Wayland environment. It installs a GTK4-based application launcher (`devlauncher`) along with editors, browsers, terminal emulators, container tools, and command-line utilities.

## Dependency Package List

### Development Foundation (via genpack/devel)

| Package | Description |
|---|---|
| `sys-devel/binutils` | Binary utilities |
| `sys-devel/gcc` | GCC compiler |
| `dev-debug/gdb` | GDB debugger |

### GUI Applications

| Package | Description |
|---|---|
| `www-client/google-chrome` | Web browser |
| `app-editors/vscode[wayland]` | Visual Studio Code |
| `x11-terms/ghostty` (<1.2) | Ghostty terminal emulator |
| `app-text/xournalpp` | Handwriting notes & PDF annotation (GTK3) |
| `dev-util/claude-code` | Claude Code CLI |

### GUI Foundation

| Package | Description |
|---|---|
| `gui-apps/waypipe[lz4,zstd]` | Wayland remote display forwarding |
| `gui-libs/gtk[wayland]` | GTK4 (used by devlauncher itself) |
| `x11-libs/gtk+[wayland]` | GTK3 (used by xournalpp etc.) |
| `dev-python/pygobject` | Python GObject bindings |
| `media-fonts/noto` | Noto fonts |
| `media-fonts/noto-cjk` | Noto CJK fonts |
| `media-fonts/noto-emoji` | Noto emoji fonts |
| `media-sound/alsa-utils` | ALSA audio utilities |

### Containers

| Package | Description |
|---|---|
| `app-containers/docker` | Docker container engine |
| `app-containers/docker-compose` | Docker Compose |

### Command-Line Tools

| Package | Description |
|---|---|
| `app-admin/sudo` | Privilege escalation |
| `sys-process/psmisc` | Process management utilities |
| `app-misc/jq` | JSON processor |
| `sys-apps/fd` | File search |
| `app-text/tree` | Directory tree display |
| `sys-apps/bat` | cat with syntax highlighting |
| `dev-python/pip` | Python package manager |
| `dev-python/pylint` | Python linter |
| `dev-python/pytest` | Python test framework |

## devlauncher Application

A GTK4 (PyGObject) based application launcher installed as `/usr/bin/devlauncher`. When launched, it displays installed `.desktop` applications in a grid view and allows launching them by clicking.

### Automatic Wayland Environment Detection

`devlauncher` checks the following conditions at startup and automatically sets environment variables:

- `WAYLAND_DISPLAY` is set
- `DISPLAY` is not set (not X11)
- `XDG_SESSION_TYPE` is not `wayland`

When these conditions are met, it sets `XDG_SESSION_TYPE=wayland` and `MOZ_ENABLE_WAYLAND=1`. This compensates for cases where Wayland session information is incomplete during remote connections via waypipe SSH.

## Indirectly Required Flags

To correctly build devlauncher and its dependencies, there are USE flags required by indirect dependencies beyond what is directly specified in the ebuild's RDEPEND. When using the `weston` profile, these are set by the profile itself, but when combining with profiles that lack GUI settings such as `paravirt`, they must be explicitly specified in the `use` section of `genpack.json5`.

### License Acceptance

Proprietary packages require acceptance in the `license` section of `genpack.json5`:

```json5
license: {
    "www-client/google-chrome": "google-chrome",
    "dev-util/claude-code": "all-rights-reserved",
    "app-editors/vscode": "Microsoft-vscode"
}
```

### Wayland/Display Related

For GTK to work with the Wayland backend, the graphics stack also needs Wayland support.

| Package | USE Flag | Reason |
|---|---|---|
| `gui-libs/gtk` | `wayland` | GTK4 Wayland backend. Directly used by devlauncher |
| `x11-libs/gtk+` | `wayland` | GTK3 Wayland backend. Used by xournalpp etc. |
| `media-libs/mesa` | `vulkan wayland` | `gtk[wayland]` requires `mesa[wayland]`. `vulkan` is REQUIRED_USE for lavapipe/zink |
| `x11-libs/cairo` | `X` | Required by `gtk+[X]`. Needed for Chrome/Electron dependency chain |
| `media-libs/libglvnd` | `X` | Required via `gtk+` |
| `app-crypt/gcr` | `gtk` | VSCode → gnome-keyring → gcr dependency chain |
| `media-libs/freetype` | `harfbuzz` | Font rendering. Has circular dependency with harfbuzz |
| `app-text/poppler` | `cairo` | Required for xournalpp PDF rendering |

### Circular Dependency Resolution

`media-libs/freetype` and `media-libs/harfbuzz` have a mutual dependency, requiring `circulardep_breaker` configuration:

```json5
circulardep_breaker: {
    packages: ["media-libs/freetype", "media-libs/harfbuzz"],
    use: "-harfbuzz -truetype"
}
```

### genpack.json5 Configuration Example

Minimal USE flag settings when using devlauncher with the `paravirt` profile:

```json5
{
    profile: "paravirt",
    packages: ["genpack/devlauncher"],
    use: {
        "gui-libs/gtk": "wayland",
        "x11-libs/gtk+": "wayland",
        "media-libs/mesa": "vulkan wayland",
        "x11-libs/cairo": "X",
        "media-libs/libglvnd": "X",
        "media-libs/freetype": "harfbuzz",
        "app-crypt/gcr": "gtk",
        "app-text/poppler": "cairo"
    },
    circulardep_breaker: {
        packages: ["media-libs/freetype", "media-libs/harfbuzz"],
        use: "-harfbuzz -truetype"
    },
    license: {
        "www-client/google-chrome": "google-chrome",
        "dev-util/claude-code": "all-rights-reserved",
        "app-editors/vscode": "Microsoft-vscode"
    }
}
```

### Relationship with weston Profile

The `weston` profile globally sets `USE="wayland -X"` in `make.defaults` and covers most of the above USE flags in `package.use`. However, the `weston/paravirt` profile assumes a full desktop environment including the Weston compositor, which is excessive when only using remote display via waypipe. Individually specifying the required USE flags on the `paravirt` profile results in lighter images.

## Source References

- [genpack/devlauncher ebuild](https://github.com/wbrxcorp/genpack-overlay/tree/main/genpack/devlauncher)
- [profiles/genpack/weston/package.use](https://github.com/wbrxcorp/genpack-overlay/blob/main/profiles/genpack/weston/package.use)
- [profiles/genpack/paravirt/package.use](https://github.com/wbrxcorp/genpack-overlay/blob/main/profiles/genpack/paravirt/package.use)

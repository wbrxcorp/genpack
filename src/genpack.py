#!/usr/bin/python3
# -*- coding: utf-8 -*-
import os,logging,io,tarfile,subprocess,re,json,argparse,json,hashlib,time
from datetime import datetime

import json5 # dev-python/json5
import requests # dev-python/requests

DEFAULT_LOWER_SIZE_IN_GIB = 24  # Default max size of lower image in GiB
DEFAULT_UPPER_SIZE_IN_GIB = 12  # Default max size of upper image in GiB
OVERLAY_SOURCE = "https://github.com/wbrxcorp/genpack-overlay.git"

debug = False  # Set to True to enable debug output
arch = os.uname().machine

work_root = "work"
work_dir = os.path.join(work_root, arch)

cache_root = os.path.join(os.path.expanduser("~"), ".cache/genpack")
cache_arch_dir = os.path.join(cache_root, arch)
binpkgs_dir = os.path.join(cache_arch_dir, "binpkgs")
download_dir = os.path.join(cache_root, "download")

base_url = "http://ftp.iij.ad.jp/pub/linux/gentoo/"
user_agent = "genpack/0.1"
overlay_override = None
independent_binpkgs = False
deep_depclean = False
genpack_json = None
genpack_json_time = None

container_name = "genpack-%d" % os.getpid()

class Variant:
    def __init__(self, name):
        self.name = name
        self.lower_image = os.path.join(work_dir, "lower.img") if self.name is None else os.path.join(work_dir, "lower-%s.img" % self.name)
        self.lower_files = os.path.join(work_dir, "lower.files") if self.name is None else os.path.join(work_dir, "lower-%s.files" % self.name)
        self.upper_image = os.path.join(work_dir, "upper.img") if self.name is None else os.path.join(work_dir, "upper-%s.img" % self.name)

def url_readlines(url):
    """Read lines from a URL."""
    logging.debug(f"Reading lines from URL: {url}")
    headers = {'User-Agent': user_agent}
    response = requests.get(url, headers=headers)
    response.raise_for_status()  # Raise an error for bad responses
    lines = response.text.splitlines()
    logging.debug(f"Read {len(lines)} lines from {url}")
    return lines

def get_latest_stage3_tarball_url(stage3_variant = "systemd"):
    _arch = arch
    _arch2 = arch
    if _arch == "x86_64": _arch = _arch2 = "amd64"
    elif _arch == "i686": _arch = "x86"
    elif _arch == "aarch64": _arch = _arch2 = "arm64"
    elif _arch == "riscv64":
        _arch = "riscv"
        _arch2 = "rv64_lp64d"
    current_status = None
    for line in url_readlines(base_url + "releases/" + _arch + "/autobuilds/latest-stage3-" + _arch2 + "-%s.txt" % (stage3_variant,)):
        if current_status is None:
            if line == "-----BEGIN PGP SIGNED MESSAGE-----": current_status = "header"
            continue
        elif current_status == "header":
            if line == "": current_status = "body"
            continue
        elif current_status == "body":
            if line == "-----BEGIN PGP SIGNATURE-----": break
            line = re.sub(r'#.*$', "", line.strip())
            if line == "": continue
            #else
            splitted = line.split(" ")
            if len(splitted) < 2: continue
            #else
            return base_url + "releases/" + _arch + "/autobuilds/" + splitted[0]
    #else
    raise Exception("No stage3 tarball (arch=%s,stage3_variant=%s) found", arch, stage3_variant)

def get_latest_portage_tarball_url():
    return base_url + "snapshots/portage-latest.tar.xz"

def headers_to_info(headers):
    return f"Last-Modified:{headers.get('Last-Modified', '')} ETag:{headers.get('ETag', '')} Content-Length:{headers.get('Content-Length', '')}"

def get_headers(url):
    """Get the headers of a URL."""
    logging.debug(f"Getting headers for URL: {url}")
    headers = {'User-Agent': user_agent}
    response = requests.head(url, headers=headers)
    response.raise_for_status()  # Raise an error for bad responses
    logging.debug(f"Headers for {url}: {response.headers}")
    return response.headers

def download(url, dest):
    headers = {'User-Agent': user_agent}
    response = requests.get(url, stream=True, headers=headers)
    response.raise_for_status()  # Raise an error for bad responses

    with open(dest, 'wb') as f:
        for chunk in response.iter_content(chunk_size=8192):
            f.write(chunk)
    logging.info(f"Downloaded {url} to {dest}")
    return response.headers

def setup_lower_image(lower_image, stage3_tarball, portage_tarball):
    # create image file
    lower_size_in_gib = genpack_json.get("lower-layer-capacity", DEFAULT_LOWER_SIZE_IN_GIB)
    logging.info(f"Creating image file at {lower_image} with size {lower_size_in_gib} GiB.")
    with open(lower_image, "wb") as f:
        f.seek(lower_size_in_gib * 1024 * 1024 * 1024 - 1)
        f.write(b'\x00')
    try:
        logging.info(f"Formatting filesystem on {lower_image}")
        subprocess.run(['mkfs.ext4', lower_image], check=True)
        logging.info("Filesystem formatted successfully.")
        logging.info("Extracting stage3 to lower image...")
        subprocess.run(["genpack-helper", "stage3", lower_image, stage3_tarball], check=True)
        logging.info("Extracting portage to lower image...")
        subprocess.run(["genpack-helper", "lower", lower_image, "mkdir", "-p", "/var/db/repos/gentoo"], check=True)
        with open(portage_tarball, "rb") as f:
            helper = subprocess.run(["genpack-helper", "lower", lower_image, "tar", "Jxpf", "-", "-C", "/var/db/repos/gentoo", "--strip-components=1"],
                                stdin=f, check=True)
        logging.info("Portage extracted successfully.")
        # workaround for https://bugs.gentoo.org/734000
        subprocess.run(["genpack-helper", "lower", lower_image, "chown", "portage", "/var/cache/distfiles"], check=True)
        subprocess.run(["genpack-helper", "lower", lower_image, "chmod", "g+w", "/var/cache/distfiles"], check=True)
        # install git
        logging.info("Installing git in lower image...")
        nspawn_opts = [
            "--setenv=USE=-* curl ssl curl_ssl_openssl openssl" # disable all USE flags for initial git
        ]
        if not independent_binpkgs:
            os.makedirs(binpkgs_dir, exist_ok=True)
            nspawn_opts.append("--binpkgs-dir=" + binpkgs_dir)
        subprocess.run(["genpack-helper", "nspawn"] + nspawn_opts + [lower_image, "emerge", "-bk", "-u", "dev-vcs/git"], check=True)
    except Exception as e:
        logging.error(f"Error setting up lower image: {e}")
        os.remove(lower_image)  # Clean up the image
        raise

def replace_portage(lower_image, portage_tarball):
    logging.info(f"Replacing portage in lower image: {lower_image}")
    #portage_dir = os.path.join(mount_point, "var/db/repos/gentoo")
    script = """[ -d /var/db/repos/gentoo ] && echo "Renaming existing portage directory" && mv /var/db/repos/gentoo /var/db/repos/gentoo.old-$(date +%Y%m%d-%H%M%S) && mkdir /var/db/repos/gentoo || true"""
    subprocess.run(["genpack-helper", "lower", lower_image, "sh"], input=script, text=True, check=True)
    with open(portage_tarball, "rb") as f:
        subprocess.run(["genpack-helper", "lower", lower_image, "tar", "Jxpf", "-", "-C", "/var/db/repos/gentoo", "--strip-components=1"], stdin=f, text=False, check=True)
    logging.info("Portage replaced successfully.")

def sync_genpack_overlay(lower_image):
    script = f"""if [ ! -d "/var/db/repos/genpack-overlay" ]; then
    echo "Genpack overlay not found, cloning..."
    git clone {OVERLAY_SOURCE} /var/db/repos/genpack-overlay
else
    git -C /var/db/repos/genpack-overlay pull
fi
if [ ! -f "/etc/portage/repos.conf/genpack-overlay.conf" ]; then
    echo "Creating repos.conf for genpack-overlay"
    mkdir -p /etc/portage/repos.conf
    echo -e '[genpack-overlay]\nlocation=/var/db/repos/genpack-overlay' > /etc/portage/repos.conf/genpack-overlay.conf
fi
if [ -f /var/db/repos/genpack-overlay/.git/ORIG_HEAD ]; then
    echo "GENPACK_OVERLAY_LAST_UPDATE: $(date -r /var/db/repos/genpack-overlay/.git/ORIG_HEAD +%s.%N)"
elif [ -f /var/db/repos/genpack-overlay/.git/HEAD ]; then
    echo "GENPACK_OVERLAY_LAST_UPDATE: $(date -r /var/db/repos/genpack-overlay/.git/HEAD +%s.%N)"
fi
"""
    sync = subprocess.run(["genpack-helper", "lower", lower_image, "sh"], input=script, text=True, check=True, capture_output=True)
    lines = sync.stdout.splitlines()
    for line in lines:
        if line.startswith("GENPACK_OVERLAY_LAST_UPDATE:"):
            mtime = float(line.split(":")[1].strip())
            logging.info(f"Genpack overlay last update time: {datetime.fromtimestamp(mtime)}")
            return mtime
        else:
            print(line)  # Print other messages from the script
    return 0

def apply_portage_sets_and_flags(lower_image, runtime_packages, buildtime_packages, accept_keywords, use, license, mask):
    if accept_keywords is None: accept_keywords = {}
    if use is None: use = {}
    if license is None: license = {}
    if mask is None: mask = []
    if buildtime_packages is None: buildtime_packages = []

    files = {}

    if not isinstance(runtime_packages, list):
        raise ValueError("runtime_packages must be a list")
    #else

    files["etc/portage/sets/genpack-runtime"] = "\n".join(runtime_packages)

    if not isinstance(buildtime_packages, list):
        raise ValueError("buildtime_packages must be a list or None")
    #else
    files["etc/portage/sets/genpack-buildtime"] = "\n".join(buildtime_packages)

    if not isinstance(accept_keywords, dict):
        raise ValueError("accept_keywords must be a dictionary")

    accept_keywords_content = ""
    for k, v in accept_keywords.items():
        if v is None:
            accept_keywords_content += f"{k}\n"
        elif isinstance(v, list):
            accept_keywords_content += f"{k} {' '.join(v)}\n"
        else:
            accept_keywords_content += f"{k} {v}\n"
    files["etc/portage/package.accept_keywords/genpack"] = accept_keywords_content

    if not isinstance(use, dict):
        raise ValueError("use must be a dictionary")
    use_content = ""
    for k, v in use.items():
        if v is None:
            use_content += f"{k}\n"
        elif isinstance(v, list):
            use_content += f"{k} {' '.join(v)}\n"
        else:
            use_content += f"{k} {v}\n"
    files["etc/portage/package.use/genpack"] = use_content

    if not isinstance(license, dict):
        raise ValueError("license must be a dictionary")
    license_content = ""
    for k, v in license.items():
        if v is None:
            license_content += f"{k}\n"
        elif isinstance(v, list):
            license_content += f"{k} {' '.join(v)}\n"
        else:
            license_content += f"{k} {v}\n"
    files["etc/portage/package.license/genpack"] = license_content

    if not isinstance(mask, list):
        raise ValueError("mask must be a list")
    files["etc/portage/package.mask/genpack"] = "\n".join(mask)

    tar_buf = io.BytesIO()
    with tarfile.open(fileobj=tar_buf, mode='w') as tar:
        for path, content in files.items():
            info = tarfile.TarInfo(name=path)
            if isinstance(content, str):
                content = content.encode('utf-8')
            info.size = len(content)
            tar.addfile(tarinfo=info, fileobj=io.BytesIO(content))
    
    subprocess.run(["genpack-helper", "lower", lower_image, "tar", "xf", "-"], input=tar_buf.getvalue(), check=True, text=False)

    # apply savedconfig
    if os.path.isdir("savedconfig"):
        logging.info(f"Installing savedconfig...")
        subprocess.run(["genpack-helper", "nspawn", lower_image, 'rsync', '-rlptD', "--delete", "/mnt/host/savedconfig", "/etc/portage"], check=True)
    else:
        script = """[ -d /etc/portage/savedconfig ] && echo "Removing existing savedconfig directory" && rm -rf /etc/portage/savedconfig || true"""
        subprocess.run(["genpack-helper", "lower", lower_image, "sh"], input=script, text=True, check=True)

    # apply patches
    if os.path.isdir("patches"):
        logging.info(f"Installing patches...")
        subprocess.run(["genpack-helper", "nspawn", lower_image, 'rsync', '-rlptD', "--delete", "/mnt/host/patches", "/etc/portage"], check=True)
    else:
        script = """[ -d /etc/portage/patches ] && echo "Removing existing patches directory" && rm -rf /etc/portage/patches || true"""
        subprocess.run(["genpack-helper", "lower", lower_image, "sh"], input=script, text=True, check=True)
        
    # apply kernel config
    if os.path.isdir("kernel"):
        logging.info(f"Installing kernel config...")
        subprocess.run(["genpack-helper", "nspawn", lower_image, 'rsync', '-rlptD', "--delete", "/mnt/host/kernel", "/etc/kernel"], check=True)  
    else:
        script = """[ -d /etc/kernel ] && echo "Removing existing kernel directory" && rm -rf /etc/kernel || true"""
        subprocess.run(["genpack-helper", "lower", lower_image, "sh"], input=script, text=True, check=True)

    # apply local overlay
    if os.path.isdir("overlay"):
        logging.info(f"Installing local overlay...")
        subprocess.run(["genpack-helper", "nspawn", lower_image, 'rsync', '-rlptD', "--delete", "/mnt/host/overlay/", "/var/db/repos/genpack-local-overlay"], check=True)
        script = """[ ! -f /etc/portage/repos.conf/genpack-local-overlay.conf ] && echo "Creating repos.conf for genpack-local-overlay" && mkdir -p /etc/portage/repos.conf && echo -e '[genpack-local-overlay]\nlocation=/var/db/repos/genpack-local-overlay' > /etc/portage/repos.conf/genpack-local-overlay.conf || true"""
        subprocess.run(["genpack-helper", "lower", lower_image, "sh"], input=script, text=True, check=True)
        script = """[ ! -f /var/db/repos/genpack-local-overlay/metadata/layout.conf ] && echo "Creating layout.conf for genpack-local-overlay" && mkdir -p /var/db/repos/genpack-local-overlay/metadata && echo -e 'masters = gentoo' > /var/db/repos/genpack-local-overlay/metadata/layout.conf || true"""
        subprocess.run(["genpack-helper", "lower", lower_image, "sh"], input=script, text=True, check=True)
        script = """[ ! -f /var/db/repos/genpack-local-overlay/profiles/repo_name ] && echo "Creating repo_name for local overlay" && mkdir -p /var/db/repos/genpack-local-overlay/profiles && echo 'genpack-local-overlay' > /var/db/repos/genpack-local-overlay/profiles/repo_name || true"""
        subprocess.run(["genpack-helper", "lower", lower_image, "sh"], input=script, text=True, check=True)
    else:
        script = """[ -f /etc/portage/repos.conf/genpack-local-overlay.conf ] && echo "Removing existing repos.conf for genpack-local-overlay" && rm -f /etc/portage/repos.conf/genpack-local-overlay.conf || true"""
        subprocess.run(["genpack-helper", "lower", lower_image, "sh"], input=script, text=True, check=True)

def set_profile(lower_image, profile_name):
    arch_map = {
        "x86_64": "amd64",
        "aarch64": "arm64",
        "i686": "x86",
        "riscv64": "riscv",
    }
    portage_arch = arch_map.get(arch, None)
    exact_profile_name = "genpack-overlay:genpack/" + portage_arch
    if profile_name is not None and profile_name != "":
        exact_profile_name += "/" + profile_name
    print(f"Setting gentoo profile to {exact_profile_name}...")
    nspawn_opts = []
    if overlay_override is not None:
        nspawn_opts.append(f"--genpack-overlay-dir={overlay_override}")
    subprocess.run(["genpack-helper", "nspawn"] + nspawn_opts + [lower_image, "eselect", "profile", "set", exact_profile_name], check=True)

def load_genpack_json(directory="."):
    json_parser, json_file = None, None

    genpack_json5 = os.path.join(directory, "genpack.json5")
    if os.path.isfile(genpack_json5):
        json_parser = json5
        json_file = genpack_json5
    genpack_json = os.path.join(directory, "genpack.json")
    if os.path.isfile(genpack_json):
        if json_parser is None:
            json_parser = json
            json_file = genpack_json
        else:
            raise ValueError("Both genpack.json5 and genpack.json found. Please remove one of them.")
    if json_file is None:
        raise FileNotFoundError("""Neither genpack.json5 nor genpack.json file found. `echo '{"packages":["genpack/paravirt"]}' > genpack.json5` or so to create the minimal one.""")

    #else
    return (json_parser.load(open(json_file, "r")), os.path.getmtime(json_file))

def merge_genpack_json(trunk, branch, path, allowed_properties = ["profile", "outfile","devel","packages","buildtime_packages",
                                                           "accept_keywords","use","mask","license","binpkg_excludes","users","groups", 
                                                           "services", "arch","variants", ], variant = None):
    if not isinstance(trunk, dict):
        raise ValueError("trunk must be a dictionary")
    #else
    path_str = " > ".join(path)
    if not isinstance(branch, dict):
        raise ValueError(f"branch at {path_str} must be a dictionary")

    if "profile" in allowed_properties and "profile" in branch:
        if not isinstance(branch["profile"], str):
            raise ValueError(f"profile at {path_str} must be a string")
        #else
        trunk["profile"] = branch["profile"]

    if "outfile" in allowed_properties and "outfile" in branch:
        trunk["outfile"] = branch["outfile"]
    
    if "devel" in allowed_properties and "devel" in branch:
        if not isinstance(branch["devel"], bool):
            raise ValueError(f"devel at {path_str} must be a boolean")
        #else
        trunk["devel"] = branch["devel"]

    if "packages" in allowed_properties and "packages" in branch:
        if not isinstance(branch["packages"], list):
            raise ValueError(f"packages at {path_str} must be a list")
        #else
        if "packages" not in trunk: trunk["packages"] = []
        for package in branch["packages"]:
            if package[0] == '-':
                package = package[1:]
                if package in trunk["packages"]:
                    trunk["packages"].remove(package)
            elif package not in trunk["packages"]:
                trunk["packages"].append(package)

    if "buildtime_packages" in allowed_properties:
        if "buildtime-packages" in branch:
            raise ValueError(f"buildtime-packages at {path_str} is deprecated, use buildtime_packages instead")
        if "buildtime_packages" in branch:
            if not isinstance(branch["buildtime_packages"], list):
                raise ValueError(f"buildtime_packages at {path_str} must be a list")
            #else
            if "buildtime_packages" not in trunk: trunk["buildtime_packages"] = []
            for package in branch["buildtime_packages"]:
                if package not in trunk["buildtime_packages"]:
                    trunk["buildtime_packages"].append(package)
    
    if "accept_keywords" in allowed_properties and "accept_keywords" in branch:
        if not isinstance(branch["accept_keywords"], dict):
            raise ValueError(f"accept_keywords at {path_str} must be a dictionary")
        #else
        if "accept_keywords" not in trunk: trunk["accept_keywords"] = {}
        for k, v in branch["accept_keywords"].items():
            trunk["accept_keywords"][k] = v

    if "use" in allowed_properties and "use" in branch:
        if not isinstance(branch["use"], dict):
            raise ValueError(f"use at {path_str} must be a dictionary")
        #else
        if "use" not in trunk: trunk["use"] = {}
        for k, v in branch["use"].items():
            trunk["use"][k] = v # TODO: merge if already exists
    
    if "mask" in allowed_properties and "mask" in branch:
        if not isinstance(branch["mask"], list):
            raise ValueError(f"mask at {path_str} must be a list")
        #else
        if "mask" not in trunk: trunk["mask"] = []
        for package in branch["mask"]:
            if package not in trunk["mask"]:
                trunk["mask"].append(package)

    if "license" in allowed_properties and "license" in branch:
        if not isinstance(branch["license"], dict):
            raise ValueError(f"license at {path_str} must be a dictionary")
        #else
        if "license" not in trunk: trunk["license"] = {}
        for k, v in branch["license"].items():
            trunk["license"][k] = v
    
    if "binpkg_excludes" in allowed_properties:
        if "binpkg-exclude" in branch:
            raise ValueError(f"binpkg-exclude at {path_str} is deprecated, use binpkg_excludes instead")
        if "binpkg_excludes" in branch:
            if not isinstance(branch["binpkg_excludes"], (str, list)):
                raise ValueError(f"binpkg_excludes at {path_str} must be a string or a list of strings")
            #else
            if "binpkg_excludes" not in trunk: trunk["binpkg_excludes"] = []
            if isinstance(branch["binpkg_excludes"], str):
                branch["binpkg_excludes"] = [branch["binpkg_excludes"]]
            for package in branch["binpkg_excludes"]:
                if package not in trunk["binpkg_excludes"]:
                    trunk["binpkg_excludes"].append(package)

    if "users" in allowed_properties and "users" in branch:
        if not isinstance(branch["users"], list):
            raise ValueError(f"users at {path_str} must be a list")
        #else
        if "users" not in trunk: trunk["users"] = []
        trunk["users"] += branch["users"]

    if "groups" in allowed_properties and "groups" in branch:
        if not isinstance(branch["groups"], list):
            raise ValueError(f"groups at {path_str} must be a list")
        #else
        if "groups" not in trunk: trunk["groups"] = []
        trunk["groups"] += branch["groups"]
    
    if "services" in allowed_properties and "services" in branch:
        if not isinstance(branch["services"], list):
            raise ValueError(f"services at {path_str} must be a list")
        #else
        if "services" not in trunk: trunk["services"] = []
        for service in branch["services"]:
            if service not in trunk["services"]:
                trunk["services"].append(service)
    
    if "arch" in allowed_properties and "arch" in branch:
        if not isinstance(branch["arch"], dict):
            raise ValueError(f"arch at {path_str} must be a dictionary")
        #else
        for k, v in branch["arch"].items():
            if not isinstance(k, str):
                raise ValueError(f"arch at {path_str} must be a string")
            if arch in k.split('|'):
                merge_genpack_json(trunk, v, path + [f"arch={k}"], [
                    "packages","buildtime_packages",
                    "accept_keywords","use","mask","license","binpkg_excludes","services"
                ])
    
    if "variants" in allowed_properties and "variants" in branch and variant is not None:
        if not isinstance(branch["variants"], dict):    
            raise ValueError(f"variants at {path_str} must be a dictionary")
        #else
        if isinstance(variant, Variant): variant = variant.name
        if variant in branch["variants"]:
            merge_genpack_json(trunk, branch["variants"][variant], path + [f"variant={variant}"], [
                "name","profile","outfile","packages","buildtime_packages",
                "accept_keywords","use","mask","license","binpkg_excludes","users","groups",
                "services","arch"
            ])

def lower(variant=None, devel=False):
    logging.info("Processing lower layer...")
    os.makedirs(work_dir, exist_ok=True)
    # todo: create .gitignore in work_root
    stage3_is_new = False
    stage3_url = get_latest_stage3_tarball_url()
    logging.info(f"Latest stage3 tarball URL: {stage3_url}")
    stage3_headers = get_headers(stage3_url)
    stage3_tarball = os.path.join(work_dir, "stage3.tar.xz")
    stage3_saved_headers_path = os.path.join(work_dir, "stage3.tar.xz.headers")
    stage3_saved_headers = open(stage3_saved_headers_path).read().strip() if os.path.isfile(stage3_saved_headers_path) else None
    if stage3_saved_headers != headers_to_info(stage3_headers):
        logging.info("Stage3 tarball info has changed, downloading new tarball.")
        stage3_headers = download(stage3_url, stage3_tarball)
        stage3_is_new = True
    
    portage_is_new = False
    portage_url = get_latest_portage_tarball_url()
    logging.info(f"Latest portage tarball URL: {portage_url}")
    portage_headers = get_headers(portage_url)
    portage_tarball = os.path.join(work_root, "portage.tar.xz") # because portage tarball is not architecture specific
    portage_saved_headers_path = os.path.join(work_root, "portage.tar.xz.headers")
    portage_saved_headers = open(portage_saved_headers_path).read().strip() if os.path.isfile(portage_saved_headers_path) else None
    if portage_saved_headers != headers_to_info(portage_headers):
        logging.info("Portage tarball info has changed, downloading new tarball.")
        portage_headers = download(portage_url, portage_tarball)
        portage_is_new = True

    image_is_new = False
    if stage3_is_new or not os.path.isfile(variant.lower_image):
        setup_lower_image(variant.lower_image, stage3_tarball, portage_tarball)
        image_is_new = True
        with open(stage3_saved_headers_path, 'w') as f:
            f.write(headers_to_info(stage3_headers))
    elif portage_is_new:
        replace_portage(variant.lower_image, portage_tarball)

    if portage_is_new:
        with open(portage_saved_headers_path, 'w') as f:
            f.write(headers_to_info(portage_headers))
    
    latest_mtime = sync_genpack_overlay(variant.lower_image)
    logging.debug(f"Latest genpack-overlay mtime: {time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(latest_mtime))}")
    logging.debug(f"lower_files time: {time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(os.path.getmtime(variant.lower_files))) if os.path.exists(variant.lower_files) else 'N/A'}")

    if os.path.exists(variant.lower_files) and (stage3_is_new or portage_is_new or os.path.getmtime(variant.lower_files) < latest_mtime):
        logging.info(f"Removing old {variant.lower_files} file due to changes in stage3 or portage.")
        os.remove(variant.lower_files)

    if os.path.exists(variant.lower_files):
        logging.info("Lower image is up-to-date, skipping.")
        return

    # merge main genpack.json
    merged_genpack_json = {}
    merge_genpack_json(merged_genpack_json, genpack_json, ["genpack.json"], 
        ["profile","devel","packages","buildtime_packages",
            "accept_keywords","use","mask","license","binpkg_excludes",
            "arch","variants"], variant)

    profile = genpack_json.get("profile", None)
    set_profile(variant.lower_image, profile)

    devel = devel or merged_genpack_json.get("devel", False)

    apply_portage_sets_and_flags(variant.lower_image, 
                                merged_genpack_json.get("packages", []),
                                merged_genpack_json.get("buildtime_packages", []),
                                merged_genpack_json.get("accept_keywords", {}),
                                merged_genpack_json.get("use", {}), 
                                merged_genpack_json.get("license", {}), 
                                merged_genpack_json.get("mask", []))

    # binpkg_excludes
    binpkg_excludes = merged_genpack_json.get("binpkg_excludes", [])
    if isinstance(binpkg_excludes, str):
        binpkg_excludes = [binpkg_excludes]
    elif not isinstance(binpkg_excludes, list):
        raise ValueError("binpkg-excludes must be a string or a list of strings")

    nspawn_opts = []
    if not independent_binpkgs:
        os.makedirs(binpkgs_dir, exist_ok=True)
        nspawn_opts.append(f"--binpkgs-dir={binpkgs_dir}")
    if overlay_override is not None:
        nspawn_opts.append(f"--genpack-overlay-dir={overlay_override}")

    # circular dependency breaker
    if "circulardep-breaker" in genpack_json:
        raise ValueError("Use circulardep_breaker instead of circulardep-breaker in genpack.json")
    if "circulardep_breaker" in genpack_json:
        circulardep_breaker_packages = genpack_json["circulardep_breaker"].get("packages", [])
        circulardep_breaker_use = genpack_json["circulardep_breaker"].get("use", None)
        if len(circulardep_breaker_packages) > 0:
            logging.info("Emerging circular dependency breaker packages...")
            circulardep_breaker_nspawn_opts = nspawn_opts.copy()
            if circulardep_breaker_use is not None:
                circulardep_breaker_nspawn_opts.append(f"--setenv=USE={circulardep_breaker_use}")
            emerge_cmd = ["emerge", "-bk", "--binpkg-respect-use=y", "-u", "--keep-going"]
            if len(binpkg_excludes) > 0:
                emerge_cmd += ["--usepkg-exclude", " ".join(binpkg_excludes)]
                emerge_cmd += ["--buildpkg-exclude", " ".join(binpkg_excludes)]
            emerge_cmd += circulardep_breaker_packages
            subprocess.run(["genpack-helper", "nspawn"] + circulardep_breaker_nspawn_opts + [variant.lower_image] + emerge_cmd, check=True)

    logging.info("Emerging all packages...")
    emerge_cmd = ["emerge", "-bk", "--binpkg-respect-use=y", "-uDN", "--keep-going"]
    if len(binpkg_excludes) > 0:
        emerge_cmd += ["--usepkg-exclude", " ".join(binpkg_excludes)]
        emerge_cmd += ["--buildpkg-exclude", " ".join(binpkg_excludes)]
    emerge_cmd += ["@world", "genpack-progs", "@genpack-runtime", "@genpack-buildtime"]
    subprocess.run(["genpack-helper", "nspawn"] + nspawn_opts + [variant.lower_image] + emerge_cmd, check=True)
    logging.info("Rebuilding kernel modules if necessary...")
    subprocess.run(["genpack-helper", "nspawn"] + nspawn_opts + [variant.lower_image, "rebuild-kernel-modules-if-necessary"], check=True)

    logging.info("Rebuilding preserved packages...")
    emerge_cmd = ["emerge", "-bk", "--binpkg-respect-use=y"]
    if len(binpkg_excludes) > 0:
        emerge_cmd += ["--usepkg-exclude", " ".join(binpkg_excludes)]
        emerge_cmd += ["--buildpkg-exclude", " ".join(binpkg_excludes)]
    emerge_cmd += ["@preserved-rebuild"]
    subprocess.run(["genpack-helper", "nspawn"] + nspawn_opts + [variant.lower_image] + emerge_cmd, check=True)

    logging.info("Unmerging masked packages...")
    subprocess.run(["genpack-helper", "nspawn"] + nspawn_opts + [variant.lower_image, "unmerge-masked-packages"], check=True)

    logging.info("Cleaning up...")
    cleanup_cmd = "emerge --depclean"
    if deep_depclean:
        cleanup_cmd += " --with-bdeps=n"
    cleanup_cmd += " && etc-update --automode -5"
    cleanup_cmd += " && eclean-dist -d"
    cleanup_cmd += " && eclean-pkg"
    if independent_binpkgs:
        cleanup_cmd += " -d" # with independent binpkgs, we can clean up binpkgs more aggressively
    subprocess.run(["genpack-helper", "nspawn"] + nspawn_opts + [variant.lower_image, "sh", "-c", cleanup_cmd], check=True)

    files = []
    lib64_exists = None

    # check if lib64 exists
    lib64_exists = subprocess.check_call(["genpack-helper", "lower", variant.lower_image, "[" , "-d", "/lib64", "]"]) == 0
    nspawn_opts = []
    if overlay_override is not None:
        nspawn_opts.append(f"--genpack-overlay-dir={overlay_override}")
    list_pkg_files = subprocess.Popen(["genpack-helper", "nspawn", variant.lower_image] + nspawn_opts + ["list-pkg-files"], stdout=subprocess.PIPE, text=True, bufsize=1)
    try:
        for line in list_pkg_files.stdout:
            line = line.rstrip('\n')
            if not line or line.startswith('#'): continue
            #else
            if not os.path.isabs(line):
                raise ValueError(f"list-pkg-files returned non-absolute path: {line}")
            #else
            files.append(line.lstrip('/'))  # remove leading slash
    finally:
        return_code = list_pkg_files.wait()
        if return_code != 0:
            raise subprocess.CalledProcessError(return_code, list_pkg_files.args)

    with open(variant.lower_files, "w") as f:
        for file in ["bin", "sbin", "lib", "usr/sbin", "run", "proc", "sys", "root", "home", "tmp", "mnt",
                     "dev", "dev/console", "dev/null"]:
            files.append(file)
        if lib64_exists:
            files.append("lib64")
        for file in sorted(files):
            f.write(file + '\n')

def bash(variant):
    logging.info("Running bash in the lower image for debugging.")
    nspawn_opts = []
    if not independent_binpkgs:
        os.makedirs(binpkgs_dir, exist_ok=True)
        nspawn_opts.append("--binpkgs-dir=" + binpkgs_dir)
    if overlay_override is not None:
        nspawn_opts.append(f"--genpack-overlay-dir={overlay_override}")
    subprocess.run(["genpack-helper", "nspawn"] + nspawn_opts + [variant.lower_image, "bash"])
    subprocess.run(["genpack-helper", "nspawn"] + nspawn_opts + [variant.lower_image, "emaint", "binhost", "--fix"])

def upper(variant):
    logging.info("Processing upper layer...")
    if not os.path.isfile(variant.lower_image) or not os.path.exists(variant.lower_files):
        raise FileNotFoundError(f"Lower image {variant.lower_image} or lower files {variant.lower_files} does not exist. Please run 'genpack lower' first.")

    # create upper image if it does not exist
    if not os.path.isfile(variant.upper_image):
        with open(variant.upper_image, "wb") as f:
            f.seek(DEFAULT_UPPER_SIZE_IN_GIB * 1024 * 1024 * 1024 - 1)
            f.write(b'\x00')
        try:
            logging.info(f"Formatting filesystem on {variant.upper_image}")
            subprocess.run(['mkfs.ext4', variant.upper_image], check=True)
            logging.info("Filesystem formatted successfully.")
        except:
            logging.error(f"Failed to format filesystem on {variant.upper_image}.")
            os.remove(variant.upper_image)
            raise

    logging.info("Copying files from lower image to upper image...")
    with open(variant.lower_files, "r") as f:
        genpack_helper = ["genpack-helper"]
        if debug: genpack_helper.append("-g")
        subprocess.run(genpack_helper + ["copy", variant.lower_image, variant.upper_image, "--dst-dir=upper"], 
                       stdin=f, check=True)

    logging.info("Executing package scripts and generating metadata...")
    os.makedirs(download_dir, exist_ok=True)
    nspawn_opts = []
    if overlay_override is not None:
        nspawn_opts.append(f"--genpack-overlay-dir={overlay_override}")
    subprocess.run(["genpack-helper", "nspawn"] + nspawn_opts + [
                    f"--download-dir={download_dir}",
                    f"--overlay-image={variant.upper_image}:upper",
                    "-E", f"ARTIFACT={genpack_json['name']}",
                    variant.lower_image, "exec-package-scripts-and-generate-metadata"],
                    check=True)

    # merge genpack.json
    merged_genpack_json = {}
    merge_genpack_json(merged_genpack_json, genpack_json, ["genpack.json"], [
        "users","groups", "services", "arch", "variants"
    ], variant)

    # create groups
    groups = merged_genpack_json.get("groups", [])
    for group in groups:
        name = group if isinstance(group, str) else None
        gid = None
        if name is None:
            if not isinstance(group, dict): raise Exception("group must be string or dict")
            #else
            if "name" not in group: raise Exception("group dict must have 'name' key")
            #else
            name = group["name"]
            if "gid" in group: gid = group["gid"]
        groupadd_cmd = ["groupadd"]
        if gid is not None: groupadd_cmd += ["-g", str(gid)]
        groupadd_cmd.append(name)
        logging.info("Creating group %s..." % name)
        subprocess.run(["genpack-helper", "nspawn", f"--overlay-image={variant.upper_image}:upper", variant.lower_image] + groupadd_cmd, check=True)

    # create users
    users = merged_genpack_json.get("users", [])
    for user in users:
        name = user if isinstance(user, str) else None
        if name is None:
            if not isinstance(user, dict): raise Exception("user must be string or dict")
            #else
            if "name" not in user: raise Exception("user dict must have 'name' key")
            #else
            name = user["name"]
        uid = user.get("uid", None)
        comment = user.get("comment", None)
        home = user.get("home", None)
        create_home = user.get("create_home", user.get("create-home", True))
        shell = user.get("shell", None)
        initial_group = user.get("initial_group", user.get("initial-group", None))
        additional_groups = user.get("additional_groups", user.get("additional-groups", []))
        if isinstance(additional_groups, str):
            additional_groups = [additional_groups]
        elif not isinstance(additional_groups, list):
            raise Exception("additional-groups must be list or string")
        if "shell" in user: shell = user["shell"]
        empty_password = user.get("empty_password", user.get("empty-password", False))
        useradd_cmd = ["useradd"]
        if uid is not None: useradd_cmd += ["-u", str(uid)]
        if comment is not None: useradd_cmd += ["-c", comment]
        if home is not None: useradd_cmd += ["-d", home]
        if initial_group is not None: useradd_cmd += ["-g", initial_group]
        if len(additional_groups) > 0:
            useradd_cmd += ["-G", ",".join(additional_groups)]
        if shell is not None: useradd_cmd += ["-s", shell]
        if create_home: useradd_cmd += ["-m"]
        if empty_password: useradd_cmd += ["-p", ""]
        useradd_cmd.append(name)
        logging.info("Creating user %s..." % name)
        subprocess.run(["genpack-helper", "nspawn", f"--overlay-image={variant.upper_image}:upper", variant.lower_image] + useradd_cmd, check=True)

    # copy contents from files directory to upper image
    script = """set -e
if [ -d /mnt/host/files ]; then
    echo "Copying files from /mnt/host/files to upper image..."
    cp -rdv /mnt/host/files/. /
fi
execute-artifact-build-scripts"""
    subprocess.run(["genpack-helper", "nspawn", 
                    "-E", f"ARTIFACT={genpack_json['name']}", "--console=pipe", 
                    f"--download-dir={download_dir}",
                    f"--overlay-image={variant.upper_image}:upper", variant.lower_image, "sh"], 
                   input=script, text=True, check=True)

    if "setup_commands" in genpack_json:
        setup_commands = genpack_json["setup_commands"]
        if not isinstance(setup_commands, list):
            raise ValueError("setup_commands must be a list")
        for cmd in setup_commands:
            if isinstance(cmd, str):
                logging.info(f"Executing setup command: {cmd}")
                subprocess.run(["genpack-helper", "nspawn", 
                                f"--overlay-image={variant.upper_image}:upper", 
                                f"--download-dir={download_dir}",
                                "-E", f"ARTIFACT={genpack_json['name']}",
                                variant.lower_image, "sh", "-c", cmd], check=True)
            elif isinstance(cmd, dict):
                pass # TBD: support more complex command with options
            else:
                raise ValueError("setup_commands must be a list of strings or dicts")

    # enable services
    services = merged_genpack_json.get("services", [])
    if len(services) > 0:
        subprocess.run(["genpack-helper", "nspawn", f"--overlay-image={variant.upper_image}:upper", variant.lower_image, "systemctl", "enable"] + services, check=True)

def upper_bash(variant):
    if not os.path.isfile(variant.upper_image):
        raise FileNotFoundError(f"Upper layer image {variant.upper_image} does not exist. Please run 'upper' first")
    logging.info("Running bash in the upper directory for debugging.")
    subprocess.run(["genpack-helper", "nspawn", f"--overlay-image={variant.upper_image}:upper", variant.lower_image, "bash"], check=True)

def pack(variant, compression=None):
    if not os.path.isfile(variant.lower_image):
        raise FileNotFoundError(f"Lower image {variant.lower_image} does not exist. Please run 'lower' first.")
    if not os.path.isfile(variant.lower_files):
        raise FileNotFoundError(f"Lower files {variant.lower_files} does not exist. Please run 'lower' first.")
    if not os.path.isfile(variant.upper_image):
        raise FileNotFoundError(f"Upper layer image {variant.upper_image} does not exist. Please run 'upper' first.")
    #else

    merged_genpack_json = {}
    merge_genpack_json(merged_genpack_json, genpack_json, ["genpack.json"], ["outfile","variants"])

    name = genpack_json["name"]
    if variant is not None and variant.name is not None:
        name += f"-{variant.name}"
    outfile = merged_genpack_json.get("outfile", f"{name}-{arch}.squashfs")

    if compression is None:
        compression = genpack_json.get("compression", "gzip")
    
    compression_opts = []
    if compression == "xz":
        compression_opts = ["-comp", "xz", "-b", "1M"]
    elif compression == "gzip":
        compression_opts = ["-Xcompression-level", "1"]
    elif compression == "lzo":
        compression_opts = ["-comp", "lzo"]
    elif compression == "none":
        compression_opts = ["-no-compression"]
    else:
        raise ValueError(f"Unknown compression type: {compression}")

    cmdline = ["mksquashfs", "/mnt/extra/upper", os.path.join("/mnt/host",outfile), "-wildcards", "-noappend", "-no-exports"]
    cmdline += compression_opts
    cmdline += ["-e", "build", "build.d", "build.d/*", "var/log/*.log", "var/tmp/*"]

    logging.info(f"Creating SquashFS image: {outfile} with compression {compression}")
    if os.path.exists(outfile):
        logging.info(f"Output file {outfile} already exists, removing it.")
        os.remove(outfile)

    subprocess.run(["genpack-helper", "nspawn", f"--extra-image={variant.upper_image}", variant.lower_image] + cmdline, check=True)

def get_latest_mtime(*args):
    latest = 0.0
    for arg in args:
        if isinstance(arg, float): latest = max(latest, arg)
        elif isinstance(arg, str):
            if os.path.isfile(arg):
                latest = max(latest, os.path.getmtime(arg))
            elif os.path.isdir(arg):
                latest = max(latest, os.path.getmtime(arg), get_latest_mtime(*(os.path.join(arg, f) for f in os.listdir(arg) if os.path.exists(os.path.join(arg, f)))))

        elif isinstance(arg, list):
            latest = max(latest, get_latest_mtime(*arg))

    logging.debug(f"Latest mtime from {args} is {latest}")
    return latest

def create_archive():
    logging.info("Creating archive of the current directory...")
    name = genpack_json.get("name", os.path.basename(os.getcwd()))
    archive_name = f"genpack-{name}.tar.gz"
    if os.path.isfile(archive_name):
        logging.info(f"Archive {archive_name} already exists, removing it.")
        os.remove(archive_name)

    targets = []
    if os.path.isfile("genpack.json5"): targets.append("genpack.json5")
    elif os.path.isfile("genpack.json"): targets.append("genpack.json")

    if os.path.isdir("files"): targets.append("files")
    if os.path.isdir("savedconfig"): targets.append("savedconfig")
    if os.path.isdir("patches"): targets.append("patches")
    if os.path.isdir("kernel"): targets.append("kernel")
    if os.path.isdir("overlay"): targets.append("overlay")

    subprocess.run(["tar", "zcvf", archive_name] + targets, check=True)

    logging.info(f"Archive created: {archive_name}")
    return archive_name

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Genpack image Builder")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    parser.add_argument("--overlay-override", default=None, help="Directory to override genpack-overlay")
    parser.add_argument("--independent-binpkgs", action="store_true", help="Use independent binpkgs, do not use shared one")
    parser.add_argument("--deep-depclean", action="store_true", help="Perform deep depclean, removing all non-runtime packages"  )
    parser.add_argument("--compression", choices=["gzip", "xz", "lzo", "none"], default=None, help="Compression type for the final SquashFS image")
    parser.add_argument("--devel", action="store_true", help="Generate development image, if supported by genpack.json")
    parser.add_argument("--variant", default=None, help="Variant to use from genpack.json, if supported")
    parser.add_argument("action", choices=["build", "lower", "bash", "upper", "upper-bash", "upper-clean", "pack", "archive"], nargs="?", default="build", help="Action to perform")
    args = parser.parse_args()
    debug = args.debug
    logging.basicConfig(level=logging.DEBUG if debug else logging.INFO)

    genpack_json, genpack_json_time = load_genpack_json()
    if "name" not in genpack_json:
        genpack_json["name"] = os.path.basename(os.getcwd())
        logging.warning(f"'name' not found in genpack.json. using default: {genpack_json['name']}")  

    if not os.path.isfile(".gitignore"):
        with open(".gitignore", "w") as f:
            f.write("/work/\n")
            f.write("/*.squashfs\n")
            f.write("/*.img\n")
            f.write("/*.iso\n")
            f.write("/*.tar.gz\n")
            f.write("/.vscode/\n")
        logging.info("Created .gitignore file with default settings.")
    
    if not os.path.isdir(".vscode"):
        os.mkdir(".vscode")
        if not os.path.isfile(".vscode/settings.json"):
            with open(".vscode/settings.json", "w") as f:
                f.write('{\n')
                f.write('  "files.exclude": {"work/": true, "*.squashfs": true}\n')
                f.write('  "search.exclude": {"work/": true, "*.squashfs": true}\n')
                f.write('  "python.analysis.exclude": ["work/"]\n')
                f.write('}\n')
            logging.info("Created .vscode/settings.json with default settings.")

    if args.action == "archive":
        create_archive()
        exit(0)

    overlay_override = args.overlay_override

    independent_binpkgs = args.independent_binpkgs or genpack_json.get("independent_binpkgs", False)
    deep_depclean = args.deep_depclean

    variant = Variant(args.variant or genpack_json.get("default_variant", None))
    if variant.name is not None:
        available_variants = genpack_json.get("variants", {})
        if variant.name not in available_variants:
            raise ValueError(f"Variant '{variant.name}' is not available in genpack.json. Available variants: {list(available_variants.keys())}")

    # check if genpack-helper is properly installed
    subprocess.run(["genpack-helper", "ping"], check=True)

    if args.action == "bash":
        bash(variant)
        exit(0)
    elif args.action == "upper-bash":
        upper_bash(variant)
        exit(0)
    elif args.action == "upper-clean":
        raise ValueError("upper-clean is not implemented yet, use 'upper' and then remove upper directory manually.")
    #else

    def is_lower_files_outdated():
        if not os.path.exists(variant.lower_files): return False
        #else
        lower_files_mtime = os.path.getmtime(variant.lower_files)
        latest_mtime = get_latest_mtime(genpack_json_time, "savedconfig", "patches", "kernel", "overlay")
        if lower_files_mtime < latest_mtime:
            logging.info(f"Lower files {variant.lower_files} is outdated, rebuilding lower layer.")
            return True
        world_mtime = subprocess.run(["genpack-helper", "lower", variant.lower_image, "stat", "-c", "%Y", "/var/lib/portage/world"], capture_output=True, text=True)
        if world_mtime.returncode != 0:
            logging.error("Failed to get world file mtime. rebuilding lower layer.")
            return True
        #else
        if lower_files_mtime < int(world_mtime.stdout.strip()):
            logging.info(f"Lower files {variant.lower_files} is older than world file, rebuilding lower layer.")
            return True
        #else
        return False

    if args.action in ["build", "lower"]:
        if is_lower_files_outdated() or (args.action == "lower" and os.path.exists(variant.lower_files)):
            os.remove(variant.lower_files)
        lower(variant, args.devel)
    if args.action in ["build", "upper"]:
        upper(variant)
    if args.action in ["build", "pack"]:
        pack(variant, args.compression)

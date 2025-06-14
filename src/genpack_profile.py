import os,subprocess,glob
import workdir,user_dir,upstream,genpack_json,global_options
from sudo import sudo

CONTAINER_NAME="genpack-profile-%d" % os.getpid()
DEFAULT_OVERLAY_SOURCE = "https://github.com/wbrxcorp/genpack-overlay.git"
_extract_portage_done = False
_pull_overlay_done = False
_overlay_source = DEFAULT_OVERLAY_SOURCE

def set_overlay_source(overlay_source):
    global _overlay_source
    _overlay_source = overlay_source

class Profile:
    def __init__(self, profile):
        self.name = profile
        self.profile_dir = os.path.join(".", "profiles", profile)
        if not os.path.isdir(self.profile_dir):
            raise Exception("No such profile: %s" % profile)
    def __hash__(self):
        return hash(self.name)
    def __eq__(self, other):
        return isinstance(other, Profile) and self.name == other.name
    def get_dir(self):
        return self.profile_dir
    def get_workdir(self):
        return workdir.get_profile(self.name)
    def get_gentoo_workdir(self):
        return workdir.get_profile(self.name, "root")
    def get_cache_workdir(self):
        return workdir.get_profile(self.name, "cache")
    def get_gentoo_workdir_time(self):
        gentoo_dir = self.get_gentoo_workdir()
        done_file = os.path.join(gentoo_dir, ".done")
        if not os.path.isfile(done_file): return None
        #else
        # get latest pkgdb timestamp
        pkgdb_dir = os.path.join(gentoo_dir, "var/db/pkg")
        if not os.path.isdir(pkgdb_dir): return None
        latest_pkgdb_timestamp = os.path.getmtime(pkgdb_dir)
        for root, dirs, files in os.walk(pkgdb_dir):
            for name in dirs:
                timestamp = os.path.getmtime(os.path.join(root, name))
                if timestamp > latest_pkgdb_timestamp:
                    latest_pkgdb_timestamp = timestamp
        #remove .done file if it is older than latest pkgdb timestamp
        done_file_time = os.stat(done_file).st_mtime
        if done_file_time < latest_pkgdb_timestamp:
            os.unlink(done_file)
            return None
        #else
        return done_file_time
    def set_gentoo_workdir_time(self):
        gentoo_dir = self.get_gentoo_workdir()
        with open(os.path.join(gentoo_dir, ".done"), "w") as f:
            pass
    def get_all_profiles():
        profile_names = genpack_json.get("profiles", [])
        if not isinstance(profile_names, list): raise Exception("profiles must be a list")
        if len(profile_names) == 0:
            for profile_name in os.listdir(os.path.join(".", "profiles")):
                profile_names.append(profile_name)
        profiles = []
        for profile_name in profile_names:
            profiles.append(Profile(profile_name))
        return profiles
    def get_profiles_have_set(set_name):
        profiles = []
        for profile_name in os.listdir(os.path.join(".", "profiles")):
            if os.path.isfile(os.path.join(".", "profiles", profile_name, "etc/portage/sets", set_name)):
                profiles.append(Profile(profile_name))
        return profiles
    def exists(profile_name):
        return os.path.isdir(os.path.join(".", "profiles", profile_name))

def lower_exec(lower_dir, cache_dir, portage_dir, cmdline, nspawn_opts=[]):
    nspawn_cmdline = ["systemd-nspawn", "-q", "--suppress-sync=true", "-M", CONTAINER_NAME, "-D", lower_dir, 
        "--bind=%s:/var/cache" % os.path.abspath(cache_dir),
        "--capability=CAP_MKNOD,CAP_SYS_ADMIN",
        "--bind-ro=%s:/var/db/repos/gentoo" % os.path.abspath(portage_dir)
    ]

    cpus = global_options.cpus()
    if cpus is not None:
        nspawn_cmdline.append("--setenv=MAKEOPTS=-j%d" % cpus)
        nspawn_cmdline.append("--setenv=NINJAFLAGS=-j%d" % cpus)
    
    nspawn_cmdline += global_options.env_as_systemd_nspawn_args()
    nspawn_cmdline += nspawn_opts
    nspawn_cmdline += cmdline

    subprocess.check_call(sudo(nspawn_cmdline))

def extract_portage():
    global _extract_portage_done
    if _extract_portage_done: return
    _extract_portage_done = True
    with user_dir.portage_tarball() as portage_tarball:
        portage_dir = workdir.get_portage(True)
        upstream.download_if_necessary(upstream.get_latest_portage_tarball_url(), portage_tarball)

        # if portage is up-to-date, do nothing
        done_file = os.path.join(portage_dir, ".done")
        last_time_timestamp = 0
        if os.path.isfile(done_file):
            try:
                with open(done_file, "r") as f:
                    last_time_timestamp = float(f.read())
            except ValueError:
                os.unlink(done_file)
        tarball_timestamp = os.stat(portage_tarball).st_mtime
        if tarball_timestamp <= last_time_timestamp: return
        #else
        workdir.move_to_trash(portage_dir)

        print("Extracting portage into %s..." % portage_dir)
        os.makedirs(portage_dir)
        subprocess.check_call(sudo(["tar", "xpf", portage_tarball, "--strip-components=1", "-C", portage_dir]))
        with open(done_file, "w") as f:
            f.write(str(tarball_timestamp))

def extract_stage3(root_dir, variant = "systemd"):
    stage3_done_file = os.path.join(root_dir, ".stage3-done")
    with user_dir.stage3_tarball(variant) as stage3_tarball:
        upstream.download_if_necessary(upstream.get_latest_stage3_tarball_url(variant), stage3_tarball)
        if os.path.exists(stage3_done_file) and os.stat(stage3_done_file).st_mtime > os.stat(stage3_tarball).st_mtime:
            return False # stage3 already extracted

        workdir.move_to_trash(root_dir)
        os.makedirs(root_dir)
        print("Extracting stage3...")
        subprocess.check_call(sudo(["tar", "xpf", stage3_tarball, "--strip-components=1", "--exclude=./dev/*", "-C", root_dir]))

    kernel_config_dir = os.path.join(root_dir, "etc/kernels")
    repos_dir = os.path.join(root_dir, "var/db/repos/gentoo")
    subprocess.check_call(sudo(["mkdir", "-p", kernel_config_dir, repos_dir]))
    subprocess.check_call(sudo(["chmod", "-R", "o+rw", 
        os.path.join(root_dir, "etc/portage"), os.path.join(root_dir, "usr/src"), 
        os.path.join(root_dir, "var/db/repos"), os.path.join(root_dir, "var/cache"), 
        kernel_config_dir, os.path.join(root_dir, "usr/local")]))
    with open(os.path.join(root_dir, "etc/portage/make.conf"), "a") as f:
        f.write('FEATURES="-sandbox -usersandbox -network-sandbox"\n')
    with open(stage3_done_file, "w") as f:
        pass
    return True

def sync_overlay(root_dir):
    if _overlay_source.startswith("https://") or _overlay_source.startswith("git@github.com:"):
        with user_dir.overlay_dir() as overlay_dir:
            global _pull_overlay_done
            if not _pull_overlay_done:
                if os.path.exists(os.path.join(overlay_dir, ".git")):
                    print("Syncing genpack-overlay...")
                    if subprocess.call(["git", "-C", overlay_dir, "pull"]) != 0:
                        print("Failed to pull genpack-overlay, proceeding without sync")
                else:
                    print("Cloning genpack-overlay...")
                    subprocess.check_call(["git", "clone", _overlay_source, overlay_dir])
                _pull_overlay_done = True
            subprocess.check_call(sudo(["rsync", "-a", "--delete", overlay_dir, os.path.join(root_dir, "var/db/repos/")]))
    else: # from local directory
        print("Using genpack-overlay from %s" % _overlay_source)
        if not os.path.exists(os.path.join(root_dir, "var/db/repos/genpack-overlay")):
            os.makedirs(os.path.join(root_dir, "var/db/repos/genpack-overlay"))
        subprocess.check_call(sudo(["rsync", "-a", "--delete", _overlay_source + "/", os.path.join(root_dir, "var/db/repos/genpack-overlay/")]))

    if not os.path.exists(os.path.join(root_dir, "etc/portage/repos.conf")):
        subprocess.check_call(sudo(["mkdir", "-m", "0777", os.path.join(root_dir, "etc/portage/repos.conf")]))
    if not os.path.isfile(os.path.join(root_dir, "etc/portage/repos.conf/genpack-overlay.conf")):
        with open(os.path.join(root_dir, "etc/portage/repos.conf/genpack-overlay.conf"), "w") as f:
            f.write("[genpack-overlay]\nlocation=/var/db/repos/genpack-overlay")

def scan_files(dir):
    files_found = []
    newest_file = 0
    for root,dirs,files in os.walk(dir, followlinks=True):
        if len(files) == 0: continue
        for f in files:
            mtime = os.lstat(os.path.join(root,f)).st_mtime
            if mtime > newest_file: newest_file = mtime
            files_found.append(os.path.join(root[len(dir) + 1:], f))
    return (files_found, newest_file)

def link_files(srcdir, dstdir):
    files_to_link, newest_file = scan_files(srcdir)

    for f in files_to_link:
        src = os.path.join(srcdir, f)
        dst = os.path.join(dstdir, f)
        dst_dir = os.path.dirname(dst)
        if os.path.exists(dst_dir):
            if not os.path.isdir(dst_dir): raise Exception("%s should be a directory" % dst_dir)
        else:
            subprocess.check_call(sudo(["mkdir", "-p", dst_dir]))
        if os.path.islink(src):
            subprocess.check_call(sudo(["cp", "-d", "--remove-destination", src, dst]))
        else:
            subprocess.check_call(sudo(["ln", "-f", src, dst]))
    
    return newest_file

def prepare(profile, disable_using_binpkg = False, setup_only = False):
    extract_portage()
    gentoo_dir = profile.get_gentoo_workdir()
    fresh_stage3 = extract_stage3(gentoo_dir)
    sync_overlay(gentoo_dir)

    newest_file = 0
    newest_file = max(newest_file, link_files(profile.get_dir(), gentoo_dir))

    # move files under /var/cache
    cache_dir = profile.get_cache_workdir()
    os.makedirs(cache_dir, exist_ok=True)
    subprocess.check_call(sudo(["rsync", "-a", "--remove-source-files", os.path.join(gentoo_dir,"var/cache/"), cache_dir]))

    portage_dir = workdir.get_portage(False)
    done_file_time = profile.get_gentoo_workdir_time()

    portage_time = os.stat(os.path.join(portage_dir, "metadata/timestamp")).st_mtime
    overlay_time = 0
    overlay_dir = user_dir.get_overlay_dir()
    # check latest mtime of overlay_dir/**/Manifect
    for manifest in glob.glob("**/Manifest", root_dir=overlay_dir, recursive=True):
        overlay_time = max(overlay_time, os.stat(os.path.join(overlay_dir, manifest)).st_mtime)
    newest_file = max(newest_file, portage_time, overlay_time)

    if setup_only or (done_file_time is not None and  newest_file <= done_file_time): return

    #else
    # install genpack-progs
    if disable_using_binpkg:
        print("Disabling using binary packages")
        lower_exec(gentoo_dir, cache_dir, portage_dir, ["emerge", "-b", "--usepkg=n", "-uDN", "genpack-progs", "--keep-going"])
    else:
        lower_exec(gentoo_dir, cache_dir, portage_dir, ["emerge", "-bk", "--binpkg-respect-use=y", "-uDN", "genpack-progs", "--keep-going"])

    if fresh_stage3:
        # unmerge unnecceary pythons
        lower_exec(gentoo_dir, cache_dir, portage_dir, ["check-unwanted-pythons", "--unmerge"])

    # do preparation
    lower_exec(gentoo_dir, cache_dir, portage_dir, ["genpack-prepare"] + (["--disable-using-binpkg"] if disable_using_binpkg else []))

def bash(profile, bind = []):
    prepare(profile, False, True)
    print("Entering profile %s with bash..." % profile.name)
    print("Run `eclean-pkg -d` to clean up binary packages which is uninstalled.")
    gentoo_dir = profile.get_gentoo_workdir()
    cache_dir = profile.get_cache_workdir()
    portage_dir = workdir.get_portage(False)
    nspawn_opts = []
    for b in bind:
        nspawn_opts.append("--bind=%s" % b)
    try:
        lower_exec(gentoo_dir, cache_dir, portage_dir, ["bash"], nspawn_opts=nspawn_opts)
    except subprocess.CalledProcessError:
        # ignore exception raised by subprocess.check_call
        pass

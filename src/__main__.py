#!/usr/bin/python3
# Copyright (c) 2021-2023 Walbrix Corporation
# https://github.com/wbrxcorp/genpack/blob/main/LICENSE

import os,sys,subprocess,atexit,logging
import upstream,workdir,genpack_profile,genpack_artifact,qemu,global_options
from sudo import sudo

def prepare(args):
    genpack_profile.set_overlay_source(args.overlay_source)
    profiles = []
    if len(args.profile) == 0 and os.path.isdir("./profiles"):
        profiles += genpack_profile.Profile.get_all_profiles()
    else:
        for profile in args.profile:
            profiles.append(genpack_profile.Profile(profile))
    if len(profiles) == 0: profiles.append(genpack_profile.Profile("default"))

    disable_using_binpkg = args.disable_using_binpkg
    for profile in profiles:
        print("Preparing profile %s..." % profile.name)
        try:
            genpack_profile.prepare(profile, disable_using_binpkg, False)
        except Exception as e:
            if args.keep_going:
                logging.error("Error occurred while preparing profile %s: %s" % (profile.name, str(e)))
            else:
                raise e

def bash(args):
    genpack_profile.set_overlay_source(args.overlay_source)
    if global_options.debug():
        logging.debug(args.bind)
    profile = genpack_profile.Profile(args.profile)
    genpack_profile.bash(profile, args.bind)

def build(args):
    genpack_profile.set_overlay_source(args.overlay_source)
    artifacts = []
    if len(args.artifact) == 0 and os.path.isdir("./artifacts"):
        artifacts += [artifact for artifact in genpack_artifact.Artifact.get_all_artifacts() if artifact.arch_matches()]
    else:
        for artifact in args.artifact:
            artifacts.append(genpack_artifact.Artifact(artifact))
    
    if len(artifacts) == 0: artifacts.append(genpack_artifact.Artifact("default"))

    if args.variant is not None:
        if len(artifacts) > 1:
            raise Exception("Cannot specify variant when building multiple artifacts")
        else:
            artifacts[0].set_active_variant(args.variant)

    profiles = set()
    profiles_prepared = set()

    for artifact in artifacts:
        if not artifact.arch_matches():
            raise Exception("Architecture mismatch: %s" % artifact.name)
        profiles.add(artifact.get_profile())

    disable_using_binpkg = args.disable_using_binpkg
    for profile in profiles:
        print("Preparing profile %s..." % profile.name)
        try:
            genpack_profile.prepare(profile, disable_using_binpkg)
            profiles_prepared.add(profile)
        except Exception as e:
            if args.keep_going:
                logging.error("Error occurred while preparing profile %s: %s" % (profile.name, str(e)))
            else:
                raise e

    for artifact in artifacts:
        if artifact.get_profile() not in profiles_prepared:
            logging.warning("Profile %s is not prepared. Skipping %s." % (artifact.get_profile().name, artifact.name))
            continue
        try:
            if artifact.is_up_to_date():
                print("Artifact %s is up-to-date" % artifact.name)
            else:
                print("Building artifact %s..." % artifact.name)
                genpack_artifact.build(artifact)
            if not artifact.is_outfile_up_to_date():
                print("Packing artifact %s..." % artifact.name)
                genpack_artifact.pack(artifact, None, args.compression_override)
        except Exception as e:
            if args.keep_going:
                logging.error("Error occurred while building artifact %s: %s" % (artifact.name, str(e)))
            else:
                raise e

    print("Done.")
    
def run(args):
    artifact = genpack_artifact.Artifact(args.artifact)
    if args.variant is not None: artifact.set_active_variant(args.variant)

    if not artifact.is_up_to_date():
        print("Artifact %s is not up-to-date" % artifact.name)
        sys.exit(1)

    print("Pressing ']' 3 times will exit the container and return to the host.")
    cmdline = ["systemd-nspawn", "--suppress-sync=true", "-M", "genpack-run-%d" % os.getpid(), 
            "-q", "-D", artifact.get_workdir(), "--network-veth"] + global_options.env_as_systemd_nspawn_args()
    if args.bash: cmdline.append("/bin/bash")
    else: cmdline.append("-b")
    subprocess.call(sudo(cmdline))

def _qemu(args):
    artifact = genpack_artifact.Artifact(args.artifact)
    if args.variant is not None: artifact.set_active_variant(args.variant)
    outfile = artifact.get_outfile()
    qemu.run(outfile, os.path.join(args.workdir, "qemu.img"), args.drm, args.data_volume, args.system_ini)

def clean(args):
    subprocess.check_call(sudo(["rm", "-rf", workdir.get(None, False)]))

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--debug", action="store_true", help="Enable debug mode")
    parser.add_argument("--base", default=None, help="Base URL contains dirs 'releases' 'snapshots'")
    parser.add_argument("--workdir", default=None, help="Working directory to use(default:./work)")
    parser.add_argument("--env", default=None, help="Environment variable in NAME=VALUE format (comma separated)")
    parser.add_argument('--cpus', default=None, type=int, help='Number of CPUs to use')

    subparsers = parser.add_subparsers()
    # prepare subcommand
    prepare_parser = subparsers.add_parser('prepare', help='Prepare profiles')
    prepare_parser.add_argument('profile', nargs='*', default=[], help='Profiles to prepare')
    prepare_parser.add_argument('--keep-going', action='store_true', help='Keep going even if an error occurs')
    prepare_parser.add_argument('--disable-using-binpkg', action='store_true', help='Disable using binary packages')
    prepare_parser.add_argument('--overlay-source', default=genpack_profile.DEFAULT_OVERLAY_SOURCE, help='Source git URL or directory for overlay files')
    prepare_parser.set_defaults(func=prepare)

    # bash subcommand
    bash_parser = subparsers.add_parser('bash', help='Run bash on a profile')
    bash_parser.add_argument('profile', nargs='?', default='default', help='Profile to run bash')
    bash_parser.add_argument('--bind', action='append', default=[], help="Bind mount in HOST_PATH:CONTAINER_PATH format")
    bash_parser.add_argument('--overlay-source', default=genpack_profile.DEFAULT_OVERLAY_SOURCE, help='Source git URL or directory for overlay files')
    bash_parser.set_defaults(func=bash)

    # build subcommand
    build_parser = subparsers.add_parser('build', help='Build artifacts')
    build_parser.add_argument("artifact", default=[], nargs='*', help="Artifacts to build")
    build_parser.add_argument('--keep-going', action='store_true', help='Keep going even if an error occurs')
    build_parser.add_argument('--disable-using-binpkg', action='store_true', help='Disable using binary packages')
    build_parser.add_argument('--variant', default=None, help='Variant to build')
    build_parser.add_argument('--compression-override', default=None, help='Override compression method')
    build_parser.add_argument('--overlay-source', default=genpack_profile.DEFAULT_OVERLAY_SOURCE, help='Source git URL or directory for overlay files')
    build_parser.set_defaults(func=build)

    # run subcommand
    run_parser = subparsers.add_parser('run', help='Run an artifact')
    run_parser.add_argument('--bash', action='store_true', help='Run bash instead of spawning container')
    run_parser.add_argument('artifact', nargs='?', default='default', help='Artifact to run')
    run_parser.add_argument('--variant', default=None, help='Variant to run')
    run_parser.set_defaults(func=run)

    # qemu subcommand
    qemu_parser = subparsers.add_parser('qemu', help='Run an artifact using qemu')
    qemu_parser.add_argument('artifact', nargs='?', default='default', help='Artifact to run')
    qemu_parser.add_argument('--variant', default=None, help='Variant to run')
    qemu_parser.add_argument('--drm', action='store_true', help='Enable DRM(virgl) when running qemu')
    qemu_parser.add_argument('--data-volume', action='store_true', help='Create data partition when running qemu')
    qemu_parser.add_argument('--system-ini', help='system.ini file when running qemu')
    qemu_parser.set_defaults(func=_qemu)

    # clean subcommand
    clean_parser = subparsers.add_parser('clean', help='Clean up artifacts')
    clean_parser.add_argument('artifact', nargs='?', default='default', help='Artifact to clean')
    clean_parser.set_defaults(func=clean)

    args = parser.parse_args()

    global_options.read_global_options(args)
    if global_options.debug():
        logging.basicConfig(level=logging.DEBUG)
        logging.debug("Debug mode enabled")

    if global_options.base() is not None: 
        upstream.set_base_url(global_options.base())
        logging.info("Base URL set to %s" % global_options.base())
    if global_options.workdir() is not None:
        workdir.set(global_options.workdir())
        logging.info("Working directory set to %s" % global_options.workdir())
    
    import genpack_json
    genpack_json.load()

    if not hasattr(args, 'func'):
        parser.print_help()
        sys.exit(1)
    #else
    atexit.register(workdir.cleanup_trash)
    args.func(args)

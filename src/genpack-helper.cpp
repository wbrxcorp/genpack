#include <sys/mount.h>
#include <sys/stat.h>
#include <sys/wait.h>

#include <unistd.h>
#include <pwd.h>
#include <grp.h>

#include <filesystem>
#include <fstream>
#include <cstring>
#include <functional>

#include <libmount/libmount.h>

#include <argparse/argparse.hpp>

bool debug = false;

bool is_mounted(const std::filesystem::path& path)
{
    if (!std::filesystem::is_directory(path)) {
        std::cerr << "Path is not a directory: " << path << std::endl;
        return false; // Path is not a directory
    }
    // else
    std::shared_ptr<libmnt_table> tb(mnt_new_table_from_file("/proc/self/mountinfo"),mnt_unref_table);
    std::shared_ptr<libmnt_cache> cache(mnt_new_cache(), mnt_unref_cache);
    mnt_table_set_cache(tb.get(), cache.get());

    int rst = -1;
    return mnt_table_find_target(tb.get(), path.c_str(), MNT_ITER_BACKWARD)? 
        true : false;
}

void must_be_owned_by_original_user(const std::filesystem::path& path) 
{
    uid_t original_uid = getuid();
    if (original_uid == 0) {
        // If running as root, we can skip the ownership check
        return;
    }

    struct stat file_stat;
    if (stat(path.c_str(), &file_stat) != 0) {
        throw std::runtime_error("Failed to stat file: " + path.string());
    }
    // Check if the file is owned by the original user
    if (file_stat.st_uid != original_uid) {
        throw std::runtime_error("File is not owned by the original user: " + path.string());
    }
}

void must_be_accessible_by_original_user(const std::filesystem::path& path) 
{
    // check if the file exists and is a regular file
    if (!std::filesystem::exists(path) || !std::filesystem::is_regular_file(path)) {
        throw std::runtime_error("File does not exist or is not a regular file: " + path.string());
    }
    // Check if the file is writable by the original user
    struct stat file_stat;
    if (stat(path.c_str(), &file_stat) != 0) {
        throw std::runtime_error("Failed to stat file: " + path.string());
    }

    auto mode = file_stat.st_mode;

    uid_t original_uid = getuid();
    if (original_uid == 0) original_uid = file_stat.st_uid; // If running as root, use the file's owner UID
    if (file_stat.st_uid == original_uid && (mode & S_IWUSR)) {
        return; // File is writable by the original user
    }
    // else 
    auto passwd_entry = getpwuid(original_uid); // Ensure the original user is in the group list
    gid_t groups[32];
    int ngroups = 32;
    if (getgrouplist(passwd_entry->pw_name, passwd_entry->pw_gid, groups, &ngroups) < 0) {
        throw std::runtime_error("Failed to get groups for user: " + std::string(passwd_entry->pw_name) + " (belongs to too many groups?)");
    }

    for (int i = 0; i < ngroups; ++i) {
        if (file_stat.st_gid == groups[i] && (mode & S_IWGRP)) {
            return; // File is writable by one of the groups of the original user
        }
    }

    // else

    if (file_stat.st_mode & S_IWOTH) {
        return; // File is writable by others
    }

    //else
    throw std::runtime_error("File is not writable by the original user or their groups: " + path.string());
}

class RealRootSection {
public:
    RealRootSection() {
        original_uid_ = getuid();
        if (setuid(0) != 0) {
            throw std::runtime_error("Failed to set real user ID to root");
        }
    }

    ~RealRootSection() {
        if (setreuid(original_uid_, -1) != 0) {
            std::cerr << "Warning: Failed to restore original user ID: " << strerror(errno) << std::endl;
        }
        if (debug) {
            std::cout << "uid=" << getuid() << " euid=" << geteuid() << std::endl;
        }
    }
private:
    uid_t original_uid_;
};

void mount_loop(const std::filesystem::path& source,
  const std::filesystem::path& mountpoint,
  const std::string& fstype = "auto")
{
    must_be_accessible_by_original_user(source);

    RealRootSection root_section; // real uid must be root to mount

    std::shared_ptr<libmnt_context> ctx(mnt_new_context(), mnt_free_context);
    mnt_context_set_fstype_pattern(ctx.get(), fstype.c_str());
    mnt_context_set_source(ctx.get(), source.c_str());
    mnt_context_set_target(ctx.get(), mountpoint.c_str());
    mnt_context_set_mflags(ctx.get(), MS_RELATIME);
    mnt_context_set_options(ctx.get(), "loop");

    auto rst = mnt_context_mount(ctx.get());
    auto status = mnt_context_get_status(ctx.get());
    auto helper_success = mnt_context_helper_executed(ctx.get()) == 1 ? (mnt_context_get_helper_status(ctx.get()) == 0) : true;

    if (rst > 0) {
        throw std::runtime_error("mnt_context_mount failed: " + std::string(strerror(errno)));
    }
    if (rst < 0) throw std::runtime_error("mnt_context_mount returned error(errno not set)");
    if (status != 1) throw std::runtime_error("mnt_context_get_status returned error");
    if (!helper_success) throw std::runtime_error("mnt_context_get_helper_status returned error");
}

class TempDir {
public:
    TempDir() {
        // Create a temporary directory
        char temp_dir_template[] = "/tmp/genpack-helper.XXXXXX";
        if (mkdtemp(temp_dir_template) == nullptr) {
            throw std::runtime_error("Failed to create temporary directory");
        }
        //else
        if (debug) {
            std::cout << "Temporary directory created: " << temp_dir_template << std::endl;
        }
        path_ = std::filesystem::path(temp_dir_template);
    }

    ~TempDir() {
        // Check if path is mounted
        if (is_mounted(path_)) {
            // If it's mounted, try to unmount it first
            if (debug) {
                std::cout << "Unmounting temporary directory: " << path_ << std::endl;
            }
            RealRootSection root_section;
            if (umount(path_.c_str()) != 0) {
                std::cerr << "Warning: Failed to unmount " << path_ << " (" << strerror(errno) << ")" << std::endl;
                return;
            }
        }
        
        // Remove the temporary directory
        if (debug) {
            std::cout << "Removing temporary directory: " << path_ << std::endl;
        }
        try {
            std::filesystem::remove_all(path_);
        } catch (const std::filesystem::filesystem_error& e) {
            std::cerr << "Error removing temporary directory: " << e.what() << std::endl;
        }
    }

    const std::filesystem::path& path() const {
        return path_;
    }

private:
    std::filesystem::path path_;
};

int fork_and_exec(const std::vector<std::string>& cmdline, const std::optional<std::filesystem::path>& chroot = std::nullopt)
{
    pid_t pid = fork();
    if (pid < 0) {
        perror("fork");
        return -1; // Fork failed
    }
    // else
    if (pid == 0) {
        // Child process
        if (chroot) {
            if (chdir(chroot->c_str()) != 0) {
                perror("chdir");
                exit(EXIT_FAILURE); // Change directory failed
            }
            if (::chroot(chroot->c_str()) != 0) {
                perror("chroot");
                exit(EXIT_FAILURE); // Chroot failed
            }
        }
        std::vector<char*> args;
        for (const auto& arg : cmdline) {
            args.push_back(const_cast<char*>(arg.c_str()));
        }
        args.push_back(nullptr); // Null-terminate the argument list

        execvp(args[0], args.data());
        perror("execvp"); // If execvp returns, it must have failed
        exit(EXIT_FAILURE);
    }
    // else
    int status;
    waitpid(pid, &status, 0); // Wait for the child process to finish
    return WIFEXITED(status) ? WEXITSTATUS(status) : -1; // Return exit status or -1 on error
}

void stage3(const std::filesystem::path& lower_img, const std::filesystem::path& archive_tar)
{
    TempDir temp_dir;
    mount_loop(lower_img, temp_dir.path(), "ext4");
    std::vector<std::string> cmdline = {"tar", "xpf", archive_tar.string(), "-C", temp_dir.path().string()};
    if (fork_and_exec(cmdline) != 0) {
        throw std::runtime_error("Failed to extract stage3 archive: " + archive_tar.string());
    }
}

int lower(const std::filesystem::path& lower_img, const std::vector<std::string>& cmdline)
{
    TempDir temp_dir;
    mount_loop(lower_img, temp_dir.path(), "ext4");
    if (debug) {
        std::cout << "uid=" << getuid() << " euid=" << geteuid() << std::endl;
    }
    RealRootSection root_section; // Ensure we are running as root for the command execution
    return fork_and_exec(cmdline, temp_dir.path());
}

std::string escape_colon(const std::filesystem::path& path) {
    // Escape colons in the path for systemd-nspawn
    std::string escaped = path.string();
    size_t pos = 0;
    while ((pos = escaped.find(':', pos)) != std::string::npos) {
        escaped.replace(pos, 1, "\\:");
        pos += 2; // Move past the escaped colon
    }
    return escaped;
}

struct NspawnOptions {
    std::map<std::string, std::string> env_vars;
    std::optional<std::string> console;
    std::optional<std::filesystem::path> genpack_overlay_dir;
    std::optional<std::filesystem::path> binpkgs_dir;
    std::optional<std::filesystem::path> download_dir;
    std::optional<std::pair<std::filesystem::path,std::filesystem::path>> overlay_image;
    std::optional<std::filesystem::path> extra_image;
};

int nspawn(const std::filesystem::path& lower_img,
    const std::vector<std::string>& cmdline,
    const NspawnOptions& options = {})
{
    must_be_owned_by_original_user(".");

    std::vector<std::string> nspawn_cmdline = {
        "systemd-nspawn", "-q", "--suppress-sync=true", 
        "--as-pid2", "-M", "genpack-" + std::to_string(getpid()), "--image=" + lower_img.string(),
        "--tmpfs=/var/tmp",
        "--capability=CAP_MKNOD,CAP_SYS_ADMIN,CAP_NET_ADMIN", // Portage's network sandbox needs CAP_NET_ADMIN
    };
    uid_t original_uid = getuid();
    // Bind mount the current directory to /mnt/host
    nspawn_cmdline.push_back(original_uid == 0 ? "--bind=.:/mnt/host" : "--bind=.:/mnt/host:rootidmap");
    if (options.binpkgs_dir) {
        must_be_owned_by_original_user(*options.binpkgs_dir);
        std::string bind = "--bind=" + escape_colon(*options.binpkgs_dir) + ":/var/cache/binpkgs";
        if (original_uid != 0) bind += ":rootidmap";
        nspawn_cmdline.push_back(bind);
    }
    if (options.download_dir) {
        must_be_owned_by_original_user(*options.download_dir);
        std::string bind = "--bind=" + escape_colon(*options.download_dir) + ":/var/cache/download";
        if (original_uid != 0) bind += ":rootidmap";
        nspawn_cmdline.push_back(bind);
    }
    if (options.genpack_overlay_dir) {
        must_be_owned_by_original_user(*options.genpack_overlay_dir);
        std::string bind = "--bind=" + escape_colon(*options.genpack_overlay_dir) + ":/var/db/repos/genpack-overlay";
        nspawn_cmdline.push_back(bind);
    }
    for (const auto& [key, value] : options.env_vars) {
        nspawn_cmdline.push_back("--setenv=" + key + "=" + value);
    }
    if (options.console) {
        nspawn_cmdline.push_back("--console=" + *options.console);
    }

    TempDir overlay_image_dir;
    if (options.overlay_image) {
        must_be_owned_by_original_user(options.overlay_image->first);
        mount_loop(options.overlay_image->first, overlay_image_dir.path(), "ext4");
        nspawn_cmdline.push_back("--overlay=+/:" + escape_colon(overlay_image_dir.path() / options.overlay_image->second) + ":/");
    }

    TempDir extra_image_dir;
    if (options.extra_image) {
        mount_loop(*options.extra_image, extra_image_dir.path(), "ext4");
        nspawn_cmdline.push_back("--bind=" + escape_colon(extra_image_dir.path()) + ":/mnt/extra");
    }

    nspawn_cmdline.insert(nspawn_cmdline.end(), cmdline.begin(), cmdline.end());
    RealRootSection root_section; // Ensure we are running as root for the command execution
    return fork_and_exec(nspawn_cmdline);
}

int copy(const std::filesystem::path& src_img, const std::filesystem::path& dst_img, const std::filesystem::path& dst_dir = "")
{
    must_be_owned_by_original_user(src_img);
    TempDir src_temp_dir;
    mount_loop(src_img, src_temp_dir.path(), "ext4");
    must_be_owned_by_original_user(dst_img);
    TempDir dst_temp_dir;
    mount_loop(dst_img, dst_temp_dir.path(), "ext4");

    //  - Read file list from stdin
    //  - remove all files and links in dst except listed
    //  - remove all empty directories in dst except listed
    // create temporary file to hold the list of files to copy
    char temp_file_template[] = "/tmp/genpack-helper.XXXXXX";
    auto fd = mkstemp(temp_file_template);
    if (fd < 0) {
        throw std::runtime_error("Failed to create temporary file for file list");
    }

    std::string line;
    std::set<std::filesystem::path> files_to_copy;
    while (std::getline(std::cin, line)) {
        if (line.empty() || line[0] == '#') continue; // Skip empty lines and comments
        std::string file_str_with_eol = line + "\n";
        if (debug) std::cout << "Processing file: " << line << std::endl;
        if (write(fd, file_str_with_eol.c_str(), file_str_with_eol.length()) < 0) {
            close(fd);
            throw std::runtime_error("Failed to write to temporary file for file list");
        }

        auto path = std::filesystem::path(line);
        std::filesystem::path current;
        for (const auto& part : path) {
            current /= part;
            if (part == ".." || part == ".") {
                std::cerr << "Invalid path in file list: " << path.string() << std::endl;
                continue; // Skip invalid paths
            }
            //else
            files_to_copy.insert(current);
        }
    }
    close(fd);

    std::set<std::filesystem::path> files_to_remove;
    std::set<std::filesystem::path> dirs_to_remove;
    auto dst_actual_dir = dst_temp_dir.path() / dst_dir;
    std::filesystem::create_directories(dst_actual_dir); // Ensure the destination directory exists
    for (const auto& entry : std::filesystem::recursive_directory_iterator(dst_actual_dir)) {
        if (files_to_copy.find(std::filesystem::relative(entry.path(), dst_actual_dir)) == files_to_copy.end()) {
            if (entry.is_regular_file() || entry.is_symlink()) {
                files_to_remove.insert(entry.path());
            } else if (entry.is_directory()) {
                dirs_to_remove.insert(entry.path());
            }
        }
    }

    for (const auto& file : files_to_remove) {
        if (std::filesystem::remove(file)) {
            if (debug) std::cout << "Removed file: " << file << std::endl;
        } else {
            std::cerr << "Failed to remove file: " << file << std::endl;
        }
    }

    std::vector<std::filesystem::path> dirs_to_remove_sorted(dirs_to_remove.begin(), dirs_to_remove.end());
    std::sort(dirs_to_remove_sorted.begin(), dirs_to_remove_sorted.end(), [](const std::filesystem::path& a, const std::filesystem::path& b) {
        return a.string().length() > b.string().length();
    });

    for (const auto& dir : dirs_to_remove_sorted) {
        if (std::filesystem::is_empty(dir)) {
            if (std::filesystem::remove(dir)) {
                if (debug) std::cout << "Removed empty directory: " << dir << std::endl;
            } else {
                std::cerr << "Failed to remove directory: " << dir << std::endl;
            }
        } else {
            if (debug) std::cerr << "Directory not empty, skipping removal: " << dir << std::endl;
        }
    }

    auto rst = fork_and_exec({"rsync", debug? "-av" : "-a", "--files-from=" + std::string(temp_file_template), "--relative", src_temp_dir.path().string() + "/", (dst_temp_dir.path() / dst_dir).string()});
    std::filesystem::remove(temp_file_template); // Clean up the temporary file
    return rst;
}

int main(int argc, const char* argv[])
{
    if (geteuid() != 0) {
        std::cerr << "This program's setuid bit must be set to run with root privileges." << std::endl;
        return 1;
    }

    // else
    argparse::ArgumentParser program("genpack-helper");
    program.add_argument("--debug", "-g")
        .default_value(false)
        .implicit_value(true)
        .help("Enable debug mode");

    argparse::ArgumentParser ping("ping", "Check if the program is properly installed");
    argparse::ArgumentParser stage3("stage3", "Extract a stage3 archive into a lower image");
    argparse::ArgumentParser lower("lower", "Execute a command in the lower image");
    argparse::ArgumentParser nspawn("nspawn", "Run a command in a lower image using systemd-nspawn");
    argparse::ArgumentParser copy("copy", "Copy files between two images according to filelist from stdin");

    std::map<std::string,std::tuple<argparse::ArgumentParser&,std::function<void(argparse::ArgumentParser&)>,std::function<int(const argparse::ArgumentParser&)>>> subcommands = {
        {"ping", {
            std::ref(ping),
            [](argparse::ArgumentParser& argparser) {
                // No arguments needed for ping command
            },
            [](const argparse::ArgumentParser& argparser) {
                return 0;
            }
        }},
        {"stage3", {
            std::ref(stage3), 
            [](argparse::ArgumentParser& argparser) {
                argparser.add_argument("lower_img", "The lower image file to extract the stage3 archive into.")
                    .required()
                    .help("Path to the formatted lower image file.");
                argparser.add_argument("archive_tar", "The stage3 archive to extract into the lower image.")
                    .required()
                    .help("Path to the stage3 archive file (tar.xz).");
            },
            [](const argparse::ArgumentParser& argparser) {
                auto lower_img = argparser.get<std::string>("lower_img");
                auto archive_tar = argparser.get<std::string>("archive_tar");
                ::stage3(lower_img, archive_tar);
                return 0;
            }
        }},
        {"lower", {
            std::ref(lower),
            [](argparse::ArgumentParser& argparser) {
                argparser.add_argument("lower_img", "The lower image file to execute the command in.")
                    .required()
                    .help("Path to the formatted lower image file.");
                argparser.add_argument("command", "The command to execute in the lower image.")
                    .remaining()
                    .help("Command to execute in the lower image.");
            },
            [](const argparse::ArgumentParser& argparser) {
                auto lower_img = argparser.get<std::string>("lower_img");
                auto cmdline = argparser.get<std::vector<std::string>>("command");
                return ::lower(lower_img, cmdline);
            }
        }},
        {"nspawn", {
            std::ref(nspawn),
            [](argparse::ArgumentParser& argparser) {
                argparser.add_argument("lower_img", "The lower image file to run the command in.")
                    .required()
                    .help("Path to the formatted lower image file.");
                argparser.add_argument("--setenv", "-E", "Set an environment variable for the command.")
                    .default_value<std::vector<std::string>>({})
                    .append()
                    .help("Set an environment variable for the command in the lower image.");
                argparser.add_argument("--console", "Console mode")
                    .nargs(1)
                    .help("Console mode(see man systemd-nspawn)");
                argparser.add_argument("--binpkgs-dir", "-B", "Directory for binary packages.")
                    .nargs(1)
                    .help("Directory for binary packages in the lower image.");
                argparser.add_argument("--download-dir", "-D", "Directory for downloading files in the lower image.")
                    .nargs(1)
                    .help("Directory for downloading files in the lower image.");
                argparser.add_argument("--genpack-overlay-dir", "-O", "Override the genpack overlay directory.")
                    .nargs(1)
                    .help("Override the genpack overlay directory in the lower image.");
                argparser.add_argument("--overlay-image", "-I", "Path to an overlay image and subdirectory to bind mount.")
                    .nargs(1)
                    .help("Path to an overlay image to bind mount in the lower image.");
                argparser.add_argument("--extra-image", "-X", "Path to an extra image to bind mount.")
                    .nargs(1)
                    .help("Path to an extra image to bind mount in the lower image.");
                argparser.add_argument("command", "The command to run in the lower image using systemd-nspawn.")
                    .remaining()
                    .help("Command to run in the lower image using systemd-nspawn.");
            },
            [](const argparse::ArgumentParser& argparser) {
                auto lower_img = argparser.get<std::string>("lower_img");
                auto env_vars = argparser.get<std::vector<std::string>>("--setenv");
                std::map<std::string, std::string> env_map;
                for (const auto& env : env_vars) {
                    auto pos = env.find('=');
                    if (pos != std::string::npos) {
                        env_map[env.substr(0, pos)] = env.substr(pos + 1);
                    } else {
                        std::cerr << "Invalid environment variable format: " << env << std::endl;
                        throw std::invalid_argument("Invalid environment variable format");
                    }
                }
                auto cmdline = argparser.get<std::vector<std::string>>("command");
                auto overlay_image_and_dir = argparser.present<std::string>("--overlay-image");
                std::optional<std::pair<std::filesystem::path, std::filesystem::path>> overlay_image;
                if (overlay_image_and_dir) {
                    auto pos = overlay_image_and_dir->find(':');
                    if (pos != std::string::npos) {
                        overlay_image = std::make_pair(
                            std::filesystem::path(overlay_image_and_dir->substr(0, pos)),
                            std::filesystem::path(overlay_image_and_dir->substr(pos + 1))
                        );
                    } else {
                        throw std::invalid_argument("--overlay-image must be in the format <image>:<subdir>");
                    }
                }
                return ::nspawn(lower_img, cmdline, {
                    .env_vars = env_map,
                    .console = argparser.present<std::string>("--console"),
                    .genpack_overlay_dir = argparser.present<std::string>("--genpack-overlay-dir"),
                    .binpkgs_dir = argparser.present<std::string>("--binpkgs-dir"),
                    .download_dir = argparser.present<std::string>("--download-dir"),
                    .overlay_image = overlay_image,
                    .extra_image = argparser.present<std::string>("--extra-image")
                });
            }
        }},
        {"copy", {
            std::ref(copy),
            [](argparse::ArgumentParser& argparser) {
                argparser.add_argument("src_img", "The source image file to copy files from.")
                    .required()
                    .help("Path to the source image file.");
                argparser.add_argument("dst_img", "The destination image file to copy files to.")
                    .required()
                    .help("Path to the destination image file.");
                argparser.add_argument("--dst-dir", "-d", "Destination directory inside the destination image.")
                    .default_value<std::string>("")
                    .help("Destination directory inside the destination image.");
            },
            [](const argparse::ArgumentParser& argparser) {
                auto src_img = argparser.get<std::string>("src_img");
                auto dst_img = argparser.get<std::string>("dst_img");
                auto dst_dir = argparser.get<std::string>("--dst-dir");
                return ::copy(src_img, dst_img, dst_dir);
            }

        }}
    };

    for (const auto& [name, cmd] : subcommands) {
        auto& subparser = std::get<0>(cmd);
        program.add_subparser(subparser);
        std::get<1>(cmd)(subparser);
    }

    try {
        program.parse_args(argc, argv);
    }
    catch (const std::runtime_error& e) {
        std::cerr << e.what() << std::endl;
        for (const auto& [name, cmd] : subcommands) {
            if (program.is_subcommand_used(name)) {
                std::cerr << std::get<0>(cmd) << std::endl;
                return 1;
            }
        }
    }
    catch (const std::invalid_argument& err) {
        std::cerr << err.what() << std::endl;
        return 1;
    }

    debug = program.get<bool>("--debug");

    auto subcommand_used = std::find_if(subcommands.begin(), subcommands.end(),
        [&program](const auto& pair) {
            return program.is_subcommand_used(pair.first);
        });
 
    if (subcommand_used == subcommands.end()) {
        std::cerr << "No subcommand specified. Use --help for usage information." << std::endl;
    }
    //else

    // Make mount namespace private. This is necessary to ensure that the mounts created by this program do not affect the host system.
    if (unshare(CLONE_NEWNS) == -1) {
        perror("unshare");
        return 1;
    }
    if (mount("none", "/", NULL, MS_PRIVATE | MS_REC, NULL) == -1) {
        perror("mount private");
        return 1;
    }

    const auto& name = subcommand_used->first;
    const auto& func = std::get<2>(subcommand_used->second);
    const auto& parser = std::get<0>(subcommand_used->second);

    if (debug) {
        return func(parser);
    }
    // else
    try {
        return func(parser);
    }
    catch (const std::exception& e) {
        std::cerr << "Error occurred while executing subcommand '" << name << "': " << e.what() << std::endl;
        return 1;
    }
}
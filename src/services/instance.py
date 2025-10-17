import os
import time
import shutil
import signal
import subprocess
import shlex
import stat
from pathlib import Path
import psutil
from typing import List, Optional, Dict
from ..core.config import Config
from ..core.exceptions import DependencyError
from ..core.logger import Logger
from ..models.profile import GameProfile, PlayerInstanceConfig
from ..models.instance import GameInstance
from .proton import ProtonService
from .dependency_manager import DependencyManager

class InstanceService:
    """Service responsible for managing game instances, including dependency validation, creation, launching, and monitoring."""
    def __init__(self, logger: Logger):
        """Initializes the instance service with logger and ProtonService."""
        self.logger = logger
        self.proton_service = ProtonService(logger)
        self.pids: List[int] = []
        self.managed_instances: List[GameInstance] = []
        self.cpu_count = psutil.cpu_count(logical=True)
        self.proton_path: Optional[Path] = None
        self.termination_in_progress = False

    def validate_dependencies(self) -> None:
        """Validates if all necessary commands are available on the system."""
        self.logger.info("Validating dependencies...")
        for cmd in Config.REQUIRED_COMMANDS:
            if not shutil.which(cmd):
                raise DependencyError(f"Required command '{cmd}' not found")
        self.logger.info("Dependencies validated successfully")

    def launch_instances(self, profile: GameProfile, profile_name: str) -> None:
            """Launches all game instances according to the provided profile."""
            if not profile.exe_path:
                self.logger.errgor(f"Executable path is not configured for profile '{profile_name}'. Cannot launch.")
                return

            # # Validate gamescope if needed
            # if profile.use_gamescope:
            #     if not shutil.which('gamescope'):
            #         raise DependencyError("Gamescope is enabled for this profile but 'gamescope' command not found. Please install gamescope or disable it in the profile settings.")
            #     self.logger.info("Gamescope is enabled and available for this profile.")

            # # Validate bwrap if needed
            # if not profile.disable_bwrap:
            #     if not shutil.which('bwrap'):
            #         raise DependencyError("bwrap is required but not found. Please install bubblewrap or enable 'Disable bwrap' in the profile settings (not recommended).")
            #     self.logger.info("bwrap is enabled and available for this profile.")
            # else:
            #     self.logger.warning("⚠️  bwrap is disabled for this profile. Input device isolation will NOT work!")

            if profile.is_native:
                self.proton_path = None
                steam_root = None
            else:
                self.proton_path, steam_root = self.proton_service.find_proton_path(profile.proton_version or "Experimental")

            proton_path = self.proton_path # Use local variable for the rest of the function

            # Create directories in batch
            directories = [
                Config.LOG_DIR,
                Config.PREFIX_BASE_DIR
            ]
            for directory in directories:
                directory.mkdir(parents=True, exist_ok=True)

            instances = self._create_instances(profile, profile_name, proton_path, steam_root)

            # Calculate CPU core assignments for each instance
            num_instances = len(instances)
            if num_instances == 0:
                self.logger.info("No instances to launch.")
                return

            cores_per_instance = self.cpu_count // num_instances
            remaining_cores = self.cpu_count % num_instances
            core_assignments = []
            current_core_start = 0

            for i in range(num_instances):
                num_cores_for_instance = cores_per_instance
                if remaining_cores > 0:
                    num_cores_for_instance += 1
                    remaining_cores -= 1

                # Build the core string, e.g., "0-3" or "4,5,6"
                cores_list = []
                for j in range(num_cores_for_instance):
                    cores_list.append(str(current_core_start + j))
                core_assignments.append(",".join(cores_list))
                current_core_start += num_cores_for_instance

            self.logger.info(f"Launching {num_instances} instance(s) of '{profile.game_name}'...")

            original_game_path = profile.exe_path.parent

            for i, instance in enumerate(instances):
                cpu_affinity = core_assignments[i]
                self._launch_single_instance(instance, profile, proton_path, steam_root, original_game_path, cpu_affinity)
                time.sleep(5)

            self.logger.info(f"All {num_instances} instances launched")
            self.logger.info(f"PIDs: {self.pids}")
            self.logger.info("Press CTRL+C to terminate all instances")

    def _create_instances(self, profile: GameProfile, profile_name: str, proton_path: Optional[Path], steam_root: Optional[Path]) -> List[GameInstance]:
        """Creates instance models for each player."""
        instances = []

        if not profile.is_native and proton_path and steam_root:
            dependency_manager = DependencyManager(self.logger, proton_path, steam_root)
        else:
            dependency_manager = None

        # Iterates over the complete list of player configurations with its index
        for i, player_config in enumerate(profile.player_configs):
            instance_num = i + 1

            # Checks if this instance is in the list of selected players to launch.
            # If the selection list is empty or None, all players are launched.
            if profile.selected_players and instance_num not in profile.selected_players:
                self.logger.info(f"Skipping instance {instance_num} as it's not selected by the user.")
                continue  # Skip to the next player if not selected

            # Organizes prefixes by game and by instance.
            # Uses the sanitized `profile.game_name` to ensure paths are clean.
            prefix_dir = Config.get_prefix_base_dir(profile.game_name) / f"instance_{instance_num}"
            log_file = Config.LOG_DIR / f"{profile.game_name}_instance_{instance_num}.log"
            prefix_dir.mkdir(parents=True, exist_ok=True)
            (prefix_dir / "pfx").mkdir(exist_ok=True)

            if dependency_manager:
                # Only initialize the prefix if we intend to modify it with DXVK or Winetricks.
                # Otherwise, we let Proton/Wine create it on the first actual game launch.
                if profile.apply_dxvk_vkd3d or profile.winetricks_verbs:
                    self.logger.info(f"Instance {instance_num}: DXVK/VKD3D or Winetricks verbs configured. Initializing prefix before launch.")
                    # Initialize the prefix first. This is a crucial, one-time setup.
                    dependency_manager.initialize_prefix(prefix_dir)

                    # Now, apply dependencies if configured
                    if profile.apply_dxvk_vkd3d:
                        dependency_manager.apply_dxvk_vkd3d(prefix_dir)
                    if profile.winetricks_verbs:
                        dependency_manager.apply_winetricks(prefix_dir, profile.winetricks_verbs)
                else:
                    self.logger.info(f"Instance {instance_num}: No prefix modifications required. Skipping explicit initialization.")

            instance = GameInstance(
                instance_num=instance_num,
                profile_name=profile.game_name,  # Use sanitized name
                prefix_dir=prefix_dir,
                log_file=log_file,
                player_config=player_config,
                is_native=profile.is_native
            )
            instances.append(instance)
        self.managed_instances = instances
        return instances

    def _create_game_directory_symlink_structure(self, instance: GameInstance, original_game_path: Path, original_exe_path: Path, profile: GameProfile) -> Path:
        """Creates a mirrored directory structure with symlinks for the original game folder.
        Returns the path to the main executable's symlink.
        """
        instance_game_root = instance.prefix_dir / "game_files" / original_game_path.name
        instance_game_root.mkdir(parents=True, exist_ok=True)

        self.logger.info(f"Instance {instance.instance_num}: Creating symlink structure for {original_game_path} at {instance_game_root}")

        # Determines the relative path of the original executable in relation to the game's root folder.
        try:
            relative_exe_path = original_exe_path.relative_to(original_game_path)
        except ValueError as e:
            # This can happen if original_exe_path is not inside original_game_path
            self.logger.error(f"Instance {instance.instance_num}: Executable path {original_exe_path} is not inside game path {original_game_path}. Error: {e}")
            raise

        # Expected path for the executable symlink
        symlinked_exe_path_target = instance_game_root / relative_exe_path

        self._process_game_files(instance, original_game_path, instance_game_root, profile)
        self._verify_executable_symlink(instance, symlinked_exe_path_target, original_exe_path)

        return symlinked_exe_path_target

    def _process_game_files(self, instance: GameInstance, original_game_path: Path, instance_game_root: Path, profile: GameProfile) -> None:
        """Processes all game files, creating symlinks and configuring the Goldberg Emulator."""
        self.logger.info(f"Instance {instance.instance_num}: Processing game files")

        # Create directory structure
        instance_game_root.mkdir(parents=True, exist_ok=True)

        # Create symlinks for game files
        for item in original_game_path.rglob("*"):
            relative_item_path = item.relative_to(original_game_path)
            target_path_for_item = instance_game_root / relative_item_path

            # Ensures the parent directory exists
            target_path_for_item.parent.mkdir(parents=True, exist_ok=True)

            if item.is_dir():
                target_path_for_item.mkdir(parents=True, exist_ok=True)
            else:
                # If a file already exists at the target path, log it and skip.
                # This allows users to place custom/original files that won't be overwritten.
                if target_path_for_item.exists():
                    self.logger.info(f"Instance {instance.instance_num}: Skipped symlink, file already exists: {target_path_for_item}")
                else:
                    try:
                        target_path_for_item.symlink_to(item)
                        self.logger.info(f"Instance {instance.instance_num}: Created symlink: {target_path_for_item} -> {item}")
                    except Exception as e:
                        self.logger.warning(f"Instance {instance.instance_num}: Failed to create symlink for {item}: {e}")

    def _verify_executable_symlink(self, instance: GameInstance, symlinked_exe_path_target: Path, original_exe_path: Path) -> None:
        """Verifies if the executable file exists at the target path, regardless of whether it's a symlink or a regular file."""
        if not symlinked_exe_path_target.exists():
            self.logger.error(f"Instance {instance.instance_num}: Executable file not found at the expected path: {symlinked_exe_path_target}")
            raise FileNotFoundError(f"Executable file not found for instance {instance.instance_num} at {symlinked_exe_path_target}")

        if symlinked_exe_path_target.is_symlink():
            self.logger.info(f"Instance {instance.instance_num}: Verified symlinked executable: {symlinked_exe_path_target}")
        else:
            self.logger.info(f"Instance {instance.instance_num}: Verified executable (not a symlink): {symlinked_exe_path_target}")

    def _create_launcher_script(self, instance: GameInstance, gamescope_cmd: List[str], proton_cmd: List[str]) -> Path:
        """Creates a launcher script to work around the Gamescope+LD_PRELOAD conflict."""
        script_path = instance.prefix_dir / "protoncoop_launcher.sh"
        self.logger.info(f"Instance {instance.instance_num}: Creating Gamescope launcher script at {script_path}")

        # Use shlex.join to ensure all arguments are correctly quoted
        gamescope_cmd_str = shlex.join(gamescope_cmd)
        proton_cmd_str = shlex.join(proton_cmd)

        script_content = f"""#!/bin/bash
# This script is a workaround for the conflict between Gamescope's Steam integration
# and the Steam Overlay library (gameoverlayrenderer.so) injected via LD_PRELOAD.
# It runs Gamescope in a clean environment and re-applies LD_PRELOAD only for the game process.

# Backup the original LD_PRELOAD from the bwrap environment
export LD_PRELOAD_BAK="$LD_PRELOAD"
# Unset it for the Gamescope process
unset LD_PRELOAD

# Execute Gamescope, and inside it, execute the game command with the original LD_PRELOAD restored.
# The 'exec' command replaces the script process with the gamescope process.
exec {gamescope_cmd_str} -- env LD_PRELOAD="$LD_PRELOAD_BAK" {proton_cmd_str}
"""
        # Write the script content to the file
        script_path.write_text(script_content)

        # Make the script executable (add +x permission for owner, group, and others)
        st = os.stat(script_path)
        os.chmod(script_path, st.st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)

        self.logger.info(f"Instance {instance.instance_num}: Launcher script created and made executable.")
        return script_path

    def _launch_single_instance(self, instance: GameInstance, profile: GameProfile,
                              proton_path: Optional[Path], steam_root: Optional[Path], original_game_path: Path, cpu_affinity: str) -> None:
        """Launches a single game instance with CPU affinity."""
        self.logger.info(f"Preparing instance {instance.instance_num} with CPU affinity: {cpu_affinity}...")

        if not profile.exe_path:
            self.logger.error(f"Instance {instance.instance_num}: Executable path is missing in profile, cannot launch.")
            return

        symlinked_executable_path = self._create_game_directory_symlink_structure(
            instance,
            original_game_path,
            profile.exe_path,
            profile # Passing the complete profile object
        )

        # Validate devices for this instance
        instance_idx = instance.instance_num - 1
        device_info = self._validate_input_devices(profile, instance_idx, instance.instance_num)

        env = self._prepare_environment(instance, steam_root, proton_path, profile, device_info)

        # Invertido: Lançar o sidecar PRIMEIRO para evitar que o Gamescope o capture
        if profile.sidecar_executable:
            sidecar_path = Path(profile.sidecar_executable)
            if sidecar_path.exists():
                self.logger.info(f"Instance {instance.instance_num}: Pre-launching sidecar executable: {sidecar_path}")
                # Criar um ambiente simplificado SÓ para o sidecar
                sidecar_env = self._prepare_sidecar_environment(instance, steam_root, proton_path, profile)
                sidecar_cmd = self._build_sidecar_command(profile, proton_path, instance, sidecar_path, sidecar_env)
                try:
                    # Abrir o log no modo 'w' para o sidecar para limpar logs antigos, o jogo irá anexar
                    with open(instance.log_file, 'w') as log:
                        log.write(f"--- Launching Sidecar: {sidecar_path} ---\n")
                        sidecar_process = subprocess.Popen(
                            sidecar_cmd,
                            stdout=log,
                            stderr=subprocess.STDOUT,
                            cwd=sidecar_path.parent,
                            preexec_fn=os.setpgrp
                        )
                    self.logger.info(f"Instance {instance.instance_num}: Sidecar process started with PID: {sidecar_process.pid}")
                    # Dar um pequeno compasso de espera para a janela do sidecar aparecer
                    time.sleep(2)
                except Exception as e:
                    self.logger.error(f"Failed to launch sidecar executable for instance {instance.instance_num}: {e}")
            else:
                self.logger.warning(f"Instance {instance.instance_num}: Sidecar executable '{profile.sidecar_executable}' not found. Skipping.")

        # Agora, lançar o jogo principal
        cmd = self._build_command(profile, proton_path, instance, symlinked_executable_path, cpu_affinity, env)

        self.logger.info(f"Launching main game for instance {instance.instance_num} (Log: {instance.log_file})")
        try:
            # Usar o modo 'a' (append) para o log do jogo para não sobrescrever o log do sidecar
            with open(instance.log_file, 'a') as log:
                log.write(f"\n--- Launching Main Game: {profile.exe_path.name} ---\n")
                process = subprocess.Popen(
                    cmd,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    cwd=symlinked_executable_path.parent,
                    preexec_fn=os.setpgrp
                )
            pid = process.pid
            self.pids.append(pid)
            instance.pid = pid
            self.logger.info(f"Instance {instance.instance_num} main game started with PID: {pid}")

        except Exception as e:
            self.logger.error(f"Failed to launch main game for instance {instance.instance_num}: {e}")

    def _prepare_environment(self, instance: GameInstance, steam_root: Optional[Path], proton_path: Optional[Path], profile: Optional[GameProfile] = None, device_info: dict = {}) -> dict:
        """Prepares a minimal environment for the game instance, plus device-specific vars."""
        env = os.environ.copy()
        original_path = env.get('PATH', '')

        # Clean up potentially conflicting Python variables
        env.pop('PYTHONHOME', None)
        env.pop('PYTHONPATH', None)

        if not (profile and profile.is_native):
            # --- Essential Proton/Wine variables ---
            if steam_root:
                env['STEAM_COMPAT_CLIENT_INSTALL_PATH'] = str(steam_root)
            env['STEAM_COMPAT_DATA_PATH'] = str(instance.prefix_dir)
            env['WINEPREFIX'] = str(instance.prefix_dir / 'pfx')

            # --- PATH modification ---
            if proton_path:
                proton_bin_dir = proton_path.parent
                env['PATH'] = f"{str(proton_bin_dir)}:{original_path}"

            # --- Sane defaults ---
            if 'PROTON_NO_ESYNC' not in env:
                env['PROTON_NO_ESYNC'] = "0"
            if 'PROTON_NO_FSYNC' not in env:
                env['PROTON_NO_FSYNC'] = "0"

            # --- Steam Integration ---
            if profile and profile.app_id:
                env['SteamAppId'] = profile.app_id
                env['SteamGameId'] = profile.app_id

            # --- Force Host Network ---
            # This is critical for allowing instances to communicate via localhost (127.0.0.1)
            # by disabling Proton's network namespacing.
            env['PV_NET_SHARE'] = "1"

        # --- Add environment variables defined in the profile ---
        if profile and profile.env_vars:
            for key, value in profile.env_vars.items():
                env[key] = value

        # --- Device specific environment variables ---
        # Handle joystick assignment
        assigned_joystick_path = self._get_joystick_for_instance(instance, profile)
        if assigned_joystick_path:
            env['SDL_JOYSTICK_DEVICE'] = assigned_joystick_path
            self.logger.info(f"Instance {instance.instance_num}: Setting SDL_JOYSTICK_DEVICE to '{assigned_joystick_path}'.")
        else:
            env.pop('SDL_JOYSTICK_DEVICE', None)

        # Handle audio device assignment (PULSE_SINK for PulseAudio)
        if device_info.get('audio_device_id_for_instance'):
            audio_device_id = device_info['audio_device_id_for_instance']
            env['PULSE_SINK'] = audio_device_id
            self.logger.info(f"Instance {instance.instance_num}: Setting PULSE_SINK to '{audio_device_id}'.")
        else:
            env.pop('PULSE_SINK', None)

        self.logger.info(f"Instance {instance.instance_num}: Final environment prepared.")
        return env

    def _get_joystick_for_instance(self, instance: GameInstance, profile: Optional[GameProfile]) -> Optional[str]:
        """Get joystick path for instance."""
        if not profile or not profile.player_configs or not (0 <= instance.instance_num - 1 < len(profile.player_configs)):
            return None

        idx = instance.instance_num - 1
        player_config = profile.player_configs[idx]
        device_from_profile = player_config.PHYSICAL_DEVICE_ID

        if not device_from_profile or not device_from_profile.strip():
            return None

        if Path(device_from_profile).exists():
            return device_from_profile
        return None

    def _build_command(self, profile: GameProfile, proton_path: Optional[Path], instance: GameInstance, symlinked_exe_path: Path, cpu_affinity: str, env: Dict[str, str]) -> List[str]:
        """Builds the command to run gamescope and the game (native or via Proton), using bwrap to isolate the control."""
        instance_idx = instance.instance_num - 1

        # Validate input devices
        device_info = self._validate_input_devices(profile, instance_idx, instance.instance_num)

        # Build Gamescope command
        gamescope_cmd = self._build_gamescope_command(profile, device_info['should_add_grab_flags'], instance.instance_num)

        # If gamescope is used, always use the launcher script for consistency and to avoid LD_PRELOAD conflicts.
        if gamescope_cmd:
            self.logger.info(f"Instance {instance.instance_num}: Using Gamescope. Applying launcher script for robust execution.")
            # Build the game command without the Gamescope prefix
            game_cmd_without_gamescope = self._build_base_game_command(profile, proton_path, symlinked_exe_path, [], instance.instance_num)
            # Create the script that wraps both commands
            launcher_script_path = self._create_launcher_script(instance, gamescope_cmd, game_cmd_without_gamescope)
            base_cmd = [str(launcher_script_path)]
        else:
            # Build base game command normally (without gamescope)
            base_cmd = self._build_base_game_command(profile, proton_path, symlinked_exe_path, [], instance.instance_num)

        # Build bwrap command with devices
        bwrap_cmd = self._build_bwrap_command(profile, instance_idx, device_info, instance.instance_num, env)

        # Command without taskset for CPU affinity, to mirror user's script
        final_cmd = bwrap_cmd + base_cmd
        # Use shlex.join for safer logging of the command
        final_bwrap_cmd_str = shlex.join(final_cmd)
        self.logger.info(f"Instance {instance.instance_num}: Full command: {final_bwrap_cmd_str}")

        return final_cmd

    def _validate_input_devices(self, profile: GameProfile, instance_idx: int, instance_num: int) -> dict:
        """Validates input devices and returns information about them."""
        has_dedicated_mouse = False
        mouse_path_str_for_instance = None

        # Get specific player config
        player_config = profile.player_configs[instance_idx] if profile.player_configs and 0 <= instance_idx < len(profile.player_configs) else None

        if player_config:
            mouse_path_str_for_instance = player_config.MOUSE_EVENT_PATH
            if mouse_path_str_for_instance and mouse_path_str_for_instance.strip():
                mouse_path_obj = Path(mouse_path_str_for_instance)
                if mouse_path_obj.exists() and mouse_path_obj.is_char_device():
                    has_dedicated_mouse = True
                else:
                    self.logger.warning(f"Instance {instance_num}: Mouse device '{mouse_path_str_for_instance}' specified in profile but not found or not a char device.")

        has_dedicated_keyboard = False
        keyboard_path_str_for_instance = None
        if player_config:
            keyboard_path_str_for_instance = player_config.KEYBOARD_EVENT_PATH
            if keyboard_path_str_for_instance and keyboard_path_str_for_instance.strip():
                keyboard_path_obj = Path(keyboard_path_str_for_instance)
                if keyboard_path_obj.exists() and keyboard_path_obj.is_char_device():
                    has_dedicated_keyboard = True
                else:
                    self.logger.warning(f"Instance {instance_num}: Keyboard device '{keyboard_path_str_for_instance}' specified in profile but not found or not a char device.")

        audio_device_id_for_instance = None
        if player_config:
            audio_device_id = player_config.AUDIO_DEVICE_ID
            if audio_device_id and audio_device_id.strip():
                audio_device_id_for_instance = audio_device_id
                self.logger.info(f"Instance {instance_num}: Audio device ID '{audio_device_id}' assigned.")

        return {
            'has_dedicated_mouse': has_dedicated_mouse,
            'mouse_path_str_for_instance': mouse_path_str_for_instance,
            'has_dedicated_keyboard': has_dedicated_keyboard,
            'keyboard_path_str_for_instance': keyboard_path_str_for_instance,
            'audio_device_id_for_instance': audio_device_id_for_instance,
            'should_add_grab_flags': has_dedicated_mouse and has_dedicated_keyboard
        }

    def _build_gamescope_command(self, profile: GameProfile, should_add_grab_flags: bool, instance_num: int) -> List[str]:
        """Builds the Gamescope command."""
        gamescope_path = 'gamescope'

        # Get instance dimensions directly from the profile
        effective_width, effective_height = profile.get_instance_dimensions(instance_num)

        gamescope_cli_options = [
            gamescope_path,
            '-b', # Use borderless instead of fullscreen for better compatibility
            '-W', str(effective_width),
            '-H', str(effective_height),
            '-w', str(effective_width),
            '-h', str(effective_height),
        ]

        # Always set an unfocused FPS limit to a very high value
        gamescope_cli_options.extend(['-o', '999'])
        self.logger.info(f"Instance {instance_num}: Setting unfocused FPS limit to 999.")

        # Always set a focused FPS limit to a very high value
        gamescope_cli_options.extend(['-r', '999'])
        self.logger.info(f"Instance {instance_num}: Setting focused FPS limit to 999.")

        # Add adaptive sync if not in splitscreen mode
        if not profile.is_splitscreen_mode:
            gamescope_cli_options.append('--adaptive-sync')

        if should_add_grab_flags:
            self.logger.info(f"Instance {instance_num}: Using dedicated mouse and keyboard. Adding --grab and --force-grab-cursor to Gamescope.")
            gamescope_cli_options.extend(['--grab', '--force-grab-cursor'])

        return gamescope_cli_options

    def _build_base_game_command(self, profile: GameProfile, proton_path: Optional[Path], symlinked_exe_path: Path, gamescope_cmd: List[str], instance_num: int) -> List[str]:
        """Builds the base game command."""
        # Add game arguments defined in the profile, if any
        game_specific_args = []
        if profile.game_args:
            game_specific_args = profile.game_args.split()
            self.logger.info(f"Instance {instance_num}: Adding game arguments: {game_specific_args}")

        # Only add gamescope prefix and separator if gamescope is enabled
        if gamescope_cmd:
            base_cmd_prefix = gamescope_cmd + ['--']  # Separator for the command to be executed
        else:
            base_cmd_prefix = []

        if profile.is_native:
            base_cmd = list(base_cmd_prefix)
            if symlinked_exe_path:
                base_cmd.append(str(symlinked_exe_path))
                base_cmd.extend(game_specific_args)
        else:
            base_cmd = list(base_cmd_prefix)
            if proton_path and symlinked_exe_path:
                base_cmd.extend([str(proton_path), 'run', str(symlinked_exe_path)])
                base_cmd.extend(game_specific_args)

        return base_cmd

    def _build_bwrap_command(self, profile: GameProfile, instance_idx: int, device_info: dict, instance_num: int, env: Dict[str, str]) -> List[str]:
        """Builds the bwrap command, including device bindings and environment variables."""
        bwrap_cmd = [
            'bwrap',
            '--die-with-parent',
            '--dev-bind', '/', '/',
            '--proc', '/proc',
            '--tmpfs', '/tmp',
            '--cap-add', 'all',
            '--share-net',
        ]

        # Pass environment variables into the sandbox
        for key, value in env.items():
            bwrap_cmd.extend(['--setenv', key, value])

        device_paths_to_bind = self._collect_device_paths(profile, instance_idx, device_info, instance_num)

        if device_paths_to_bind:
            bwrap_cmd.extend(['--tmpfs', '/dev/input'])
            for device_path in device_paths_to_bind:
                bwrap_cmd.extend(['--dev-bind', device_path, device_path])
                self.logger.info(f"Instance {instance_num}: bwrap will bind '{device_path}' to '{device_path}'.")
        else:
            self.logger.info(f"Instance {instance_num}: No specific input devices to bind with bwrap. Creating an empty isolated /dev/input.")
            bwrap_cmd.extend(['--tmpfs', '/dev/input'])

        return bwrap_cmd

    def _collect_device_paths(self, profile: GameProfile, instance_idx: int, device_info: dict, instance_num: int) -> List[str]:
        """Collects all necessary device paths for bwrap."""
        collected_paths = []

        # Joysticks
        # Get specific player config
        player_config = profile.player_configs[instance_idx] if profile.player_configs and 0 <= instance_idx < len(profile.player_configs) else None

        if player_config:
            joystick_path_str = player_config.PHYSICAL_DEVICE_ID
            if joystick_path_str and joystick_path_str.strip():
                joystick_path = Path(joystick_path_str)
                if joystick_path.exists() and joystick_path.is_char_device():
                    collected_paths.append(str(joystick_path))
                    self.logger.info(f"Instance {instance_num}: Queued joystick '{joystick_path}' for bwrap binding.")
                else:
                    self.logger.warning(f"Instance {instance_num}: Joystick device '{joystick_path_str}' specified in profile but not found or not a char device. Not binding.")

        # Mice - uses already validated variables
        if device_info['has_dedicated_mouse']:
            collected_paths.append(device_info['mouse_path_str_for_instance'])
            self.logger.info(f"Instance {instance_num}: Queued mouse device '{device_info['mouse_path_str_for_instance']}' for bwrap binding.")

        # Keyboards - uses already validated variables
        if device_info['has_dedicated_keyboard']:
            collected_paths.append(device_info['keyboard_path_str_for_instance'])
            self.logger.info(f"Instance {instance_num}: Queued keyboard device '{device_info['keyboard_path_str_for_instance']}' for bwrap binding.")

        return collected_paths

    def _prepare_sidecar_environment(self, instance: GameInstance, steam_root: Optional[Path], proton_path: Optional[Path], profile: GameProfile) -> dict:
        """Prepares a minimal environment specifically for the sidecar executable."""
        env = os.environ.copy()
        original_path = env.get('PATH', '')

        # Clean up potentially conflicting Python variables
        env.pop('PYTHONHOME', None)
        env.pop('PYTHONPATH', None)

        if not profile.is_native:
            # --- Essential Proton/Wine variables ---
            if steam_root:
                env['STEAM_COMPAT_CLIENT_INSTALL_PATH'] = str(steam_root)
            env['STEAM_COMPAT_DATA_PATH'] = str(instance.prefix_dir)
            env['WINEPREFIX'] = str(instance.prefix_dir / 'pfx')

            # --- PATH modification ---
            if proton_path:
                proton_bin_dir = proton_path.parent
                env['PATH'] = f"{str(proton_bin_dir)}:{original_path}"

        # NÃO adicionar variáveis de isolamento de dispositivo (SDL_JOYSTICK_DEVICE, etc.)
        # NÃO adicionar variáveis do jogo (SteamAppId, etc.)

        self.logger.info(f"Instance {instance.instance_num}: Minimal sidecar environment prepared.")
        return env

    def _build_sidecar_command(self, profile: GameProfile, proton_path: Optional[Path], instance: GameInstance, sidecar_exe_path: Path, env: Dict[str, str]) -> List[str]:
        """Builds a simplified command to run a sidecar executable without device isolation."""
        self.logger.info(f"Instance {instance.instance_num}: Building simplified command for sidecar executable '{sidecar_exe_path}'.")

        sidecar_args = []
        if profile.sidecar_args:
            try:
                # Usar shlex.split para lidar com argumentos que contenham espaços e aspas
                sidecar_args = shlex.split(profile.sidecar_args)
                self.logger.info(f"Instance {instance.instance_num}: Parsed sidecar arguments: {sidecar_args}")
            except ValueError as e:
                self.logger.error(f"Instance {instance.instance_num}: Error parsing sidecar arguments '{profile.sidecar_args}': {e}")

        if profile.is_native:
            base_cmd = [str(sidecar_exe_path)] + sidecar_args
        else:
            if not proton_path:
                self.logger.error(f"Instance {instance.instance_num}: Cannot launch Windows sidecar executable without a valid Proton path.")
                return []
            base_cmd = [str(proton_path), 'run', str(sidecar_exe_path)] + sidecar_args

        # Comando bwrap simplificado: não isola /dev/input
        bwrap_cmd = [
            'bwrap',
            '--die-with-parent',
            '--dev-bind', '/', '/',
            '--proc', '/proc',
            '--tmpfs', '/tmp',
        ]

        # Passar o ambiente simplificado para dentro do sandbox
        for key, value in env.items():
            bwrap_cmd.extend(['--setenv', key, value])

        final_cmd = bwrap_cmd + base_cmd
        final_cmd_str = shlex.join(final_cmd)
        self.logger.info(f"Instance {instance.instance_num}: Full sidecar command: {final_cmd_str}")

        return final_cmd

    def _is_any_process_running(self) -> bool:
        """Checks if any of the managed PIDs are still running."""
        if not self.pids:
            return False

        alive_pids = [pid for pid in self.pids if psutil.pid_exists(pid)]
        self.pids = alive_pids
        return len(alive_pids) > 0

    def monitor_and_wait(self, parent_pid: Optional[int] = None) -> None:
        """
        Monitors game instances and, optionally, a parent process (the GUI).
        It triggers a full cleanup if either a game instance terminates unexpectedly
        or the parent process disappears.
        """
        if parent_pid:
            self.logger.info(f"CLI process is monitoring parent GUI with PID: {parent_pid}")

        try:
            while True:
                # 1. Check if the parent GUI process is still alive
                if parent_pid and not psutil.pid_exists(parent_pid):
                    self.logger.warning(f"Parent GUI process (PID {parent_pid}) terminated. Shutting down all instances.")
                    break  # Exit the loop to trigger final termination

                # 2. Check if any game instances have terminated
                if not self._is_any_process_running():
                    self.logger.info("All game instances have terminated.")
                    if parent_pid:
                        self.logger.info(f"Notifying parent GUI (PID {parent_pid}) to close.")
                        try:
                            os.kill(parent_pid, signal.SIGUSR1)
                        except ProcessLookupError:
                            self.logger.warning(f"Parent GUI (PID {parent_pid}) not found. Cannot send close signal.")
                        except Exception as e:
                            self.logger.error(f"Failed to send SIGUSR1 to parent GUI (PID {parent_pid}): {e}")
                    break  # Exit if no instances are left

                time.sleep(2)  # Poll every 2 seconds
        finally:
            self.logger.info("Monitoring loop finished. Performing final cleanup...")
            # We no longer need to call terminate_all() here if the parent is closing us,
            # but it's good practice to keep it for robustness in case this loop exits for other reasons.
            self.terminate_all()
            self.logger.info("All instances have been terminated and cleaned up.")

    def terminate_all(self) -> None:
        """Terminates all managed game instances, process groups, and associated wineserver processes."""
        if self.termination_in_progress:
            self.logger.info("Termination already in progress, skipping.")
            return
        try:
            self.termination_in_progress = True
            self.logger.info("Starting termination of all instances...")

            # Terminate main process groups first
            if self.pids:
                self.logger.info(f"Terminating process groups for PIDs: {self.pids}")
                for pid in self.pids:
                    try:
                        # Use os.killpg to terminate the entire process group
                        os.killpg(pid, signal.SIGKILL)
                        self.logger.info(f"Sent SIGKILL to process group of PID {pid}")
                    except ProcessLookupError:
                        self.logger.info(f"Process group for PID {pid} not found, likely already terminated.")
                    except Exception as e:
                        self.logger.error(f"Failed to kill process group for PID {pid}: {e}")
            else:
                self.logger.info("No PIDs to terminate.")

            # Gracefully stop the wineserver for each non-native instance
            if self.managed_instances:
                self.logger.info(f"Stopping wineserver for {len(self.managed_instances)} instance(s).")

                wineserver_executable = None
                if self.proton_path:
                    proton_bin_dir = self.proton_path.parent
                    wineserver_executable = shutil.which('wineserver', path=str(proton_bin_dir))

                if not wineserver_executable:
                    self.logger.warning("Could not find 'wineserver' executable in Proton directory. Falling back to system 'wineserver'. This may not work as expected.")
                    wineserver_executable = 'wineserver' # Fallback

                for instance in self.managed_instances:
                    if not instance.is_native:
                        wine_prefix_path = instance.prefix_dir / 'pfx'
                        if wine_prefix_path.is_dir():
                            try:
                                self.logger.info(f"Attempting to stop wineserver for prefix: {wine_prefix_path}")
                                env = os.environ.copy()
                                env['WINEPREFIX'] = str(wine_prefix_path)

                                result = subprocess.run(
                                    [wineserver_executable, "-k"],
                                    env=env, check=False, capture_output=True, text=True, errors='replace'
                                )
                                if result.returncode == 0:
                                    self.logger.info(f"Successfully sent 'wineserver -k' for prefix: {wine_prefix_path}")
                                else:
                                    self.logger.warning(f"'wineserver -k' for prefix {wine_prefix_path} exited with code {result.returncode}. stderr: {result.stderr}")
                            except FileNotFoundError:
                                self.logger.warning(f"'{wineserver_executable}' command not found. Cannot stop wineserver for prefix: {wine_prefix_path}")
                            except Exception as e:
                                self.logger.error(f"Failed to stop wineserver for prefix {wine_prefix_path}: {e}")
            else:
                self.logger.info("No managed instances to clean up wineservers for.")

            # Clear internal state
            self.pids = []
            self.managed_instances = []
            self.logger.info("Instance termination and cleanup complete.")
        finally:
            self.termination_in_progress = False

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, Gdk, GLib
from pathlib import Path
import json
import subprocess
import os
import signal
import time
import cairo
import sys
from typing import Dict, List, Tuple, Any, Optional

from ..services.device_manager import DeviceManager
from ..services.proton import ProtonService
from ..services.game_manager import GameManager
from ..models.game import Game
from ..models.profile import Profile, GameProfile, PlayerInstanceConfig, SplitscreenConfig
from ..core.logger import Logger
from ..core.config import Config
from .styles import initialize_styles, get_style_manager, StyleManagerError

class ProfileEditorWindow(Adw.ApplicationWindow):
    """
    The main window for the Linux Coop application.

    This class builds and manages the entire graphical user interface, including
    the game/profile library view, configuration tabs, and all associated

    widgets and logic for creating, loading, saving, and launching games.
    """
    def __init__(self, app):
        super().__init__(application=app, title="Linux Coop")
        self.set_default_size(1200, 800)

        # Services and Managers
        self.logger = Logger(name="LinuxCoopGUI", log_dir=Config.LOG_DIR)
        self.game_manager = GameManager(self.logger)
        self.device_manager = DeviceManager()
        self.proton_service = ProtonService(self.logger)

        # State Tracking
        self.selected_game: Optional[Game] = None
        self.selected_profile: Optional[Profile] = None
        self.cli_process_pid: Optional[int] = None
        self.monitoring_timeout_id: Optional[int] = None

        # Main Layout
        main_vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.set_content(main_vbox)

        self.main_paned = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        main_vbox.append(self.main_paned)

        # --- Left Pane: Game and Profile Library ---
        self.sidebar_vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        self.sidebar_vbox.set_size_request(250, -1)
        self.main_paned.set_start_child(self.sidebar_vbox)

        # TreeView for games and profiles
        scrolled_window = Gtk.ScrolledWindow()
        scrolled_window.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scrolled_window.set_vexpand(True)
        self.sidebar_vbox.append(scrolled_window)

        # TreeStore model: Name, Game Object, Profile Object
        self.game_tree_store = Gtk.TreeStore(str, object, object)
        self.game_tree_view = Gtk.TreeView(model=self.game_tree_store)
        self.game_tree_view.get_selection().connect("changed", self._on_library_selection_changed)
        scrolled_window.set_child(self.game_tree_view)

        renderer = Gtk.CellRendererText()
        column = Gtk.TreeViewColumn("Library", renderer, text=0)
        self.game_tree_view.append_column(column)

        # Buttons container
        buttons_hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)
        buttons_hbox.set_margin_start(8)
        buttons_hbox.set_margin_end(8)
        buttons_hbox.set_margin_bottom(8)
        buttons_hbox.set_margin_top(8)
        self.sidebar_vbox.append(buttons_hbox)

        # Action Buttons
        self.add_game_button = Gtk.Button(label="➕ Add Game")
        self.add_game_button.set_tooltip_text("Add a new game to the library")
        self.add_game_button.connect("clicked", self._on_add_game_clicked)
        self.add_game_button.set_hexpand(True)
        buttons_hbox.append(self.add_game_button)

        self.delete_button = Gtk.Button(label="🗑️")
        self.delete_button.add_css_class("destructive-action")
        self.delete_button.set_tooltip_text("Delete selected game or profile")
        self.delete_button.set_sensitive(False)
        self.delete_button.connect("clicked", self._on_delete_clicked)
        buttons_hbox.append(self.delete_button)

        # --- Right Pane: Configuration Notebook ---
        right_pane_vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        right_pane_vbox.set_vexpand(True)
        right_pane_vbox.set_hexpand(True)
        self.main_paned.set_end_child(right_pane_vbox)

        self.notebook = Gtk.Notebook()
        self.notebook.set_vexpand(True)
        self.notebook.set_hexpand(True)
        right_pane_vbox.append(self.notebook)

        # --- Action Buttons (Bottom Bar) ---
        button_separator = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        right_pane_vbox.append(button_separator)

        button_container = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        button_container.set_halign(Gtk.Align.END)
        button_container.set_margin_start(10)
        button_container.set_margin_end(10)
        button_container.set_margin_top(10)
        button_container.set_margin_bottom(10)
        right_pane_vbox.append(button_container)

        self.save_button = Gtk.Button(label="💾 Save")
        self.save_button.connect("clicked", self.on_save_button_clicked)
        self.save_button.set_sensitive(False)
        button_container.append(self.save_button)

        self.play_button = Gtk.Button(label="▶️ Launch")
        self.play_button.connect("clicked", self.on_play_button_clicked)
        self.play_button.set_sensitive(False)
        button_container.append(self.play_button)

        # --- Initialize UI Widgets ---
        self._initialize_widgets()

        # --- Setup Configuration Tabs ---
        self.setup_game_settings_tab()
        self.setup_profile_settings_tab()
        self.setup_window_layout_tab()

        # --- Connect Signals ---
        self._connect_layout_signals()

        # --- Finalize Initialization ---
        self.statusbar = Gtk.Label()
        self.statusbar.set_halign(Gtk.Align.START)
        self.statusbar.set_margin_start(10)
        self.statusbar.set_margin_end(10)
        self.statusbar.set_margin_top(5)
        self.statusbar.set_margin_bottom(5)
        main_vbox.append(self.statusbar)

        self.show()
        self._update_action_buttons_state()
        self._populate_game_library()
        self.connect("close-request", self._on_close_request)

    def _initialize_widgets(self):
        """Initializes all configuration widgets used across the UI."""
        # --- Device Detection ---
        self.detected_input_devices = self.device_manager.get_input_devices()
        self.detected_audio_devices = self.device_manager.get_audio_devices()
        self.detected_display_outputs = self.device_manager.get_display_outputs()

        self.device_name_to_id = {"None": None}
        self.device_id_to_name = {None: "None"}

        self.device_lists = {
            "joystick": [{"name": "None", "id": None}] + self.detected_input_devices.get("joystick", []),
            "mouse": [{"name": "None", "id": None}] + self.detected_input_devices.get("mouse", []),
            "keyboard": [{"name": "None", "id": None}] + self.detected_input_devices.get("keyboard", []),
            "audio": [{"name": "None", "id": None}] + self.detected_audio_devices,
            "display": [{"name": "None", "id": None}] + self.detected_display_outputs
        }

        for device_type in ["joystick", "mouse", "keyboard"]:
            for device in self.detected_input_devices.get(device_type, []):
                self.device_name_to_id[device["name"]] = device["id"]
                self.device_id_to_name[device["id"]] = device["name"]

        for device in self.detected_audio_devices:
            self.device_name_to_id[device["name"]] = device["id"]
            self.device_id_to_name[device["id"]] = device["name"]

        for device in self.detected_display_outputs:
            self.device_name_to_id[device["name"]] = device["id"]
            self.device_id_to_name[device["id"]] = device["name"]

        # --- Game Details ---
        self.game_name_entry = Gtk.Entry(placeholder_text="Ex: Palworld")
        self.exe_path_entry = Gtk.Entry(placeholder_text="~/.steam/steamapps/common/Palworld/Palworld.exe")
        self.app_id_entry = Gtk.Entry(placeholder_text="Optional (ex: 1621530)")
        self.game_args_entry = Gtk.Entry(placeholder_text="Optional (ex: -EpicPortal)")
        self.is_native_check = Gtk.CheckButton()

        # --- Profile Details ---
        self.profile_name_entry = Gtk.Entry(placeholder_text="Ex: Coop Campaign, Modded Playthrough")
        self.profile_selector_combo = Gtk.ComboBoxText()
        self.add_profile_button = Gtk.Button(label="➕")
        self.delete_profile_button = Gtk.Button(label="🗑️")

        # --- Launch Options ---
        self.proton_version_combo = Gtk.ComboBoxText()
        proton_versions = self.proton_service.list_installed_proton_versions()
        if not proton_versions:
            self.proton_version_combo.append_text("No Proton versions found")
            self.proton_version_combo.set_sensitive(False)
        else:
            self.proton_version_combo.append_text("None (Use Steam default)")
            for version in proton_versions:
                self.proton_version_combo.append_text(version)
            self.proton_version_combo.set_active(0)

        self.apply_dxvk_vkd3d_check = Gtk.CheckButton(active=True)
        self.winetricks_verbs_entry = Gtk.Entry(placeholder_text="Optional (e.g., vcrun2019 dotnet48)")
        self.sidecar_executable_entry = Gtk.Entry(placeholder_text="Optional sidecar executable")
        self.sidecar_args_entry = Gtk.Entry(placeholder_text="Optional sidecar arguments")
        self.sidecar_width_spin = Gtk.SpinButton.new_with_range(320, 7680, 1)
        self.sidecar_height_spin = Gtk.SpinButton.new_with_range(240, 4320, 1)

        # --- Layout & Display ---
        self.num_players_spin = Gtk.SpinButton.new_with_range(1, 4, 1)
        self.instance_width_spin = Gtk.SpinButton.new_with_range(640, 7680, 1)
        self.instance_height_spin = Gtk.SpinButton.new_with_range(480, 4320, 1)
        self.mode_combo = Gtk.ComboBoxText()
        self.mode_combo.append("fullscreen", "Fullscreen")
        self.mode_combo.append("splitscreen", "Splitscreen")
        self.splitscreen_orientation_combo = Gtk.ComboBoxText()
        self.splitscreen_orientation_combo.append("horizontal", "Horizontal")
        self.splitscreen_orientation_combo.append("vertical", "Vertical")

        # --- Environment Variables ---
        self.env_vars_listbox = Gtk.ListBox()
        self.env_vars_listbox.set_selection_mode(Gtk.SelectionMode.NONE)
        self.env_var_entries = []

        # --- Player Configs ---
        self.player_config_vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        self.player_frames = []
        self.player_device_combos = []
        self.player_checkboxes = []

        # --- Preview ---
        self.drawing_area = Gtk.DrawingArea(hexpand=True, vexpand=True, width_request=200, height_request=200)

    def setup_game_settings_tab(self):
        """Sets up the 'Game Settings' tab."""
        page_vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=15, margin_start=10, margin_end=10, margin_top=10, margin_bottom=10)
        scrolled_window = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER, vscrollbar_policy=Gtk.PolicyType.AUTOMATIC)
        scrolled_window.set_child(page_vbox)
        self.notebook.append_page(scrolled_window, Gtk.Label(label="Game Settings"))

        # --- Game Details Frame ---
        game_details_frame = Gtk.Frame(label="Game Details")
        page_vbox.append(game_details_frame)
        game_details_grid = Gtk.Grid(column_spacing=10, row_spacing=10, margin_start=10, margin_end=10, margin_top=10, margin_bottom=10)
        game_details_frame.set_child(game_details_grid)

        row = 0
        game_details_grid.attach(Gtk.Label(label="Game Name:", xalign=0), 0, row, 1, 1)
        game_details_grid.attach(self.game_name_entry, 1, row, 1, 1)
        row += 1
        game_details_grid.attach(Gtk.Label(label="Executable Path:", xalign=0), 0, row, 1, 1)
        exe_path_hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)
        self.exe_path_entry.set_hexpand(True)
        exe_path_hbox.append(self.exe_path_entry)
        exe_path_button = Gtk.Button(label="Browse...")
        exe_path_button.connect("clicked", self.on_exe_path_button_clicked)
        exe_path_hbox.append(exe_path_button)
        game_details_grid.attach(exe_path_hbox, 1, row, 1, 1)
        row += 1
        game_details_grid.attach(Gtk.Label(label="App ID (Steam):", xalign=0), 0, row, 1, 1)
        game_details_grid.attach(self.app_id_entry, 1, row, 1, 1)
        row += 1
        game_details_grid.attach(Gtk.Label(label="Game Arguments:", xalign=0), 0, row, 1, 1)
        game_details_grid.attach(self.game_args_entry, 1, row, 1, 1)
        row += 1
        game_details_grid.attach(Gtk.Label(label="Is Native Game (Linux)?", xalign=0), 0, row, 1, 1)
        game_details_grid.attach(self.is_native_check, 1, row, 1, 1)

        # --- Profiles Frame ---
        profiles_frame = Gtk.Frame(label="Profiles")
        page_vbox.append(profiles_frame)
        profiles_grid = Gtk.Grid(column_spacing=10, row_spacing=10, margin_start=10, margin_end=10, margin_top=10, margin_bottom=10)
        profiles_frame.set_child(profiles_grid)

        profile_selector_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)
        self.profile_selector_combo.set_hexpand(True)
        profile_selector_box.append(self.profile_selector_combo)

        self.add_profile_button.set_tooltip_text("Add a new profile")
        self.add_profile_button.connect("clicked", self._on_add_profile_clicked)
        profile_selector_box.append(self.add_profile_button)

        self.delete_profile_button.set_tooltip_text("Delete selected profile")
        self.delete_profile_button.add_css_class("destructive-action")
        self.delete_profile_button.connect("clicked", self._on_delete_clicked)
        profile_selector_box.append(self.delete_profile_button)

        profiles_grid.attach(Gtk.Label(label="Select Profile:", xalign=0), 0, 0, 1, 1)
        profiles_grid.attach(profile_selector_box, 1, 0, 1, 1)
        self.profile_selector_combo.connect("changed", self._on_profile_selected_from_combo)

        # --- Launch Options Frame ---
        launch_options_frame = Gtk.Frame(label="Launch Options")
        page_vbox.append(launch_options_frame)
        launch_options_grid = Gtk.Grid(column_spacing=10, row_spacing=10, margin_start=10, margin_end=10, margin_top=10, margin_bottom=10)
        launch_options_frame.set_child(launch_options_grid)

        row = 0
        launch_options_grid.attach(Gtk.Label(label="Proton Version:", xalign=0), 0, row, 1, 1)
        launch_options_grid.attach(self.proton_version_combo, 1, row, 1, 1)
        row += 1
        launch_options_grid.attach(Gtk.Label(label="Apply DXVK/VKD3D:", xalign=0), 0, row, 1, 1)
        launch_options_grid.attach(self.apply_dxvk_vkd3d_check, 1, row, 1, 1)
        row += 1
        launch_options_grid.attach(Gtk.Label(label="Winetricks Verbs:", xalign=0), 0, row, 1, 1)
        launch_options_grid.attach(self.winetricks_verbs_entry, 1, row, 1, 1)
        row += 1
        launch_options_grid.attach(Gtk.Label(label="Sidecar Executable:", xalign=0), 0, row, 1, 1)
        sidecar_path_hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)
        self.sidecar_executable_entry.set_hexpand(True)
        sidecar_path_hbox.append(self.sidecar_executable_entry)
        sidecar_path_button = Gtk.Button(label="Browse...")
        sidecar_path_button.connect("clicked", self.on_sidecar_path_button_clicked)
        sidecar_path_hbox.append(sidecar_path_button)
        launch_options_grid.attach(sidecar_path_hbox, 1, row, 1, 1)
        row += 1
        launch_options_grid.attach(Gtk.Label(label="Sidecar Arguments:", xalign=0), 0, row, 1, 1)
        launch_options_grid.attach(self.sidecar_args_entry, 1, row, 1, 1)
        row += 1
        sidecar_dims_hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)
        sidecar_dims_hbox.append(Gtk.Label(label="Sidecar Width:", xalign=0))
        sidecar_dims_hbox.append(self.sidecar_width_spin)
        sidecar_dims_hbox.append(Gtk.Label(label="Height:", xalign=0))
        sidecar_dims_hbox.append(self.sidecar_height_spin)
        launch_options_grid.attach(sidecar_dims_hbox, 1, row, 1, 1)


        # --- Environment Variables Frame ---
        env_vars_frame = Gtk.Frame(label="Custom Environment Variables")
        page_vbox.append(env_vars_frame)
        env_vars_vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5, margin_start=10, margin_end=10, margin_top=10, margin_bottom=10)
        env_vars_frame.set_child(env_vars_vbox)

        env_vars_vbox.append(self.env_vars_listbox)
        self._add_env_var_row("WINEDLLOVERRIDES", "")
        self._add_env_var_row("MANGOHUD", "1")
        add_env_var_button = Gtk.Button(label="Add Variable")
        add_env_var_button.connect("clicked", self._on_add_env_var_clicked)
        env_vars_vbox.append(add_env_var_button)

    def setup_profile_settings_tab(self):
        """Sets up the 'Profile Settings' tab."""
        page_vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=15, margin_start=10, margin_end=10, margin_top=10, margin_bottom=10)
        scrolled_window = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER, vscrollbar_policy=Gtk.PolicyType.AUTOMATIC)
        scrolled_window.set_child(page_vbox)
        self.notebook.append_page(scrolled_window, Gtk.Label(label="Profile Settings"))

        # --- Profile Details ---
        profile_details_frame = Gtk.Frame(label="Profile Details")
        page_vbox.append(profile_details_frame)
        profile_details_grid = Gtk.Grid(column_spacing=10, row_spacing=10, margin_start=10, margin_end=10, margin_top=10, margin_bottom=10)
        profile_details_frame.set_child(profile_details_grid)
        profile_details_grid.attach(Gtk.Label(label="Profile Name:", xalign=0), 0, 0, 1, 1)
        profile_details_grid.attach(self.profile_name_entry, 1, 0, 1, 1)

        # --- Layout and Display ---
        # --- Player Configurations ---
        players_frame = Gtk.Frame(label="Player Configurations")
        page_vbox.append(players_frame)
        players_frame.set_child(self.player_config_vbox)

    def setup_window_layout_tab(self):
        """Sets up the 'Window Layout' preview tab."""
        page = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10, margin_start=10, margin_end=10, margin_top=10, margin_bottom=10)
        self.notebook.append_page(page, Gtk.Label(label="Window Layout"))

        # --- Settings Panel (Left) ---
        settings_panel = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        settings_panel.set_size_request(300, -1)
        page.append(settings_panel)

        settings_grid = Gtk.Grid(column_spacing=10, row_spacing=10)
        settings_panel.append(settings_grid)

        row = 0
        settings_grid.attach(Gtk.Label(label="Number of Players:", xalign=0), 0, row, 1, 1)
        settings_grid.attach(self.num_players_spin, 1, row, 1, 1)
        row += 1
        settings_grid.attach(Gtk.Label(label="Instance Width:", xalign=0), 0, row, 1, 1)
        settings_grid.attach(self.instance_width_spin, 1, row, 1, 1)
        row += 1
        settings_grid.attach(Gtk.Label(label="Instance Height:", xalign=0), 0, row, 1, 1)
        settings_grid.attach(self.instance_height_spin, 1, row, 1, 1)
        row += 1
        settings_grid.attach(Gtk.Label(label="Mode:", xalign=0), 0, row, 1, 1)
        settings_grid.attach(self.mode_combo, 1, row, 1, 1)
        row += 1
        self.splitscreen_orientation_label = Gtk.Label(label="Orientation:", xalign=0)
        settings_grid.attach(self.splitscreen_orientation_label, 0, row, 1, 1)
        settings_grid.attach(self.splitscreen_orientation_combo, 1, row, 1, 1)

        # --- Preview Panel (Right) ---
        preview_panel = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5, hexpand=True, vexpand=True)
        page.append(preview_panel)

        preview_label = Gtk.Label(label="Preview", halign=Gtk.Align.START, margin_bottom=5)
        preview_label.add_css_class("heading")
        preview_panel.append(preview_label)

        self.drawing_area.set_draw_func(self.on_draw_window_layout)
        preview_panel.append(self.drawing_area)

    def _connect_layout_signals(self):
        """Connects signals for widgets that affect the layout preview."""
        self.instance_width_spin.connect("value-changed", self.on_layout_setting_changed)
        self.instance_height_spin.connect("value-changed", self.on_layout_setting_changed)
        self.num_players_spin.connect("value-changed", self.on_layout_setting_changed)
        self.mode_combo.connect("changed", self.on_layout_setting_changed)
        self.splitscreen_orientation_combo.connect("changed", self.on_layout_setting_changed)

        # Specific handlers
        self.mode_combo.connect("changed", self.on_mode_changed)
        self.num_players_spin.connect("value-changed", self.on_num_players_changed)

    def _update_action_buttons_state(self):
        """Updates the sensitivity of all action buttons based on the current selection."""
        game_selected = self.selected_game is not None
        profile_selected = self.selected_profile is not None

        # Sidebar buttons
        self.delete_button.set_sensitive(game_selected) # The main delete button now only deletes games

        # Game Settings tab buttons
        self.add_profile_button.set_sensitive(game_selected)
        self.delete_profile_button.set_sensitive(profile_selected)

        # Bottom-bar buttons
        self.save_button.set_sensitive(game_selected) # Can always save game settings
        self.play_button.set_sensitive(profile_selected) # Can only launch with a profile

        # Play/Stop button state
        if self.cli_process_pid:
            self.play_button.set_label("⏹️ Stop")
            self.play_button.get_style_context().add_class("destructive-action")
            self.play_button.get_style_context().remove_class("suggested-action")
        else:
            self.play_button.set_label("▶️ Launch")
            self.play_button.get_style_context().add_class("suggested-action")
            self.play_button.get_style_context().remove_class("destructive-action")

    def on_exe_path_button_clicked(self, button):
        """Handles the 'Browse...' button click to select a game executable."""
        dialog = Gtk.FileChooserDialog(
            title="Select Game Executable",
            action=Gtk.FileChooserAction.OPEN
        )

        # Set parent after creation for GTK4 compatibility
        dialog.set_transient_for(self)
        dialog.set_modal(True)

        # Add buttons manually for GTK4 compatibility
        dialog.add_button("_Cancel", Gtk.ResponseType.CANCEL)
        dialog.add_button("_Open", Gtk.ResponseType.OK)

        dialog.connect("response", self._on_exe_path_dialog_response)
        dialog.present()

    def _on_exe_path_dialog_response(self, dialog, response):
        """Handles the response from the file chooser dialog for the executable path."""
        if response == Gtk.ResponseType.OK:
            file = dialog.get_file()
            if file:
                self.exe_path_entry.set_text(file.get_path())
        dialog.destroy()
        self.statusbar.set_label("Executable path selected.") # Changed from push

    def on_sidecar_path_button_clicked(self, button):
        """Handles the 'Browse...' button click to select a sidecar executable."""
        dialog = Gtk.FileChooserDialog(
            title="Select Sidecar Executable",
            action=Gtk.FileChooserAction.OPEN
        )

        dialog.set_transient_for(self)
        dialog.set_modal(True)
        dialog.add_button("_Cancel", Gtk.ResponseType.CANCEL)
        dialog.add_button("_Open", Gtk.ResponseType.OK)

        dialog.connect("response", self._on_sidecar_path_dialog_response)
        dialog.present()

    def _on_sidecar_path_dialog_response(self, dialog, response):
        """Handles the response from the file chooser dialog for the sidecar executable path."""
        if response == Gtk.ResponseType.OK:
            file = dialog.get_file()
            if file:
                self.sidecar_executable_entry.set_text(file.get_path())
        dialog.destroy()
        self.statusbar.set_label("Sidecar executable path selected.")

    def _populate_game_library(self):
        """Populates the TreeView with games from the GameManager."""
        self.game_tree_store.clear()
        games = self.game_manager.get_games()
        for game in games:
            self.game_tree_store.append(None, [game.game_name, game, None])
        self.game_tree_view.expand_all()

    def _populate_profile_selector(self, game: Optional[Game]):
        """Populates the profile selector ComboBox with profiles for the given game."""
        self.profile_selector_combo.remove_all()
        if game:
            profiles = self.game_manager.get_profiles(game)
            for profile in profiles:
                self.profile_selector_combo.append(profile.profile_name, profile.profile_name)
        self.profile_selector_combo.set_active(-1)

    def _on_library_selection_changed(self, selection):
        """Handles selection changes in the game library TreeView."""
        model, tree_iter = selection.get_selected()
        if tree_iter:
            self.selected_game = model.get_value(tree_iter, 1)
            self._clear_all_fields()
            self._load_game_data(self.selected_game)
            self._populate_profile_selector(self.selected_game)
            self._set_fields_sensitivity(is_game_selected=True, is_profile_selected=False)
        else:
            self.selected_game = None
            self.selected_profile = None
            self._clear_all_fields()
            self._populate_profile_selector(None)
            self._set_fields_sensitivity(is_game_selected=False, is_profile_selected=False)

        self._update_action_buttons_state()

    def _on_profile_selected_from_combo(self, combo):
        """Handles selection changes in the profile ComboBox."""
        profile_name = combo.get_active_text()
        if profile_name and self.selected_game:
            profiles = self.game_manager.get_profiles(self.selected_game)
            self.selected_profile = next((p for p in profiles if p.profile_name == profile_name), None)
            if self.selected_profile:
                self._load_profile_data(self.selected_game, self.selected_profile)
                self._set_fields_sensitivity(is_game_selected=True, is_profile_selected=True)
        else:
            self.selected_profile = None
            # Re-load game data to clear profile-specific fields
            if self.selected_game:
                self._load_game_data(self.selected_game)
            self._set_fields_sensitivity(is_game_selected=(self.selected_game is not None), is_profile_selected=False)

        self._update_action_buttons_state()

    def _select_item_in_library(self, game_name: str, profile_name: Optional[str] = None):
        """Programmatically selects a game and then defers profile selection."""
        model = self.game_tree_store
        root_iter = model.get_iter_first()
        while root_iter:
            stored_game = model.get_value(root_iter, 1)
            if stored_game and stored_game.game_name == game_name:
                # This selection will trigger _on_library_selection_changed,
                # which will correctly populate the profile ComboBox.
                self.game_tree_view.get_selection().select_iter(root_iter)
                self.game_tree_view.scroll_to_cell(model.get_path(root_iter))

                # Defer the profile selection to the next idle cycle.
                # This gives the TreeView selection signal handler time to run
                # and populate the ComboBox before we try to select an item in it.
                if profile_name:
                    GLib.idle_add(self.profile_selector_combo.set_active_id, profile_name)

                return
            root_iter = model.iter_next(root_iter)

    def _on_add_env_var_clicked(self, button):
        """Handles the 'Add Variable' button click for environment variables."""
        self._add_env_var_row()
        self.statusbar.set_label("Environment variable added.") # Changed from push

    def _add_env_var_row(self, key="", value=""):
        """Adds a new row to the environment variables listbox."""
        hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)

        key_entry = Gtk.Entry()
        key_entry.set_placeholder_text("Variable Name")
        key_entry.set_hexpand(True)
        key_entry.set_text(key)
        hbox.append(key_entry) # Changed from pack_start

        value_entry = Gtk.Entry()
        value_entry.set_placeholder_text("Value")
        value_entry.set_hexpand(True)
        value_entry.set_text(value)
        hbox.append(value_entry) # Changed from pack_start

        remove_button = Gtk.Button(label="-")
        # remove_button.set_relief(Gtk.ReliefStyle.NONE) # set_relief is Gtk3 only
        remove_button.set_tooltip_text("Remove this environment variable")

        list_box_row = Gtk.ListBoxRow()
        list_box_row.set_child(hbox) # Changed from add

        remove_button.connect("clicked", lambda btn, row=list_box_row, k_entry=key_entry, v_entry=value_entry: self._remove_env_var_row(btn, row, k_entry, v_entry))
        hbox.append(remove_button) # Changed from pack_end

        self.env_vars_listbox.append(list_box_row) # Changed from add
        list_box_row.show() # Explicitly show the row for Gtk4 ListBox
        self.env_var_entries.append((key_entry, value_entry, list_box_row))

    def _remove_env_var_row(self, button, row, key_entry, value_entry):
        """Removes a row from the environment variables listbox."""
        self.env_vars_listbox.remove(row)
        self.env_var_entries.remove((key_entry, value_entry, row))
        self.statusbar.set_label("Environment variable removed.") # Changed from push

    def _clear_environment_variables_ui(self):
        """Clears the environment variables from the UI."""
        while self.env_vars_listbox.get_first_child():
            self.env_vars_listbox.remove(self.env_vars_listbox.get_first_child())
        self.env_var_entries.clear()
        self.env_vars_listbox.queue_draw()

    def _add_default_environment_variables(self):
        """Adds the default environment variables to the UI."""
        self._add_env_var_row("WINEDLLOVERRIDES", "")
        self._add_env_var_row("MANGOHUD", "1")

    def _get_env_vars_from_ui(self) -> Dict[str, str]:
        """Gets the environment variables from the UI."""
        env_vars = {}
        for row_data in self.env_var_entries:
            key = row_data[0].get_text().strip()
            value = row_data[1].get_text().strip()
            if key:
                env_vars[key] = value
        return env_vars

    def _get_player_configs_from_ui(self) -> List[Dict[str, Any]]:
        """Gets the player configurations from the UI."""
        player_configs_data = []
        for i, (is_enabled_checkbox, player_widgets) in enumerate(zip(self.player_checkboxes, self.player_device_combos)):
            config = {}
            # Iterate through the entry widgets and collect data
            # No need to iterate self.player_config_entries, it's not structured for this anymore
            # Instead, use the player_widgets directly
            for key, widget in player_widgets.items(): # key will now be UPPER_SNAKE_CASE
                if isinstance(widget, Gtk.Entry):
                    value = widget.get_text().strip()
                    config[key] = value if value != "" else None # Convert empty string to None if applicable
                elif isinstance(widget, Gtk.DropDown): # Gtk.DropDown for device selection
                    selected_index = widget.get_selected()
                    device_type = getattr(widget, 'device_type', None)

                    if device_type and device_type in self.device_lists:
                        device_list = self.device_lists[device_type]
                        if 0 <= selected_index < len(device_list):
                            device = device_list[selected_index]
                            device_id = device["id"]
                            device_name = device["name"]
                        else:
                            device_id = None
                            device_name = "None"
                    else:
                        # Fallback to old method
                        selected_item = widget.get_selected_item()
                        selected_name = selected_item.get_string() if selected_item else "None"
                        device_id = self.device_name_to_id.get(selected_name, None)
                        device_name = selected_name

                    self.logger.info(f"DEBUG: Player config: Selected name for {key}: '{device_name}' (index: {selected_index})")
                    self.logger.info(f"DEBUG: Player config: Resolved ID for {key} ('{device_name}'): '{device_id}'")
                    config[key] = device_id
                else:
                    config[key] = "" # Default empty string for other widget types if any
            player_configs_data.append(config)
        self.logger.info(f"DEBUG: Collected player configurations data: {player_configs_data}")
        return player_configs_data

    def setup_player_configs(self):
        """Sets up the initial player configuration UI."""
        self.player_frames = []
        self.player_device_combos = []

        self._create_player_config_uis(self.num_players_spin.get_value_as_int())

    def _create_player_config_uis(self, num_players: int):
        """Creates or recreates the UI for the specified number of players."""
        for frame in self.player_frames:
            frame.unparent() # Changed from destroy()
        self.player_frames.clear()
        self.player_device_combos.clear()
        self.player_checkboxes.clear()

        # In Gtk4, Gtk.Box.get_children() is removed. Remove children one by one.
        while self.player_config_vbox.get_first_child():
            self.player_config_vbox.remove(self.player_config_vbox.get_first_child())

        for i in range(num_players):
            player_frame = Gtk.Frame(label=f"Player {i+1} Configuration")
            player_frame.set_margin_top(10) # Changed from set_shadow_type
            player_frame.set_margin_bottom(10) # Added margin
            player_frame.set_margin_start(10) # Added margin
            player_frame.set_margin_end(10) # Added margin
            self.player_config_vbox.append(player_frame) # Changed from pack_start
            player_frame.show() # Explicitly show the frame
            self.player_frames.append(player_frame)

            player_grid = Gtk.Grid()
            player_grid.set_column_spacing(10)
            player_grid.set_row_spacing(10)
            player_grid.set_margin_start(10) # Changed from set_border_width
            player_grid.set_margin_end(10)   # Changed from set_border_width
            player_grid.set_margin_top(10)   # Changed from set_border_width
            player_grid.set_margin_bottom(10) # Changed from set_border_width
            player_frame.set_child(player_grid) # Changed from add
            player_grid.show() # Explicitly show the grid

            # Create DropDowns with ellipsize to prevent expansion
            physical_device_dropdown = Gtk.DropDown.new_from_strings(self._create_device_list_store(self.detected_input_devices["joystick"]))
            physical_device_dropdown.set_size_request(200, -1)

            mouse_device_dropdown = Gtk.DropDown.new_from_strings(self._create_device_list_store(self.detected_input_devices["mouse"]))
            mouse_device_dropdown.set_size_request(200, -1)

            keyboard_device_dropdown = Gtk.DropDown.new_from_strings(self._create_device_list_store(self.detected_input_devices["keyboard"]))
            keyboard_device_dropdown.set_size_request(200, -1)

            audio_device_dropdown = Gtk.DropDown.new_from_strings(self._create_device_list_store(self.detected_audio_devices))
            audio_device_dropdown.set_size_request(200, -1)

            monitor_dropdown = Gtk.DropDown.new_from_strings(self._create_device_list_store(self.detected_display_outputs))
            monitor_dropdown.set_size_request(200, -1)

            # Store device type mapping for each dropdown
            physical_device_dropdown.device_type = "joystick"
            mouse_device_dropdown.device_type = "mouse"
            keyboard_device_dropdown.device_type = "keyboard"
            audio_device_dropdown.device_type = "audio"
            monitor_dropdown.device_type = "display"

            player_combos = {
                "ACCOUNT_NAME": Gtk.Entry(),
                "LANGUAGE": Gtk.Entry(),
                "LISTEN_PORT": Gtk.Entry(),
                "USER_STEAM_ID": Gtk.Entry(),
                "PHYSICAL_DEVICE_ID": physical_device_dropdown,
                "MOUSE_EVENT_PATH": mouse_device_dropdown,
                "KEYBOARD_EVENT_PATH": keyboard_device_dropdown,
                "AUDIO_DEVICE_ID": audio_device_dropdown,
                "MONITOR_ID": monitor_dropdown,
            }
            self.player_device_combos.append(player_combos)

            p_row = 0

            check_button = Gtk.CheckButton(label=f"Enable Player {i + 1}")
            check_button.set_active(True)
            self.player_checkboxes.append(check_button)
            player_grid.attach(check_button, 0, p_row, 2, 1)
            check_button.show()
            p_row += 1

            # player_grid.attach(Gtk.Label(label="Account Name:", xalign=0), 0, p_row, 1, 1)
            # player_combos["ACCOUNT_NAME"].set_placeholder_text(f"Player {i+1}")
            # player_grid.attach(player_combos["ACCOUNT_NAME"], 1, p_row, 1, 1)
            # player_combos["ACCOUNT_NAME"].show()
            # p_row += 1

            # player_grid.attach(Gtk.Label(label="Language:", xalign=0), 0, p_row, 1, 1)
            # player_combos["LANGUAGE"].set_placeholder_text("Ex: brazilian, english")
            # player_grid.attach(player_combos["LANGUAGE"], 1, p_row, 1, 1)
            # player_combos["LANGUAGE"].show()
            # p_row += 1

            # player_grid.attach(Gtk.Label(label="Listen Port (Goldberg):", xalign=0), 0, p_row, 1, 1)
            # player_combos["LISTEN_PORT"].set_placeholder_text("Optional")
            # player_grid.attach(player_combos["LISTEN_PORT"], 1, p_row, 1, 1)
            # player_combos["LISTEN_PORT"].show()
            # p_row += 1

            # player_grid.attach(Gtk.Label(label="User Steam ID:", xalign=0), 0, p_row, 1, 1)
            # player_combos["USER_STEAM_ID"].set_placeholder_text("Optional (ex: 7656119...)")
            # player_grid.attach(player_combos["USER_STEAM_ID"], 1, p_row, 1, 1)
            # player_combos["USER_STEAM_ID"].show()
            # p_row += 1

            player_grid.attach(Gtk.Label(label="Joystick Device:", xalign=0), 0, p_row, 1, 1)
            physical_device_id_combo = player_combos["PHYSICAL_DEVICE_ID"]
            # Removed Gtk.CellRendererText and pack_start/add_attribute for Gtk4 Gtk.DropDown
            physical_device_id_combo.set_selected(0) # Select "None" by default
            player_grid.attach(physical_device_id_combo, 1, p_row, 1, 1)
            physical_device_id_combo.show()
            p_row += 1

            player_grid.attach(Gtk.Label(label="Mouse Device:", xalign=0), 0, p_row, 1, 1)
            mouse_event_path_combo = player_combos["MOUSE_EVENT_PATH"]
            # Removed Gtk.CellRendererText and pack_start/add_attribute for Gtk4 Gtk.DropDown
            mouse_event_path_combo.set_selected(0) # Select "None" by default
            player_grid.attach(mouse_event_path_combo, 1, p_row, 1, 1)
            mouse_event_path_combo.show()
            p_row += 1

            player_grid.attach(Gtk.Label(label="Keyboard Device:", xalign=0), 0, p_row, 1, 1)
            keyboard_event_path_combo = player_combos["KEYBOARD_EVENT_PATH"]
            # Removed Gtk.CellRendererText and pack_start/add_attribute for Gtk4 Gtk.DropDown
            keyboard_event_path_combo.set_selected(0) # Select "None" by default
            player_grid.attach(keyboard_event_path_combo, 1, p_row, 1, 1)
            keyboard_event_path_combo.show()
            p_row += 1

            player_grid.attach(Gtk.Label(label="Audio Device:", xalign=0), 0, p_row, 1, 1)
            audio_device_id_combo = player_combos["AUDIO_DEVICE_ID"]
            # Removed Gtk.CellRendererText and pack_start/add_attribute for Gtk4 Gtk.DropDown
            audio_device_id_combo.set_selected(0) # Select "None" by default
            player_grid.attach(audio_device_id_combo, 1, p_row, 1, 1)
            audio_device_id_combo.show()
            p_row += 1

            # # Monitor Selection
            # player_grid.attach(Gtk.Label(label="Monitor:", xalign=0), 0, p_row, 1, 1)
            # monitor_combo = player_combos["MONITOR_ID"]
            # # Removed Gtk.CellRendererText and pack_start/add_attribute for Gtk4 Gtk.DropDown
            # monitor_combo.set_selected(0) # Select "None" by default
            # player_grid.attach(monitor_combo, 1, p_row, 1, 1)
            # monitor_combo.show()
            # p_row += 1

        # self.player_config_vbox.show_all() # Not needed for Gtk4
        self.logger.info(f"DEBUG: Created {len(self.player_frames)} player config UIs.")
        self.player_config_vbox.queue_draw() # Force redraw after creating UIs

    def on_num_players_changed(self, spin_button):
        """Handles the 'Number of Players' spin button value change."""
        num_players = spin_button.get_value_as_int()
        self._create_player_config_uis(num_players)
        self.statusbar.set_label(f"Number of players changed to {num_players}.")

    def on_mode_changed(self, combo):
        """Shows or hides the splitscreen orientation dropdown based on the selected mode."""
        mode = combo.get_active_text()
        is_splitscreen = (mode == "Splitscreen")
        self.splitscreen_orientation_label.set_visible(is_splitscreen)
        self.splitscreen_orientation_combo.set_visible(is_splitscreen)
        if is_splitscreen:
            self.statusbar.set_label("Splitscreen mode activated.")
        else:
            self.statusbar.set_label("Splitscreen mode deactivated.")

    def on_save_button_clicked(self, button):
        """Handles the 'Save' button click, saving data and restoring selection."""
        game_to_reselect = None
        profile_to_reselect = None

        if self.selected_profile and self.selected_game:
            game_to_reselect = self.selected_game.game_name
            profile_to_reselect = self.profile_name_entry.get_text() # Get name from entry in case it was changed
            self.statusbar.set_label("Saving profile...")
            try:
                updated_profile = self._get_profile_from_ui()
                self.game_manager.save_profile(self.selected_game, updated_profile)
                self.statusbar.set_label(f"Profile '{updated_profile.profile_name}' saved.")
            except Exception as e:
                self.logger.error(f"Failed to save profile: {e}")
                self.statusbar.set_label(f"Error saving profile: {e}")

        elif self.selected_game:
            game_to_reselect = self.game_name_entry.get_text()
            self.statusbar.set_label("Saving game...")
            try:
                updated_game = self._get_game_from_ui()
                self.game_manager.save_game(updated_game)
                self.statusbar.set_label(f"Game '{updated_game.game_name}' saved.")
            except Exception as e:
                self.logger.error(f"Failed to save game: {e}")
                self.statusbar.set_label(f"Error saving game: {e}")

        self._populate_game_library()
        if game_to_reselect:
            self._select_item_in_library(game_to_reselect, profile_to_reselect)

    def _get_game_from_ui(self) -> Game:
        """Creates a Game object from the data in the UI fields."""
        proton_version = self.proton_version_combo.get_active_text()
        if proton_version == "None (Use Steam default)" or not proton_version:
            proton_version = None

        winetricks_text = self.winetricks_verbs_entry.get_text().strip()
        winetricks_verbs = winetricks_text.split() if winetricks_text else None

        return Game(
            game_name=self.game_name_entry.get_text(),
            exe_path=self.exe_path_entry.get_text(),
            app_id=self.app_id_entry.get_text() or None,
            game_args=self.game_args_entry.get_text() or None,
            is_native=self.is_native_check.get_active(),
            proton_version=proton_version,
            apply_dxvk_vkd3d=self.apply_dxvk_vkd3d_check.get_active(),
            winetricks_verbs=winetricks_verbs,
            env_vars=self._get_env_vars_from_ui()
        )

    def _get_profile_from_ui(self) -> Profile:
        """Creates a Profile object from the data in the UI fields."""
        proton_version = self.proton_version_combo.get_active_text()
        if proton_version == "None (Use Steam default)" or not proton_version:
            proton_version = None

        splitscreen_config = None
        if self.mode_combo.get_active_text() == "splitscreen":
            splitscreen_config = SplitscreenConfig(
                orientation=self.splitscreen_orientation_combo.get_active_text()
            )

        winetricks_text = self.winetricks_verbs_entry.get_text().strip()
        winetricks_verbs = winetricks_text.split() if winetricks_text else None

        selected_players = [i + 1 for i, cb in enumerate(self.player_checkboxes) if cb.get_active()]

        return Profile(
            profile_name=self.profile_name_entry.get_text(),
            proton_version=proton_version,
            num_players=self.num_players_spin.get_value_as_int(),
            instance_width=self.instance_width_spin.get_value_as_int(),
            instance_height=self.instance_height_spin.get_value_as_int(),
            mode=self.mode_combo.get_active_text(),
            splitscreen=splitscreen_config,
            env_vars=self._get_env_vars_from_ui(),
            player_configs=self._get_player_configs_from_ui(),
            selected_players=selected_players,
            apply_dxvk_vkd3d=self.apply_dxvk_vkd3d_check.get_active(),
            winetricks_verbs=winetricks_verbs,
            sidecar_executable=self.sidecar_executable_entry.get_text() or None,
            sidecar_args=self.sidecar_args_entry.get_text() or None,
            sidecar_width=self.sidecar_width_spin.get_value_as_int() or 800,
            sidecar_height=self.sidecar_height_spin.get_value_as_int() or 600
        )

    def on_play_button_clicked(self, widget):
        """Handles clicks on the 'Launch Game' / 'Stop Game' button."""
        if self.cli_process_pid:
            self._stop_game()
            return

        if not self.selected_game or not self.selected_profile:
            self.statusbar.set_label("Error: No profile selected to launch.")
            return

        # Store references before the auto-save potentially clears the selection
        game_to_launch = self.selected_game
        profile_to_launch = self.selected_profile

        self.statusbar.set_label("Starting game...")
        self.on_save_button_clicked(widget) # Auto-save before launch

        # The profile name for the CLI is the sanitized game name
        cli_game_name = game_to_launch.game_name.replace(" ", "_").lower()

        # Check if running as PyInstaller bundle
        if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
            # PyInstaller bundle - use the current executable
            script_path = Path(sys.executable)
            python_exec = str(script_path)
        else:
            # Normal Python execution
            script_path = Path(__file__).parent.parent.parent / "protoncoop.py"
            python_exec = sys.executable # Use o interpretador Python atual do ambiente virtual

        if not python_exec:
            self.statusbar.set_label("Error: Python interpreter not found.") # Changed from push
            dialog = Adw.MessageDialog(
                heading="Launch Error",
                body="No Python interpreter found on the system.",
                modal=True,
            )
            dialog.add_response("ok", "Ok")
            dialog.set_response_enabled("ok", True)
            dialog.set_default_response("ok")
            dialog.set_transient_for(self)
            dialog.connect("response", lambda d, r: d.close())
            dialog.present()
            return

        if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
            # PyInstaller bundle - call the executable directly
            command = [python_exec, cli_game_name, "--profile", profile_to_launch.profile_name]
        else:
            # Normal Python execution
            command = [python_exec, str(script_path), cli_game_name, "--profile", profile_to_launch.profile_name]

        # # Append --no-bwrap if requested via GUI
        # if getattr(self, 'disable_bwrap_check', None) and self.disable_bwrap_check.get_active():
        #     command.append("--no-bwrap")
        #     self.logger.info("Disabling bwrap as requested by user")

        # Pass the GUI's PID to the CLI process for monitoring
        gui_pid = os.getpid()
        command.extend(["--parent-pid", str(gui_pid)])
        self.logger.info(f"Passing parent PID {gui_pid} to CLI process.")

        self.logger.info(f"Executing command: {' '.join(command)}")

        self.play_button.set_sensitive(False)
        self.play_button.set_label("Iniciando...")

        try:
            # Launch the CLI script as a separate process group
            process = subprocess.Popen(command, preexec_fn=os.setsid)
            self.cli_process_pid = process.pid
            self.statusbar.set_label(f"Game '{cli_game_name}' launched successfully with PID: {self.cli_process_pid}.") # Changed from push
            self._update_action_buttons_state() # Update button to "Stop Gaming"
            # Start monitoring the process
            self.monitoring_timeout_id = GLib.timeout_add(1000, self._check_cli_process) # Corrigido para GLib.timeout_add
        except Exception as e:
            self.logger.error(f"Failed to launch game: {e}")
            self.statusbar.set_label(f"Error launching game: {e}") # Changed from push
            dialog = Adw.MessageDialog(
                heading="Launch Error",
                body=f"Error launching game:\n{e}",
                modal=True,
            )
            dialog.add_response("ok", "Ok")
            dialog.set_response_enabled("ok", True)
            dialog.set_default_response("ok")
            dialog.set_transient_for(self)
            dialog.connect("response", lambda d, r: d.close())
            dialog.present()
            self.cli_process_pid = None # Reset PID on error
            self._update_action_buttons_state() # Reset button to "Launch Game"

    def _stop_game(self):
        """Terminates the running game process group."""
        if not self.cli_process_pid:
            self.statusbar.set_label("No game process to stop.") # Changed from push
            return

        self.statusbar.set_label("Stopping game...") # Changed from push
        self.play_button.set_sensitive(False)
        self.play_button.set_label("Parando...")

        try:
            # Terminate the process group
            os.killpg(os.getpgid(self.cli_process_pid), signal.SIGTERM)
            self.logger.info(f"Sent SIGTERM to process group {os.getpgid(self.cli_process_pid)}")

            # Give it a moment to terminate
            # Gtk.timeout_add(1000, self._check_cli_process_after_term, self.cli_process_pid)
            # More direct approach: busy-wait for a short period, then force kill if needed
            for _ in range(5): # Wait up to 5 seconds
                if not self._is_process_running(self.cli_process_pid):
                    break
                time.sleep(1)

            if self._is_process_running(self.cli_process_pid):
                os.killpg(os.getpgid(self.cli_process_pid), signal.SIGKILL)
                self.logger.warning(f"Sent SIGKILL to process group {os.getpgid(self.cli_process_pid)} as SIGTERM was not enough.")

        except ProcessLookupError:
            self.logger.info(f"Process {self.cli_process_pid} already terminated or not found.")
        except OSError as e:
            self.logger.error(f"Error terminating process group for PID {self.cli_process_pid}: {e}")
        except Exception as e:
            self.logger.error(f"An unexpected error occurred while stopping the game: {e}")

        self.cli_process_pid = None
        if self.monitoring_timeout_id:
            GLib.source_remove(self.monitoring_timeout_id) # Stop monitoring
            self.monitoring_timeout_id = None
        self.statusbar.set_label("Game stopped.") # Changed from push
        self._update_action_buttons_state() # Reset button to "Launch Game"

    def _is_process_running(self, pid):
        """Checks if a process with the given PID is running."""
        if pid is None:
            return False
        try:
            os.kill(pid, 0) # Check if process exists
            return True
        except OSError:
            return False

    def _check_cli_process(self):
        """Periodically checks if the launched CLI process is still running."""
        if self.cli_process_pid and not self._is_process_running(self.cli_process_pid):
            self.logger.info(f"Detected CLI process {self.cli_process_pid} has terminated.")
            self.cli_process_pid = None
            self._update_play_button_state()
            self.statusbar.set_label("Game process terminated.") # Changed from push
            if self.monitoring_timeout_id:
                GLib.source_remove(self.monitoring_timeout_id)
                self.monitoring_timeout_id = None
            return False # Stop the timeout
        return True # Continue monitoring

    def on_layout_setting_changed(self, widget):
        """Handles changes to any of the layout settings."""
        self.drawing_area.queue_draw()

    def on_draw_window_layout(self, widget, cr, width, height):
        """Draws the window layout preview."""
        try:
            # Get configuration from UI
            layout_settings = self._get_layout_settings()

            # Validate the data
            if not self._validate_layout_data(layout_settings):
                return

            # Calculate drawing parameters
            drawing_params = self._calculate_drawing_parameters(width, height, layout_settings)

            # Create preview profile
            profile = self._create_preview_profile(layout_settings)
            if not profile:
                return

            # Setup cairo context
            cr.set_line_width(2)

            # Draw the appropriate layout
            if layout_settings['mode'] == "splitscreen" and layout_settings['num_players'] > 1:
                self._draw_splitscreen_layout(cr, profile, drawing_params, layout_settings)
            else:
                self._draw_fullscreen_layout(cr, profile, drawing_params)

        except Exception as e:
            self.logger.error(f"Error drawing window layout: {e}")

    def _get_layout_settings(self):
        """Extracts layout settings from the UI widgets."""
        return {
            'instance_width': self.instance_width_spin.get_value_as_int(),
            'instance_height': self.instance_height_spin.get_value_as_int(),
            'num_players': max(1, self.num_players_spin.get_value_as_int()),
            'mode': self.mode_combo.get_active_id(),
            'orientation': self.splitscreen_orientation_combo.get_active_id()
        }

    def _validate_layout_data(self, settings):
        """Validates the layout settings."""
        return (settings['instance_width'] > 0 and
                settings['instance_height'] > 0 and
                settings['num_players'] >= 1)

    def _calculate_drawing_parameters(self, drawing_width, drawing_height, settings):
        """Calculates the scale and offset for the drawing area."""
        scale_w = drawing_width / settings['instance_width']
        scale_h = drawing_height / settings['instance_height']
        scale = min(scale_w, scale_h) * 0.9

        scaled_total_width = settings['instance_width'] * scale
        scaled_total_height = settings['instance_height'] * scale

        return {
            'scale': scale,
            'x_offset': (drawing_width - scaled_total_width) / 2,
            'y_offset': (drawing_height - scaled_total_height) / 2
        }

    def _create_preview_profile(self, settings):
        """Creates a dummy GameProfile for the layout preview."""
        try:
            # Use model_construct to create the object without running validation,
            # which would fail on the non-existent dummy executable path.
            dummy_game = Game.model_construct(
                game_name="Preview",
                exe_path=Path("/tmp/dummy.exe"),
                is_native=False
            )
            dummy_profile = Profile(
                profile_name="Preview",
                num_players=settings['num_players'],
                instance_width=settings['instance_width'],
                instance_height=settings['instance_height'],
                mode=settings['mode'],
                splitscreen=SplitscreenConfig(orientation=settings['orientation']) if settings['mode'] == "splitscreen" else None,
                player_configs=[PlayerInstanceConfig() for _ in range(settings['num_players'])]
            )
            return GameProfile(game=dummy_game, profile=dummy_profile)
        except Exception as e:
            self.logger.error(f"Error creating preview profile: {e}")
            return None

    def _draw_splitscreen_layout(self, cr, profile, drawing_params, settings):
        """Draws the splitscreen layout."""
        for i in range(settings['num_players']):
            instance_w, instance_h = profile.get_instance_dimensions(i + 1)
            draw_w = instance_w * drawing_params['scale']
            draw_h = instance_h * drawing_params['scale']

            pos_x, pos_y = self._calculate_player_position(
                i, settings['num_players'], settings['orientation'],
                draw_w, draw_h, profile, drawing_params['scale']
            )

            self._draw_player_window(
                cr, i + 1, pos_x, pos_y, draw_w, draw_h,
                drawing_params['x_offset'], drawing_params['y_offset'],
                profile
            )

    def _draw_fullscreen_layout(self, cr, profile, drawing_params):
        """Draws the fullscreen layout."""
        instance_w, instance_h = profile.get_instance_dimensions(1)
        draw_w = instance_w * drawing_params['scale']
        draw_h = instance_h * drawing_params['scale']

        self._draw_player_window(
            cr, 1, 0, 0, draw_w, draw_h,
            drawing_params['x_offset'], drawing_params['y_offset'],
            profile
        )

    def _calculate_player_position(self, player_index, num_players, orientation, draw_w, draw_h, profile, scale):
        """Calculates the position of a player's window in the preview."""
        pos_x, pos_y = 0.0, 0.0

        if num_players == 2:
            if orientation == "horizontal":
                pos_x = player_index * draw_w
            else:  # vertical
                pos_y = player_index * draw_h
        elif num_players == 3:
            pos_x, pos_y = self._calculate_three_player_position(
                player_index, orientation, profile, scale
            )
        elif num_players == 4:
            # 2x2 grid
            row = player_index // 2
            col = player_index % 2
            pos_x = col * draw_w
            pos_y = row * draw_h
        else:  # Generic case for more than 4 players
            if orientation == "horizontal":  # Stacked vertically
                pos_y = player_index * draw_h
            else:  # vertical (Side by side)
                pos_x = player_index * draw_w

        return pos_x, pos_y

    def _calculate_three_player_position(self, player_index, orientation, profile, scale):
        """Calculates the position for a 3-player splitscreen layout."""
        p1_unscaled_w, p1_unscaled_h = profile.get_instance_dimensions(1)
        p2_unscaled_w, p2_unscaled_h = profile.get_instance_dimensions(2)

        p1_draw_w, p1_draw_h = p1_unscaled_w * scale, p1_unscaled_h * scale
        p2_draw_w, p2_draw_h = p2_unscaled_w * scale, p2_unscaled_h * scale

        if orientation == "horizontal":  # 1 large top, 2 small bottom
            if player_index == 0:  # Player 1 (top)
                return 0, 0
            elif player_index == 1:  # Player 2 (bottom-left)
                return 0, p1_draw_h
            elif player_index == 2:  # Player 3 (bottom-right)
                return p2_draw_w, p1_draw_h
        else:  # vertical: 1 large left, 2 small right
            if player_index == 0:  # Player 1 (left)
                return 0, 0
            elif player_index == 1:  # Player 2 (top-right)
                return p1_draw_w, 0
            elif player_index == 2:  # Player 3 (bottom-right)
                return p1_draw_w, p2_draw_h

        return 0, 0

    def _draw_player_window(self, cr, player_num, pos_x, pos_y, width, height, x_offset, y_offset, profile):
        """Draws a single player window in the preview."""
        # Draw window rectangle
        cr.rectangle(x_offset + pos_x, y_offset + pos_y, width, height)
        cr.set_source_rgb(1.0, 1.0, 1.0)  # White border
        cr.stroke()

        # Draw player text
        self._draw_player_text(cr, player_num, pos_x, pos_y, width, height, x_offset, y_offset)

        # Draw monitor info
        self._draw_monitor_info(cr, player_num - 1, pos_x, pos_y, width, height, x_offset, y_offset, profile)

    def _draw_player_text(self, cr, player_num, pos_x, pos_y, width, height, x_offset, y_offset):
        """Draws the player number text in the preview."""
        cr.select_font_face("Sans", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
        font_size = max(10, min(width, height) // 5)
        cr.set_font_size(font_size)
        cr.set_source_rgb(1.0, 1.0, 1.0)  # White text

        text = f"P{player_num}"
        _, _, width_text, height_text, _, _ = cr.text_extents(text)
        text_x = x_offset + pos_x + (width - width_text) / 2
        text_y = y_offset + pos_y + (height + height_text) / 2
        cr.move_to(text_x, text_y)
        cr.show_text(text)

    def _draw_monitor_info(self, cr, player_index, pos_x, pos_y, width, height, x_offset, y_offset, profile):
        """Draws the monitor ID in the preview."""
        monitor_id_text = self._get_monitor_text(player_index, profile)

        if monitor_id_text:
            # Calculate font size relative to player text
            base_font_size = max(10, min(width, height) // 5)
            font_size = base_font_size * 0.7

            cr.set_font_size(font_size)
            cr.set_source_rgb(0.7, 0.7, 0.7)  # Gray text for monitor ID

            _, _, width_text, height_text, _, _ = cr.text_extents(monitor_id_text)
            text_x = x_offset + pos_x + (width - width_text) / 2
            text_y = y_offset + pos_y + (height + height_text) / 2 + (base_font_size * 0.8)
            cr.move_to(text_x, text_y)
            cr.show_text(monitor_id_text)

    def _get_monitor_text(self, player_index, profile):
        """Gets the monitor text for a player."""
        if (profile.player_configs and
            player_index < len(profile.player_configs)):
            player_instance = profile.player_configs[player_index]
            monitor_id_from_profile = player_instance.monitor_id
            if monitor_id_from_profile:
                return self.device_id_to_name.get(monitor_id_from_profile, "None")
        return ""

    def get_profile_data(self):
        """Gets the profile data from the UI."""
        proton_version = self.proton_version_combo.get_active_text()
        if proton_version == "None (Use Steam default)" or not proton_version:
            proton_version = None

        player_configs_data = self._get_player_configs_from_ui()

        splitscreen_config = None
        if self.mode_combo.get_active_text() == "splitscreen":
            selected_orientation = self.splitscreen_orientation_combo.get_active_text()
            self.logger.info(f"DEBUG: Selected splitscreen orientation from UI: {selected_orientation}")
            splitscreen_config = SplitscreenConfig(
                orientation=selected_orientation
            )
            self.logger.info(f"DEBUG: SplitscreenConfig orientation immediately after creation: {splitscreen_config.orientation}")

        # Correctly determine is_native_value by checking if the path ends with .exe
        exe_path_text = self.exe_path_entry.get_text()
        is_native_value = False
        if exe_path_text:
            is_native_value = not Path(exe_path_text).suffix.lower() == ".exe"

        mode = self.mode_combo.get_active_text()

        winetricks_text = self.winetricks_verbs_entry.get_text().strip()
        winetricks_verbs = winetricks_text.split() if winetricks_text else None

        profile_data = GameProfile(
            game_name=self.game_name_entry.get_text(),
            exe_path=self.exe_path_entry.get_text(),
            num_players=self.num_players_spin.get_value_as_int(),
            proton_version=proton_version,
            instance_width=self.instance_width_spin.get_value_as_int(),
            instance_height=self.instance_height_spin.get_value_as_int(),
            app_id=self.app_id_entry.get_text() or None,
            game_args=self.game_args_entry.get_text(),
            env_vars=self._get_env_vars_from_ui(),
            is_native=is_native_value,
            # use_gamescope=self.use_gamescope_check.get_active(),
            # disable_bwrap=self.disable_bwrap_check.get_active(),
            apply_dxvk_vkd3d=self.apply_dxvk_vkd3d_check.get_active(),
            winetricks_verbs=winetricks_verbs,
            mode=mode,
            splitscreen=splitscreen_config,
            player_configs=player_configs_data, # Use the already collected data
        )

        self.logger.info(f"DEBUG: Mode value before GameProfile instantiation: {mode}")

        if profile_data.splitscreen:
            self.logger.info(f"DEBUG: Splitscreen orientation in GameProfile object: {profile_data.splitscreen.orientation}")

        profile_dumped = profile_data.model_dump(by_alias=True, exclude_unset=False, exclude_defaults=False, mode='json')
        self.logger.info(f"DEBUG: Collecting {len(profile_dumped.get('PLAYERS') or [])} player configs for saving.")
        self.logger.info(f"DEBUG: USE_GAMESCOPE value being saved: {profile_dumped.get('USE_GAMESCOPE', 'NOT FOUND')}")
        self.logger.info(f"DEBUG: DISABLE_BWRAP value being saved: {profile_dumped.get('DISABLE_BWRAP', 'NOT FOUND')}")
        return profile_dumped

    def _clear_all_fields(self):
        """Clears all UI input fields to their default states."""
        # Game details
        self.game_name_entry.set_text("")
        self.exe_path_entry.set_text("")
        self.app_id_entry.set_text("")
        self.game_args_entry.set_text("")
        self.is_native_check.set_active(False)

        # Profile details
        self.profile_name_entry.set_text("")
        self.proton_version_combo.set_active(0)
        self.apply_dxvk_vkd3d_check.set_active(True)
        self.winetricks_verbs_entry.set_text("")

        # Layout
        self.num_players_spin.set_value(1)
        self.instance_width_spin.set_value(1920)
        self.instance_height_spin.set_value(1080)
        self.mode_combo.set_active(0)
        self.splitscreen_orientation_combo.set_active(0)
        self.sidecar_executable_entry.set_text("")
        self.sidecar_args_entry.set_text("")
        self.sidecar_width_spin.set_value(800)
        self.sidecar_height_spin.set_value(600)

        # Env vars
        self._clear_environment_variables_ui()
        self._add_default_environment_variables()

        # Player configs
        self._create_player_config_uis(1)

        self.drawing_area.queue_draw()

    def _set_fields_sensitivity(self, is_game_selected: bool, is_profile_selected: bool):
        """Sets the sensitivity of all UI elements based on selection."""
        # Game-level fields are editable when a game is selected
        self.game_name_entry.set_sensitive(is_game_selected)
        self.exe_path_entry.set_sensitive(is_game_selected)
        self.app_id_entry.set_sensitive(is_game_selected)
        self.game_args_entry.set_sensitive(is_game_selected)
        self.is_native_check.set_sensitive(is_game_selected)
        self.proton_version_combo.set_sensitive(is_game_selected)
        self.apply_dxvk_vkd3d_check.set_sensitive(is_game_selected)
        self.winetricks_verbs_entry.set_sensitive(is_game_selected)
        self.env_vars_listbox.set_sensitive(is_game_selected)
        self.profile_selector_combo.set_sensitive(is_game_selected)

        # Profile-level fields are editable only when a profile is selected
        self.profile_name_entry.set_sensitive(is_profile_selected)
        self.num_players_spin.set_sensitive(is_profile_selected)
        self.instance_width_spin.set_sensitive(is_profile_selected)
        self.instance_height_spin.set_sensitive(is_profile_selected)
        self.mode_combo.set_sensitive(is_profile_selected)
        self.splitscreen_orientation_combo.set_sensitive(is_profile_selected)
        self.player_config_vbox.set_sensitive(is_profile_selected)
        self.sidecar_executable_entry.set_sensitive(is_profile_selected)
        self.sidecar_args_entry.set_sensitive(is_profile_selected)
        self.sidecar_width_spin.set_sensitive(is_profile_selected)
        self.sidecar_height_spin.set_sensitive(is_profile_selected)

        # Set sensitivity for the notebook tabs
        self.notebook.get_nth_page(0).set_sensitive(is_game_selected) # Game Settings
        self.notebook.get_nth_page(1).set_sensitive(is_profile_selected) # Profile Settings
        self.notebook.get_nth_page(2).set_sensitive(is_profile_selected) # Window Layout


    def _load_game_data(self, game: Game):
        """Loads data from a Game object into the UI fields."""
        self._clear_all_fields()
        # Game Details
        self.game_name_entry.set_text(game.game_name or "")
        self.exe_path_entry.set_text(str(game.exe_path) or "")
        self.app_id_entry.set_text(game.app_id or "")
        self.game_args_entry.set_text(game.game_args or "")
        self.is_native_check.set_active(game.is_native)

        # Launch Options
        if game.proton_version:
            model = self.proton_version_combo.get_model()
            for i, row in enumerate(model):
                if row[0] == game.proton_version:
                    self.proton_version_combo.set_active(i)
                    break
        else:
            self.proton_version_combo.set_active(0)

        self.apply_dxvk_vkd3d_check.set_active(game.apply_dxvk_vkd3d)
        self.winetricks_verbs_entry.set_text(" ".join(game.winetricks_verbs) if game.winetricks_verbs else "")

        # Env Vars
        self._clear_environment_variables_ui()
        if game.env_vars:
            for key, value in game.env_vars.items():
                self._add_env_var_row(key, value)
        else:
            self._add_default_environment_variables()

    def _load_profile_data(self, game: Game, profile: Profile):
        """Loads data from both a Game and a Profile object into the UI."""
        self._load_game_data(game)

        # Profile Details
        self.profile_name_entry.set_text(profile.profile_name or "")

        # Layout & Display
        self.num_players_spin.set_value(profile.num_players)
        self.instance_width_spin.set_value(profile.instance_width)
        self.instance_height_spin.set_value(profile.instance_height)
        self.mode_combo.set_active_id(profile.mode or "fullscreen")
        if profile.is_splitscreen_mode and profile.splitscreen:
            self.splitscreen_orientation_combo.set_active_id(profile.splitscreen.orientation)

        # Load Player Configs
        if profile.player_configs:
            self._create_player_config_uis(len(profile.player_configs))
            self._populate_player_configurations(profile.player_configs, profile)
        else:
            self._create_player_config_uis(profile.num_players)

        self.sidecar_executable_entry.set_text(profile.sidecar_executable or "")
        self.sidecar_args_entry.set_text(profile.sidecar_args or "")
        self.sidecar_width_spin.set_value(profile.sidecar_width or 800)
        self.sidecar_height_spin.set_value(profile.sidecar_height or 600)

        self.drawing_area.queue_draw()

    def _populate_player_configurations(self, player_configs: List[PlayerInstanceConfig], profile: Profile):
        """Populates the player configuration UI from a list of player config objects."""
        selected_players = profile.selected_players or []
        for i, player_config in enumerate(player_configs):
            if i < len(self.player_device_combos):
                player_widgets = self.player_device_combos[i]

                # Set checkbox
                self.player_checkboxes[i].set_active((i + 1) in selected_players)

                # Set text entries
                player_widgets["ACCOUNT_NAME"].set_text(player_config.ACCOUNT_NAME or "")
                player_widgets["LANGUAGE"].set_text(player_config.LANGUAGE or "")
                player_widgets["LISTEN_PORT"].set_text(player_config.LISTEN_PORT or "")
                player_widgets["USER_STEAM_ID"].set_text(player_config.USER_STEAM_ID or "")

                # Set device dropdowns
                self._set_device_dropdown(player_widgets["PHYSICAL_DEVICE_ID"], player_config.PHYSICAL_DEVICE_ID)
                self._set_device_dropdown(player_widgets["MOUSE_EVENT_PATH"], player_config.MOUSE_EVENT_PATH)
                self._set_device_dropdown(player_widgets["KEYBOARD_EVENT_PATH"], player_config.KEYBOARD_EVENT_PATH)
                self._set_device_dropdown(player_widgets["AUDIO_DEVICE_ID"], player_config.AUDIO_DEVICE_ID)
                self._set_device_dropdown(player_widgets["MONITOR_ID"], player_config.monitor_id)

    def _set_device_dropdown(self, dropdown, device_id):
        """Sets the selected item in a device dropdown."""
        device_type = getattr(dropdown, 'device_type', None)

        if device_type and device_type in self.device_lists:
            # Use device_lists for accurate mapping
            device_list = self.device_lists[device_type]
            for i, device in enumerate(device_list):
                if device["id"] == device_id:
                    dropdown.set_selected(i)
                    return
            # If not found, default to "None" (index 0)
            dropdown.set_selected(0)
        else:
            # Fallback to old method
            device_name = self.device_id_to_name.get(device_id, "None")
            selected_index = self._get_dropdown_index_for_name(dropdown, device_name)
            dropdown.set_selected(selected_index)


    def _get_dropdown_index_for_name(self, dropdown: Gtk.DropDown, name: str) -> int:
        """Gets the index of an item in a dropdown by its name."""
        model = dropdown.get_model()
        if model:
            for i in range(model.get_n_items()):
                item = model.get_item(i)
                if item and item.get_string() == name:
                    return i
        return 0 # Default to first item (e.g., "None") if not found or model is empty

    def _create_device_list_store(self, devices: List[Dict[str, str]]) -> List[str]:
        """Creates a list of strings for a device dropdown."""
        string_list_data = ["None"] # Add "None" as the first option
        for device in devices:
            # Truncate long device names with ellipsis
            device_name = device["name"]
            if len(device_name) > 22:
                device_name = device_name[:19] + "..."
            string_list_data.append(device_name)
        return string_list_data

    def _populate_profile_list(self):
        """Populates the profile listbox with available profiles."""
        # In Gtk4, Gtk.ListBox.get_children() is removed. Remove rows one by one.
        while self.profile_listbox.get_first_child():
            self.profile_listbox.remove(self.profile_listbox.get_first_child())

        profile_dir = Config.PROFILE_DIR
        profile_dir.mkdir(parents=True, exist_ok=True)

        profiles = sorted(profile_dir.glob("*.json"))

        if not profiles:
            label = Gtk.Label(label="No profiles found.\nCreate one and save it!")
            label.set_halign(Gtk.Align.CENTER)
            row = Gtk.ListBoxRow()
            row.set_child(label) # Changed from add
            self.profile_listbox.append(row) # Changed from add
            row.set_sensitive(False) # Make it non-selectable

            # Hide delete button when no profiles
            self.delete_profile_button.set_visible(False)
            self.selected_profile_name = None
        else:
            for profile_path in profiles:
                profile_name_stem = profile_path.stem # Get filename without extension
                try:
                    profile = GameProfile.load_from_file(profile_path) # Load profile, uses cache
                    display_name = profile.game_name or profile_name_stem # Use GAME_NAME, fallback to filename
                except Exception as e:
                    self.logger.warning(f"Could not load profile {profile_name_stem} for display in list: {e}")
                    display_name = profile_name_stem + " (Error)" # Indicate error

                row = Gtk.ListBoxRow()
                label = Gtk.Label(label=display_name)
                label.set_halign(Gtk.Align.START) # Align text to the start
                row.set_child(label) # Changed from add
                # Store the actual filename stem in the label's name property
                label.set_name(profile_name_stem)
                self.profile_listbox.append(row) # Changed from add

        # self.profile_listbox.show_all() # Not needed for Gtk4

    def _on_profile_selected_from_list(self, listbox, row):
        """Handles the selection of a profile from the listbox."""
        profile_name_stem = row.get_child().get_name() # Get the filename stem from the label's name property
        if not profile_name_stem:
            self.logger.warning("Attempted to select a profile without a stored filename property.")
            return

        # Update selected profile and show delete button
        self.selected_profile_name = profile_name_stem
        self.delete_profile_button.set_visible(True)

        profile_path = Config.PROFILE_DIR / f"{profile_name_stem}.json"
        self.logger.info(f"Loading profile from sidebar: {profile_name_stem}")

        try:
            profile = GameProfile.load_from_file(profile_path)
            self.load_profile_data(profile.model_dump(by_alias=True))
            self.statusbar.set_label(f"Profile loaded: {profile_name_stem}") # Changed from push
            # Switch to General Settings tab after loading
            self.notebook.set_current_page(0)
        except Exception as e:
            self.logger.error(f"Failed to load profile {profile_name_stem}: {e}")
            # Show error dialog
            error_dialog = Adw.MessageDialog(
                heading="Load Error",
                body=f"Failed to load profile '{profile_name_stem}':\n{str(e)}"
            )
            error_dialog.add_response("ok", "OK")
            error_dialog.set_default_response("ok")
            error_dialog.set_close_response("ok")
            error_dialog.set_transient_for(self)
            error_dialog.connect("response", lambda d, r: d.close())
            error_dialog.present()

    def _on_add_game_clicked(self, button):
        """Handles the 'Add Game' button click by showing a dialog."""
        dialog = Gtk.Dialog(title="Add New Game", transient_for=self, modal=True)
        dialog.add_buttons(
            "_Cancel", Gtk.ResponseType.CANCEL,
            "_Add", Gtk.ResponseType.OK
        )
        dialog.get_widget_for_response(Gtk.ResponseType.OK).add_css_class("suggested-action")

        content_area = dialog.get_content_area()
        grid = Gtk.Grid(column_spacing=10, row_spacing=10, margin_start=10, margin_end=10, margin_top=10, margin_bottom=10)
        content_area.append(grid)

        grid.attach(Gtk.Label(label="Game Name:", xalign=0), 0, 0, 1, 1)
        name_entry = Gtk.Entry(placeholder_text="e.g., Elden Ring")
        grid.attach(name_entry, 1, 0, 1, 1)

        grid.attach(Gtk.Label(label="Executable Path:", xalign=0), 0, 1, 1, 1)

        exe_path_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)
        exe_path_entry = Gtk.Entry(placeholder_text="Path to game's .exe", hexpand=True)
        exe_path_box.append(exe_path_entry)

        browse_button = Gtk.Button(label="Browse...")

        def on_browse_clicked(btn):
            file_dialog = Gtk.FileChooserDialog(
                title="Select Game Executable",
                transient_for=dialog,
                action=Gtk.FileChooserAction.OPEN,
            )
            file_dialog.add_buttons("_Cancel", Gtk.ResponseType.CANCEL, "_Open", Gtk.ResponseType.OK)

            def on_file_dialog_response(d, response_id):
                if response_id == Gtk.ResponseType.OK:
                    file = d.get_file()
                    if file:
                        exe_path_entry.set_text(file.get_path())
                d.destroy()

            file_dialog.connect("response", on_file_dialog_response)
            file_dialog.show()

        browse_button.connect("clicked", on_browse_clicked)
        exe_path_box.append(browse_button)
        grid.attach(exe_path_box, 1, 1, 1, 1)

        def on_response(d, response_id):
            if response_id == Gtk.ResponseType.OK:
                game_name = name_entry.get_text().strip()
                exe_path = exe_path_entry.get_text().strip()
                if game_name and exe_path:
                    try:
                        new_game = Game(game_name=game_name, exe_path=Path(exe_path))
                        self.game_manager.add_game(new_game)
                        self._populate_game_library()
                        self.statusbar.set_label(f"Game '{game_name}' added successfully.")
                    except Exception as e:
                        self.logger.error(f"Failed to add game: {e}")
                        self.statusbar.set_label(f"Error: {e}")
                else:
                    self.statusbar.set_label("Game Name and Executable Path cannot be empty.")
            d.destroy()

        dialog.connect("response", on_response)
        dialog.show()

    def _on_add_profile_clicked(self, button):
        """Handles the 'Add Profile' button click by showing a dialog."""
        if not self.selected_game:
            self.statusbar.set_label("Please select a game before adding a profile.")
            return

        dialog = Gtk.Dialog(title=f"Add Profile to {self.selected_game.game_name}", transient_for=self, modal=True)
        dialog.add_buttons(
            "_Cancel", Gtk.ResponseType.CANCEL,
            "_Create", Gtk.ResponseType.OK
        )
        dialog.get_widget_for_response(Gtk.ResponseType.OK).add_css_class("suggested-action")

        content_area = dialog.get_content_area()
        grid = Gtk.Grid(column_spacing=10, row_spacing=10, margin_start=10, margin_end=10, margin_top=10, margin_bottom=10)
        content_area.append(grid)

        grid.attach(Gtk.Label(label="New Profile Name:", xalign=0), 0, 0, 1, 1)
        name_entry = Gtk.Entry(placeholder_text="e.g., Modded, Speedrun")
        grid.attach(name_entry, 1, 0, 1, 1)

        def on_response(d, response_id):
            if response_id == Gtk.ResponseType.OK:
                profile_name = name_entry.get_text().strip()
                if profile_name:
                    try:
                        # Create a default profile
                        new_profile = Profile(
                            profile_name=profile_name,
                            num_players=2,
                            instance_width=1920,
                            instance_height=1080,
                            player_configs=[PlayerInstanceConfig(), PlayerInstanceConfig()]
                        )
                        game_name = self.selected_game.game_name
                        self.game_manager.add_profile(self.selected_game, new_profile)
                        self.statusbar.set_label(f"Profile '{profile_name}' added to {game_name}.")
                        self._populate_game_library()
                    except Exception as e:
                        self.logger.error(f"Failed to add profile: {e}")
                        self.statusbar.set_label(f"Error: {e}")
                else:
                    self.statusbar.set_label("Profile name cannot be empty.")
            d.destroy()

        dialog.connect("response", on_response)
        dialog.show()

    def _on_delete_clicked(self, button):
        """Handles the 'Delete' button click for either a game or a profile."""
        if self.selected_profile:
            # Delete profile logic
            self.logger.info(f"Deleting profile: {self.selected_profile.profile_name}")
            self.game_manager.delete_profile(self.selected_game, self.selected_profile)
        elif self.selected_game:
            # Delete game logic
            self.logger.info(f"Deleting game: {self.selected_game.game_name}")
            self.game_manager.delete_game(self.selected_game)

        self._populate_game_library()
        self._clear_all_fields()

    def _on_close_request(self, window):
        """Handles the window close request."""
        if self.cli_process_pid:
            self.logger.info("Close requested, but game is running. Stopping game first.")
            self.statusbar.set_label("Game is running. Stopping instances before closing...")
            self._stop_game()

            # We can't immediately close because _stop_game is asynchronous in its effect.
            # We need to wait until the process is confirmed dead.
            # We can use a timeout to check for process termination.
            def check_if_can_close():
                if not self._is_process_running(self.cli_process_pid):
                    self.logger.info("Game has been stopped. Now closing the window.")
                    self.close() # Now we can close for real
                    return GLib.SOURCE_REMOVE # Stop the timeout
                return GLib.SOURCE_CONTINUE # Continue checking

            GLib.timeout_add(500, check_if_can_close)

            return True # Prevent the default close handler from running

        self.logger.info("No game running. Closing window.")
        return False # Allow the default close handler to run

    def _on_close_request(self, window):
        """Handles the window close request."""
        if self.cli_process_pid:
            self.logger.info("Close requested, but game is running. Stopping game first.")
            self.statusbar.set_label("Game is running. Stopping instances before closing...")
            self._stop_game()

            # We can't immediately close because _stop_game is asynchronous in its effect.
            # We need to wait until the process is confirmed dead.
            # We can use a timeout to check for process termination.
            def check_if_can_close():
                if not self._is_process_running(self.cli_process_pid):
                    self.logger.info("Game has been stopped. Now closing the window.")
                    self.close() # Now we can close for real
                    return GLib.SOURCE_REMOVE # Stop the timeout
                return GLib.SOURCE_CONTINUE # Continue checking

            GLib.timeout_add(500, check_if_can_close)

            return True # Prevent the default close handler from running

        self.logger.info("No game running. Closing window.")
        return False # Allow the default close handler to run

class LinuxCoopApp(Adw.Application):
    """
    The main application class, inheriting from Adw.Application.

    This class is the entry point for the GUI. It handles application
    initialization, activation, styling, and signal handling for graceful
    shutdown.
    """
    def __init__(self):
        """Initializes the Adwaita application."""
        super().__init__(application_id="org.protoncoop.app")
        self.connect("activate", self.on_activate)

        # Initialize Adwaita
        Adw.init()

        # Configure proper Adwaita style manager to avoid warnings
        self._configure_adwaita_style()

        # Initialize styles using the professional StyleManager
        self._initialize_application_styles()

        # Set up a signal handler for SIGUSR1 to allow the child process to close the GUI
        GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGUSR1, self._handle_shutdown_signal, "SIGUSR1")
        # Set up a signal handler for SIGTERM to allow the system to close the GUI gracefully
        GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGTERM, self._handle_shutdown_signal, "SIGTERM")

    def _handle_shutdown_signal(self, signal_name):
        """Signal handler for SIGUSR1 or SIGTERM. Closes the main window."""
        self.logger.info(f"Received {signal_name}, closing the main window gracefully.")
        # Get the active window and close it. `self.quit()` is another option.
        window = self.get_active_window()
        if window:
            window.close() # This will trigger the _on_close_request logic
        else:
            # If there's no window, just quit the app
            self.quit()
        return True # Keep the signal handler active

    def _configure_adwaita_style(self):
        """Configures the Adwaita style manager to follow the system theme."""
        try:
            style_manager = Adw.StyleManager.get_default()
            # Use PREFER_DARK to automatically follow system theme preference
            # This will use dark theme when system prefers dark, light when system prefers light
            style_manager.set_color_scheme(Adw.ColorScheme.PREFER_DARK)

            # Optional: Connect to theme changes to update custom styles if needed
            style_manager.connect("notify::dark", self._on_theme_changed)

            # Log current theme state
            is_dark = style_manager.get_dark()
            theme_name = "dark" if is_dark else "light"
            self.logger = Logger(name="LinuxCoopGUI", log_dir=Path("./logs"))
            self.logger.info(f"Configured Adwaita to follow system theme. Current theme: {theme_name}")
        except Exception as e:
            # Fallback if AdwStyleManager is not available
            self.logger = Logger(name="LinuxCoopGUI", log_dir=Path("./logs"))
            self.logger.warning(f"Could not configure Adwaita style manager: {e}")

    def _on_theme_changed(self, style_manager, param):
        """Handles system theme changes."""
        try:
            is_dark = style_manager.get_dark()
            theme_name = "dark" if is_dark else "light"
            self.logger.info(f"System theme changed to: {theme_name}")

            # Trigger StyleManager to reload theme-specific styles
            from .styles import get_style_manager
            style_manager_instance = get_style_manager()
            style_manager_instance._load_theme_specific_styles()

            # Update window styling if needed
            self._update_window_for_theme(is_dark)
        except Exception as e:
            self.logger.warning(f"Error handling theme change: {e}")

    def _update_window_for_theme(self, is_dark: bool):
        """Updates the window styling based on the theme."""
        try:
            # Force refresh of all widgets to apply new theme
            self.queue_draw()

            # Update any theme-sensitive components
            if hasattr(self, 'drawing_area'):
                self.drawing_area.queue_draw()

        except Exception as e:
            self.logger.warning(f"Error updating window for theme: {e}")

    def _initialize_application_styles(self):
        """Initializes custom application-wide CSS styles."""
        try:
            initialize_styles()
            self.logger = Logger(name="LinuxCoopGUI", log_dir=Path("./logs"))
            self.logger.info("Successfully initialized application styles")
        except StyleManagerError as e:
            # Fallback to basic styling if StyleManager fails
            self.logger = Logger(name="LinuxCoopGUI", log_dir=Path("./logs"))
            self.logger.warning(f"Failed to initialize StyleManager: {e}")
            self._apply_fallback_styles()

    def _apply_fallback_styles(self):
        """Applies minimal fallback styles if the StyleManager fails."""
        try:
            style_manager = get_style_manager()
            fallback_css = """
            /* Minimal fallback styles */
            * { font-family: system-ui, sans-serif; }
            label { padding: 4px 0; min-height: 20px; }
            entry, button { padding: 6px; min-height: 28px; }
            """
            style_manager.load_css_from_string(fallback_css, "fallback")
        except Exception as e:
            self.logger.error(f"Even fallback styles failed: {e}")

    def on_activate(self, app):
        """
        Called when the application is activated.

        This method creates and presents the main `ProfileEditorWindow`.

        Args:
            app (LinuxCoopApp): The application instance.
        """
        window = ProfileEditorWindow(app)
        window.present() # Changed from show_all() or show()

def run_gui():
    """The main entry point function to start the GUI application."""
    app = LinuxCoopApp()
    app.run(None)

if __name__ == "__main__":
    # This ensures that the GUI is only started if the script is executed directly
    # and not when imported as a module.
    gi.require_version("Gtk", "4.0")
    gi.require_version("Adw", "1") # Added Adw require
    from gi.repository import Gtk, Gdk, Adw # Added Adw import
    import cairo # Import cairo here for drawing
    import time # Import time for busy-wait in _stop_game
    from gi.repository import GLib # Importado para usar GLib.timeout_add
    run_gui()
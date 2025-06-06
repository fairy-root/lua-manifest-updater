import customtkinter as ctk
import tkinter as tk
from tkinter import filedialog, messagebox
from tkinterdnd2 import DND_FILES, TkinterDnD
import requests
import os
import sys
import re
import urllib3
import zipfile
import shutil
import threading
import webbrowser
from PIL import Image, ImageOps, ImageDraw
from customtkinter import CTkImage
import io
from bs4 import BeautifulSoup
import time
import json

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


APP_NAME = "Lua Manifest Updater"
APP_VERSION = "1.0.3"
WINDOW_WIDTH = 550
WINDOW_HEIGHT = 830
DEFAULT_OUTPUT_SUBDIR = "Updated Files"
TELEGRAM_LINK = "https://t.me/FairyRoot"


APP_BG_COLOR = "#222222"
MAIN_FRAME_BG_COLOR = "#2E2E2E"
SECTION_CARD_BG_COLOR = "#383838"
SECTION_CARD_BORDER_COLOR = "#484848"
DND_FRAME_FG_COLOR = "#333333"
DND_FRAME_BORDER_COLOR = "#5D5FEF"


def get_game_id_from_content(content):
    """Extracts game ID from manifest content using regex."""
    match = re.search(r'addappid\s*\(\s*(\d+|"(\d+)")', content)
    if match:
        game_id = match.group(2) if match.group(2) else match.group(1)
        return game_id
    return None


def download_file(url, filename, status_callback):
    """Downloads a file from a URL, updating status via callback.

    Args:
        url (str): The URL to download from.
        filename (str): The local path to save the downloaded file.
        status_callback (function): Callback to report status (message, color).

    Returns:
        bool: True if download was successful, False otherwise.
    """
    try:
        status_callback(f"Downloading: {os.path.basename(filename)}...", "orange")
        response = requests.get(url, verify=False, stream=True, timeout=30)
        response.raise_for_status()
        with open(filename, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
        status_callback(
            f"Successfully downloaded {os.path.basename(filename)}", "lightgreen"
        )
        return True
    except requests.exceptions.Timeout:
        status_callback(
            f"Error: Download timed out for {os.path.basename(filename)}", "red"
        )
        return False
    except requests.exceptions.RequestException as e:
        status_callback(f"Error downloading {os.path.basename(filename)}: {e}", "red")
        return False
    except Exception as e:
        status_callback(
            f"Error during download of {os.path.basename(filename)}: {e}", "red"
        )
        return False


def extract_files_gui(filename, extract_dir, status_callback):
    """Extracts .manifest files from a zip archive, updating status via callback.

    Args:
        filename (str): Path to the zip file.
        extract_dir (str): Directory to extract manifest files into.
        status_callback (function): Callback to report status.

    Returns:
        list or None: A list of paths to extracted manifest files, or None on error.
    """
    try:
        status_callback("Extracting files...", "orange")
        os.makedirs(extract_dir, exist_ok=True)
        extracted_manifests = []
        with zipfile.ZipFile(filename, "r") as zip_ref:
            for file_info in zip_ref.infolist():
                if file_info.filename.startswith("/") or ".." in file_info.filename:
                    continue
                if file_info.filename.endswith(".manifest"):
                    target_path = os.path.join(
                        extract_dir, os.path.basename(file_info.filename)
                    )
                    with zip_ref.open(file_info) as source, open(
                        target_path, "wb"
                    ) as target:
                        shutil.copyfileobj(source, target)
                    extracted_manifests.append(target_path)

        if not extracted_manifests:
            status_callback(
                "Warning: No .manifest files found in the downloaded archive.", "orange"
            )

        status_callback("Successfully extracted manifest files", "lightgreen")
        return extracted_manifests
    except zipfile.BadZipFile:
        status_callback(
            f"Error: Downloaded file '{os.path.basename(filename)}' is not a valid zip archive.",
            "red",
        )
        return None
    except Exception as e:
        status_callback(f"Error extracting files: {e}", "red")
        return None


def delete_item(item_path):
    """Deletes a file or directory recursively, without status updates to GUI.

    Args:
        item_path (str): Path to the file or directory to delete.

    Returns:
        bool: True if deletion was successful or item didn't exist, False on error.
    """
    try:
        if os.path.exists(item_path):
            if os.path.isfile(item_path):
                os.remove(item_path)
            elif os.path.isdir(item_path):
                shutil.rmtree(item_path)
            return True
        return True
    except Exception as e:
        print(f"Warn: Error deleting {os.path.basename(item_path)}: {e}")
        return False


def update_lua_file_gui(
    original_lua_path, extracted_manifest_paths, game_id, temp_dir, status_callback
):
    """Updates the lua file content with new manifest IDs from extracted files.

    Args:
        original_lua_path (str): Path to the original Lua file.
        extracted_manifest_paths (list): List of paths to extracted .manifest files.
        game_id (str): The game ID.
        temp_dir (str): Directory to save the temporary updated Lua file.
        status_callback (function): Callback to report status.

    Returns:
        str or None: Path to the temporary updated Lua file, or None on error.
    """
    temp_lua_filename = f"temp_{game_id}_{os.path.basename(original_lua_path)}"
    temp_lua_filepath = os.path.join(temp_dir, temp_lua_filename)
    try:
        status_callback("Updating Lua file with new Manifest IDs...", "orange")
        with open(original_lua_path, "r", encoding="utf-8") as f:
            lua_content = f.read()

        manifest_map = {}
        for manifest_path in extracted_manifest_paths:
            match = re.match(r"(\d+)_(\d+)\.manifest", os.path.basename(manifest_path))
            if match:
                app_id, manifest_id = match.groups()
                manifest_map[app_id] = manifest_id

        def replace_manifest_id(match):
            app_id = match.group(1)
            new_id = manifest_map.get(app_id)
            return (
                f'setManifestid({app_id}, "{new_id}", 0)' if new_id else match.group(0)
            )

        updated_content, num_replacements = re.subn(
            r'setManifestid\s*\(\s*(\d+)\s*,\s*"(\d+)"\s*,\s*0\s*\)',
            replace_manifest_id,
            lua_content,
        )

        status_msg = (
            f"Updated {num_replacements} Manifest ID(s)."
            if num_replacements > 0
            else "No Manifest IDs needed updating."
        )
        status_callback(status_msg, "lightblue")

        os.makedirs(os.path.dirname(temp_lua_filepath), exist_ok=True)
        with open(temp_lua_filepath, "w", encoding="utf-8") as f:
            f.write(updated_content)

        status_callback("Successfully prepared updated Lua file", "lightgreen")
        return temp_lua_filepath

    except FileNotFoundError:
        status_callback(
            f"Error: Original Lua file not found at {original_lua_path}", "red"
        )
        return None
    except Exception as e:
        status_callback(f"Error updating lua file: {e}", "red")
        if os.path.exists(temp_lua_filepath):
            delete_item(temp_lua_filepath)
        return None


def zip_files_gui(
    output_zip_path,
    updated_lua_path,
    game_id,
    extracted_manifest_paths,
    status_callback,
):
    """Zips the updated lua file and extracted manifest files.

    Args:
        output_zip_path (str): Path for the output zip file.
        updated_lua_path (str): Path to the updated Lua file.
        game_id (str): The game ID.
        extracted_manifest_paths (list): List of paths to extracted .manifest files.
        status_callback (function): Callback to report status.

    Returns:
        bool: True if zipping was successful, False otherwise.
    """
    try:
        status_callback(
            f"Creating final zip: {os.path.basename(output_zip_path)}...", "orange"
        )
        os.makedirs(os.path.dirname(output_zip_path), exist_ok=True)

        with zipfile.ZipFile(output_zip_path, "w", zipfile.ZIP_DEFLATED) as zip_ref:
            if updated_lua_path and os.path.exists(updated_lua_path):
                zip_ref.write(updated_lua_path, f"{game_id}.lua")
            else:
                status_callback(
                    "Error: Temporary updated Lua file not found for zipping.", "red"
                )
                return False

            manifest_added = False
            for manifest_path in extracted_manifest_paths:
                if os.path.exists(manifest_path):
                    zip_ref.write(manifest_path, os.path.basename(manifest_path))
                    manifest_added = True

            if not manifest_added and extracted_manifest_paths:
                status_callback(
                    "Warning: No extracted .manifest files were added to the zip (they might be missing).",
                    "orange",
                )

        status_callback(
            f"Successfully created {os.path.basename(output_zip_path)}", "lightgreen"
        )
        return True
    except Exception as e:
        status_callback(f"Error creating zip file: {e}", "red")
        return False


class App(TkinterDnD.Tk):
    """Main application class for Lua Manifest Updater."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.selected_file_path = ctk.StringVar()
        self.repos_config = {}
        self.selected_repo_key = ctk.StringVar()

        self._load_repos_config()

        try:
            desktop_path = os.path.join(os.path.expanduser("~"), "Desktop")
            if not os.path.isdir(desktop_path):
                desktop_path = os.path.expanduser("~")
            self.default_output_dir = os.path.join(desktop_path, DEFAULT_OUTPUT_SUBDIR)
        except Exception:
            self.default_output_dir = os.path.join(
                os.path.dirname(os.path.abspath(__file__)), DEFAULT_OUTPUT_SUBDIR
            )

        self.output_folder_path = ctk.StringVar(value=self.default_output_dir)
        self.status_message = ctk.StringVar(value="Select or drop a .lua file")
        self.is_processing = False
        self.current_game_id = None

        self.title(f"{APP_NAME} v{APP_VERSION}")
        self.geometry(f"{WINDOW_WIDTH}x{WINDOW_HEIGHT}")
        self.configure(bg=APP_BG_COLOR)
        self.resizable(False, False)

        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self.main_frame = ctk.CTkFrame(self, fg_color=MAIN_FRAME_BG_COLOR)
        self.main_frame.pack(pady=10, padx=10, fill="both", expand=True)

        self.header_frame = ctk.CTkFrame(
            self.main_frame,
            fg_color=SECTION_CARD_BG_COLOR,
            corner_radius=8,
            border_width=1,
            border_color=SECTION_CARD_BORDER_COLOR,
        )
        self.header_frame.pack(pady=(5, 10), padx=10, fill="x")

        try:
            img_path = "imgs/FairyRoot.png"
            original_image = Image.open(img_path).convert("RGBA")
            size = (80, 80)

            mask = Image.new("L", size, 0)
            draw = ImageDraw.Draw(mask)
            draw.ellipse((0, 0) + size, fill=255)

            masked_image = ImageOps.fit(original_image, size, centering=(0.5, 0.5))
            masked_image.putalpha(mask)

            self.fairyroot_image = CTkImage(
                light_image=masked_image, dark_image=masked_image, size=size
            )

            self.image_label = ctk.CTkLabel(
                self.header_frame, text="", image=self.fairyroot_image, cursor="hand2"
            )
            self.image_label.pack(side="left", padx=15, pady=10)
            self.image_label.bind("<Button-1>", lambda e: self.join_telegram())

        except FileNotFoundError:
            print(f"Warning: Header image not found at {img_path}")
            self.image_label = ctk.CTkLabel(
                self.header_frame,
                text="[IMG]",
                width=size[0],
                height=size[1],
                cursor="hand2",
            )
            self.image_label.pack(side="left", padx=15, pady=10)
            self.image_label.bind("<Button-1>", lambda e: self.join_telegram())
        except Exception as e:
            print(f"Error loading header image: {e}")
            self.image_label = ctk.CTkLabel(
                self.header_frame,
                text="[ERR]",
                width=size[0],
                height=size[1],
                cursor="hand2",
            )
            self.image_label.pack(side="left", padx=15, pady=10)
            self.image_label.bind("<Button-1>", lambda e: self.join_telegram())

        self.text_frame = ctk.CTkFrame(self.header_frame, fg_color="transparent")
        self.text_frame.pack(side="left", fill="x", expand=True, pady=10, padx=(0, 10))

        self.fairyroot_label = ctk.CTkLabel(
            self.text_frame,
            text="FairyRoot",
            font=ctk.CTkFont(size=18, weight="bold"),
            anchor="w",
        )
        self.fairyroot_label.pack(pady=(0, 2), fill="x")

        self.app_name_label = ctk.CTkLabel(
            self.text_frame,
            text=APP_NAME,
            font=ctk.CTkFont(size=16),
            anchor="w",
            text_color="darkgray",
        )
        self.app_name_label.pack(pady=(0, 2), fill="x")

        self.version_label = ctk.CTkLabel(
            self.text_frame,
            text=f"Version {APP_VERSION}",
            font=ctk.CTkFont(size=12),
            anchor="w",
            text_color="gray",
        )
        self.version_label.pack(pady=(0, 0), fill="x")

        self.file_repo_frame = ctk.CTkFrame(
            self.main_frame,
            fg_color=SECTION_CARD_BG_COLOR,
            corner_radius=8,
            border_width=1,
            border_color=SECTION_CARD_BORDER_COLOR,
        )
        self.file_repo_frame.pack(pady=10, padx=10, fill="x")

        self.select_prompt_label = ctk.CTkLabel(
            self.file_repo_frame,
            text="Select a .lua file or drag and drop it below",
            text_color="gray",
        )
        self.select_prompt_label.pack(pady=(10, 5))

        self.select_file_button = ctk.CTkButton(
            self.file_repo_frame,
            text="Select File",
            command=self.select_file,
            width=180,
            height=35,
            font=ctk.CTkFont(size=14),
        )
        self.select_file_button.pack(pady=5)

        self.repo_label = ctk.CTkLabel(
            self.file_repo_frame, text="Select Repository:", text_color="gray"
        )
        self.repo_label.pack(pady=(10, 0))

        dropdown_values = (
            list(self.repos_config.keys()) if self.repos_config else ["N/A"]
        )
        self.repo_dropdown = ctk.CTkOptionMenu(
            self.file_repo_frame,
            variable=self.selected_repo_key,
            values=dropdown_values,
            command=self.on_repo_select,
            width=180,
            height=35,
            font=ctk.CTkFont(size=14),
        )
        if not self.repos_config:
            self.repo_dropdown.set("N/A")
            self.repo_dropdown.configure(state="disabled")
        self.repo_dropdown.pack(pady=(5, 10))

        self.output_action_frame = ctk.CTkFrame(
            self.main_frame,
            fg_color=SECTION_CARD_BG_COLOR,
            corner_radius=8,
            border_width=1,
            border_color=SECTION_CARD_BORDER_COLOR,
        )
        self.output_action_frame.pack(pady=10, padx=10, fill="x")

        self.output_controls_container = ctk.CTkFrame(
            self.output_action_frame, fg_color="transparent"
        )
        self.output_controls_container.pack(pady=(10, 5), fill="x")

        self.output_label = ctk.CTkLabel(
            self.output_controls_container,
            text="Output Folder:",
            text_color="gray",
            anchor="w",
        )
        self.output_label.pack(side="top", padx=(10, 5), anchor="center")

        self.browse_button = ctk.CTkButton(
            self.output_controls_container,
            text="Browse",
            command=self.select_output_folder,
            width=100,
            height=30,
        )
        self.browse_button.pack(side="top", anchor="center")

        self.output_controls_container.pack_configure(anchor="center")

        self.output_path_label = ctk.CTkLabel(
            self.output_action_frame,
            textvariable=self.output_folder_path,
            text_color="green",
            wraplength=WINDOW_WIDTH - 80,
            anchor="center",
            justify="center",
            font=ctk.CTkFont(size=11),
        )
        self.output_path_label.pack(pady=(0, 10), fill="x", padx=10)

        self.update_button = ctk.CTkButton(
            self.output_action_frame,
            text="Update",
            command=self.start_update_process,
            width=180,
            height=40,
            font=ctk.CTkFont(size=16, weight="bold"),
        )
        self.update_button.pack(pady=(5, 15))

        self.status_display_frame = ctk.CTkFrame(
            self.main_frame,
            fg_color=SECTION_CARD_BG_COLOR,
            corner_radius=8,
            border_width=1,
            border_color=SECTION_CARD_BORDER_COLOR,
        )
        self.status_display_frame.pack(pady=10, padx=10, fill="x")

        self.status_label = ctk.CTkLabel(
            self.status_display_frame,
            textvariable=self.status_message,
            wraplength=WINDOW_WIDTH - 80,
            font=ctk.CTkFont(size=12),
            text_color="lightgreen",
        )
        self.status_label.pack(pady=8, padx=10, fill="x")

        self.dnd_frame = ctk.CTkFrame(
            self.main_frame,
            border_width=2,
            border_color=DND_FRAME_BORDER_COLOR,
            fg_color=DND_FRAME_FG_COLOR,
            corner_radius=15,
        )
        self.dnd_frame.pack(pady=(5, 10), padx=10, fill="both", expand=True)
        self.dnd_frame.grid_propagate(False)
        self.dnd_frame.grid_rowconfigure(1, weight=1)
        self.dnd_frame.grid_columnconfigure(0, weight=1)

        self.dnd_placeholder_label = ctk.CTkLabel(
            self.dnd_frame,
            text="Drag and drop .lua file here",
            font=ctk.CTkFont(size=14),
            text_color="gray",
        )
        self.dnd_placeholder_label.grid(row=0, column=0, rowspan=2, sticky="nsew")

        self.dnd_game_image_label = None
        self.dnd_game_desc_textbox = None

        self.dnd_frame.drop_target_register(DND_FILES)
        self.dnd_frame.dnd_bind("<<Drop>>", self.handle_drop)
        self.dnd_placeholder_label.drop_target_register(DND_FILES)
        self.dnd_placeholder_label.dnd_bind("<<Drop>>", self.handle_drop)

    def _load_repos_config(self):
        """Loads repository configuration from repo.json.
        Sets default repository and updates dropdown options.
        """
        self.repos_config = {}
        default_repo_path_target = "Fairyvmos/BlankTMing"
        key_to_select_by_default = None

        try:
            with open("repo.json", "r", encoding="utf-8") as f:
                data = json.load(f)

            default_repo_path_target = data.get("default", "Fairyvmos/BlankTMing")

            for key, value in data.items():
                if key != "default":
                    self.repos_config[key] = value

            key_to_select_by_default = next(
                (
                    name
                    for name, path in self.repos_config.items()
                    if path == default_repo_path_target
                ),
                None,
            )

            if not key_to_select_by_default:

                if default_repo_path_target not in self.repos_config.values():
                    self.repos_config[default_repo_path_target] = (
                        default_repo_path_target
                    )
                key_to_select_by_default = default_repo_path_target

        except FileNotFoundError:
            if hasattr(self, "update_status"):
                self.update_status("repo.json not found. Creating default.", "orange")
            else:
                print("repo.json not found. Creating default.")

            default_data_to_write = {
                "default": "Fairyvmos/BlankTMing",
                "FairyRoot": "Fairyvmos/BlankTMing",
            }
            try:
                with open("repo.json", "w", encoding="utf-8") as f:
                    json.dump(default_data_to_write, f, indent=4)
                self.repos_config = {"FairyRoot": "Fairyvmos/BlankTMing"}
                key_to_select_by_default = "FairyRoot"
            except Exception as e_write:
                error_msg = f"Error creating repo.json: {e_write}"
                if hasattr(self, "update_status"):
                    self.update_status(error_msg, "red")
                else:
                    print(error_msg)
                self.repos_config = {"Fallback_Default": "Fairyvmos/BlankTMing"}
                key_to_select_by_default = "Fallback_Default"

        except json.JSONDecodeError:
            error_msg = "Error decoding repo.json. Using fallback."
            if hasattr(self, "update_status"):
                self.update_status(error_msg, "red")
            else:
                print(error_msg)
            self.repos_config = {"Fallback_JsonError": "Fairyvmos/BlankTMing"}
            key_to_select_by_default = "Fallback_JsonError"
        except Exception as e:
            error_msg = f"Error loading repos: {e}"
            if hasattr(self, "update_status"):
                self.update_status(error_msg, "red")
            else:
                print(error_msg)
            self.repos_config = {"Fallback_GeneralError": "Fairyvmos/BlankTMing"}
            key_to_select_by_default = "Fallback_GeneralError"

        if key_to_select_by_default and key_to_select_by_default in self.repos_config:
            self.selected_repo_key.set(key_to_select_by_default)
        elif self.repos_config:
            self.selected_repo_key.set(list(self.repos_config.keys())[0])
        else:
            self.repos_config = {"ErrorCaseRepo": "Fairyvmos/BlankTMing"}
            self.selected_repo_key.set("ErrorCaseRepo")

        if (
            hasattr(self, "repo_dropdown")
            and self.repo_dropdown
            and self.repo_dropdown.winfo_exists()
        ):
            current_keys = list(self.repos_config.keys())
            self.repo_dropdown.configure(
                values=current_keys if current_keys else ["N/A"]
            )
            if self.selected_repo_key.get() in current_keys:
                self.repo_dropdown.set(self.selected_repo_key.get())
            elif current_keys:
                self.repo_dropdown.set(current_keys[0])
                self.selected_repo_key.set(current_keys[0])
            else:
                self.repo_dropdown.set("N/A")
                self.repo_dropdown.configure(state="disabled")

    def on_repo_select(self, selected_display_name):
        """Handles repository selection change from the dropdown."""
        repo_path = self.repos_config.get(selected_display_name)
        if repo_path:
            self.update_status(f"Repository: {selected_display_name}", "lightblue")
        else:
            self.update_status(
                f"Unknown repository selected: {selected_display_name}", "orange"
            )

    def _clear_dnd_area(self):
        """Removes existing game info widgets from the DND frame."""
        if self.dnd_game_image_label:
            self.dnd_game_image_label.grid_forget()
            self.dnd_game_image_label.destroy()
            self.dnd_game_image_label = None
        if self.dnd_game_desc_textbox:
            self.dnd_game_desc_textbox.grid_forget()
            self.dnd_game_desc_textbox.destroy()
            self.dnd_game_desc_textbox = None
        if self.dnd_placeholder_label:
            if self.dnd_placeholder_label.winfo_exists():
                self.dnd_placeholder_label.grid_forget()
                self.dnd_placeholder_label.destroy()
            self.dnd_placeholder_label = None

    def _update_dnd_area_display(self, image, description, error_message):
        """Updates the DND frame with game info or an error message.
        Uses CTkTextbox for description. Click to refresh for actual errors.
        """
        if not self.dnd_frame.winfo_exists():
            return
        self._clear_dnd_area()

        try:
            frame_width = self.dnd_frame.winfo_width()
            if frame_width <= 1:
                frame_width = WINDOW_WIDTH - 80
        except tk.TclError:
            frame_width = WINDOW_WIDTH - 80

        if error_message is not None:
            is_actual_error = any(
                keyword in error_message.lower()
                for keyword in ["error", "could not find", "failed"]
            )

            display_text = error_message
            cursor_type = ""
            click_binding = None

            if is_actual_error:
                display_text = f"{error_message}\n(Click here to refresh)"
                cursor_type = "hand2"
                click_binding = self._retry_fetch_game_info

            self.dnd_placeholder_label = ctk.CTkLabel(
                self.dnd_frame,
                text=display_text,
                font=ctk.CTkFont(size=12),
                text_color="orange",
                wraplength=frame_width - 20,
                cursor=cursor_type,
            )
            if click_binding:
                self.dnd_placeholder_label.bind("<Button-1>", click_binding)
            self.dnd_placeholder_label.drop_target_register(DND_FILES)
            self.dnd_placeholder_label.dnd_bind("<<Drop>>", self.handle_drop)
            self.dnd_placeholder_label.grid(
                row=0, column=0, rowspan=2, sticky="nsew", padx=10, pady=10
            )

        elif image is not None and description is not None:
            self.dnd_game_image_label = ctk.CTkLabel(
                self.dnd_frame, text="", image=image
            )
            self.dnd_game_image_label.grid(
                row=0, column=0, pady=(10, 5), padx=10, sticky="n"
            )

            self.dnd_game_desc_textbox = ctk.CTkTextbox(
                self.dnd_frame,
                font=ctk.CTkFont(size=14, weight="bold"),
                text_color="lightgrey",
                wrap="word",
                border_width=0,
                fg_color="transparent",
            )
            self.dnd_game_desc_textbox.grid(
                row=1, column=0, pady=(5, 10), padx=15, sticky="nsew"
            )
            self.dnd_game_desc_textbox.insert("1.0", description)
            self.dnd_game_desc_textbox.configure(state="disabled")
        else:
            self._show_dnd_placeholder()

    def _show_dnd_placeholder(self, text="Drag and drop .lua file here"):
        """Displays the default placeholder text in the DND area."""
        if not self.dnd_frame.winfo_exists():
            return
        self._clear_dnd_area()
        self.dnd_placeholder_label = ctk.CTkLabel(
            self.dnd_frame,
            text=text,
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color="gray",
        )
        self.dnd_placeholder_label.drop_target_register(DND_FILES)
        self.dnd_placeholder_label.dnd_bind("<<Drop>>", self.handle_drop)
        self.dnd_placeholder_label.configure(cursor="")
        self.dnd_placeholder_label.grid(
            row=0, column=0, rowspan=2, sticky="nsew", padx=10, pady=10
        )

    def _fetch_game_info_thread(self, game_id):
        """Fetches game info (image, description) from Steam widget in a background thread."""
        widget_url = f"https://store.steampowered.com/widget/{game_id}/"
        headers = {"User-Agent": "Mozilla/5.0", "Accept-Language": "en-US,en;q=0.5"}
        image_url, description, error_msg, ctk_image = None, None, None, None

        try:
            response = requests.get(
                widget_url, headers=headers, timeout=10, verify=False
            )
            response.raise_for_status()
            soup = BeautifulSoup(response.text, "html.parser")
            desc_div = soup.find("div", class_="desc")

            if desc_div:
                img_tag = desc_div.find("img", class_="capsule")
                if img_tag and img_tag.get("src"):
                    image_url = img_tag["src"]

                link_tag = desc_div.find("a")
                if link_tag:

                    name_span = link_tag.find("span", class_="title")
                    if name_span:
                        description = name_span.get_text(strip=True)
                    else:
                        description = link_tag.get_text(strip=True)

                if not description or len(description) < 5:
                    description = desc_div.get_text(separator=" ", strip=True)
                    if img_tag:
                        img_alt_text = img_tag.get("alt", "")
                        if img_alt_text:
                            description = description.replace(img_alt_text, "").strip()

                if not description:
                    description = f"Game ID: {game_id}"
            else:
                error_msg = f"Game info not found for ID: {game_id}"

            if image_url:
                try:
                    img_response = requests.get(image_url, timeout=10, verify=False)
                    img_response.raise_for_status()
                    pil_image = Image.open(io.BytesIO(img_response.content))
                    target_width = 184
                    scale = target_width / pil_image.width
                    target_height = int(pil_image.height * scale)
                    ctk_image = ctk.CTkImage(
                        light_image=pil_image,
                        dark_image=pil_image,
                        size=(target_width, target_height),
                    )
                except Exception as img_e:
                    print(f"Error downloading/processing image for {game_id}: {img_e}")
                    ctk_image = None

        except requests.exceptions.RequestException as e:
            error_msg = f"Network error fetching game info for {game_id}."
            print(f"{error_msg} Details: {e}")
        except Exception as e:
            error_msg = f"Error parsing game info for {game_id}."
            print(f"{error_msg} Details: {e}")

        try:
            self.after(
                0, self._update_dnd_area_display, ctk_image, description, error_msg
            )
        except tk.TclError:
            print("App window closed before game info update could be scheduled.")

    def _start_fetch_game_info(self, filepath):
        """Reads Lua file, extracts Game ID, and starts fetching game info if ID found."""
        game_id = None
        try:
            if not os.path.isfile(filepath):
                self.after(
                    0,
                    self._update_dnd_area_display,
                    None,
                    None,
                    "Selected file no longer exists.",
                )
                return

            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()
            game_id = get_game_id_from_content(content)

            if game_id:
                self.current_game_id = game_id
                self.after(
                    0,
                    self._update_dnd_area_display,
                    None,
                    None,
                    f"Loading info for Game ID: {game_id}...",
                )
                threading.Thread(
                    target=self._fetch_game_info_thread, args=(game_id,), daemon=True
                ).start()
            else:
                self.current_game_id = None
                self.after(
                    0,
                    self._update_dnd_area_display,
                    None,
                    None,
                    "Could not find Game ID in file.",
                )
        except Exception as e:
            self.current_game_id = None
            self.after(
                0, self._update_dnd_area_display, None, None, f"Error reading file: {e}"
            )

    def _retry_fetch_game_info(self, event=None):
        """Retries fetching game info if a file is currently selected."""
        if self.is_processing:
            return

        filepath = self.selected_file_path.get()
        if not filepath:
            self.update_status("No file selected to refresh info for.", "orange")
            self._show_dnd_placeholder("No file selected.")
            return
        if not os.path.isfile(filepath):
            self.update_status(
                f"Selected file gone: {os.path.basename(filepath)}", "orange"
            )
            self._show_dnd_placeholder("Selected file cannot be found.")
            return

        self.update_status(
            f"Retrying fetch for {os.path.basename(filepath)}...", "lightblue"
        )
        self._start_fetch_game_info(filepath)

    def update_status(self, message, color="white"):
        """Updates the status label text and color on the GUI thread."""

        def _update():
            if hasattr(self, "status_label") and self.status_label.winfo_exists():
                self.status_message.set(message)
                self.status_label.configure(text_color=color)
            if (
                hasattr(self, "output_path_label")
                and self.output_path_label.winfo_exists()
                and "Saved in:" in message
            ):
                try:
                    saved_path = message.split("Saved in: ")[1]
                    if os.path.dirname(saved_path):
                        self.output_folder_path.set(os.path.dirname(saved_path))
                except IndexError:
                    pass

        try:
            self.after(0, _update)
        except tk.TclError:
            print("App window closed, cannot update status.")

    def select_file(self):
        """Opens a dialog to select a .lua file."""
        if self.is_processing:
            return
        filetypes = [("Lua Script", "*.lua"), ("All Files", "*.*")]
        filepath = filedialog.askopenfilename(
            title="Select Lua Manifest File", filetypes=filetypes
        )
        if filepath:
            if filepath.lower().endswith(".lua"):
                self.selected_file_path.set(filepath)
                base_name = os.path.basename(filepath)
                display_text = (
                    f"Selected: {base_name}"
                    if len(base_name) < 50
                    else f"Selected: ...{base_name[-45:]}"
                )
                self.update_status(display_text, "lightblue")
                self._start_fetch_game_info(filepath)
            else:
                messagebox.showerror("Invalid File Type", "Please select a .lua file.")
                self.selected_file_path.set("")
                self.current_game_id = None
                self._show_dnd_placeholder()

    def select_output_folder(self):
        """Opens a dialog to select the output folder."""
        if self.is_processing:
            return
        initial_dir = self.output_folder_path.get()
        if not os.path.isdir(initial_dir):
            initial_dir = os.path.join(os.path.expanduser("~"), "Desktop")
            if not os.path.isdir(initial_dir):
                initial_dir = os.path.expanduser("~")

        folderpath = filedialog.askdirectory(
            title="Select Output Folder", initialdir=initial_dir
        )
        if folderpath:
            self.output_folder_path.set(folderpath)
            self.update_status("Output folder selected", "lightblue")

    def handle_drop(self, event):
        """Handles a file drop event, processing a single .lua file."""
        if self.is_processing:
            return
        filepaths_str = event.data.strip()

        filepath = (
            filepaths_str[1:-1]
            if filepaths_str.startswith("{") and filepaths_str.endswith("}")
            else filepaths_str
        )

        if os.path.isfile(filepath) and filepath.lower().endswith(".lua"):
            self.selected_file_path.set(filepath)
            base_name = os.path.basename(filepath)
            display_text = (
                f"Selected: {base_name}"
                if len(base_name) < 50
                else f"Selected: ...{base_name[-45:]}"
            )
            self.update_status(display_text, "lightblue")
            self._start_fetch_game_info(filepath)
        elif os.path.isfile(filepath):
            messagebox.showerror(
                "Invalid File Type",
                f"Dropped file is not a .lua file:\n{os.path.basename(filepath)}",
            )
            self.selected_file_path.set("")
            self.current_game_id = None
            self._show_dnd_placeholder()
        else:
            messagebox.showwarning(
                "Drop Error",
                "Could not process dropped item.\nPlease drop a single .lua file.",
            )
            self.selected_file_path.set("")
            self.current_game_id = None
            self._show_dnd_placeholder()

    def join_telegram(self):
        """Opens the Telegram link in a web browser."""
        try:
            webbrowser.open_new_tab(TELEGRAM_LINK)
            self.update_status("Opening Telegram link...", "lightblue")
        except Exception as e:
            self.update_status(f"Error opening Telegram link: {e}", "red")
            messagebox.showerror("Error", f"Could not open Telegram link:\n{e}")

    def set_processing_state(self, processing):
        """Enables or disables UI elements based on processing state."""
        self.is_processing = processing
        state = "disabled" if processing else "normal"

        widgets_to_toggle = [
            self.select_file_button,
            self.browse_button,
            self.update_button,
            self.repo_dropdown,
        ]

        try:
            dnd_target = self.dnd_frame
            placeholder_target = self.dnd_placeholder_label
            if processing:
                if dnd_target and dnd_target.winfo_exists():
                    dnd_target.drop_target_unregister()
                if placeholder_target and placeholder_target.winfo_exists():
                    placeholder_target.drop_target_unregister()
            else:
                if dnd_target and dnd_target.winfo_exists():
                    dnd_target.drop_target_register(DND_FILES)
                if placeholder_target and placeholder_target.winfo_exists():
                    placeholder_target.drop_target_register(DND_FILES)
        except tk.TclError:
            print("Warning: Error toggling DND registration, window might be closing.")

        for widget in widgets_to_toggle:
            if widget and widget.winfo_exists():
                if widget == self.repo_dropdown:

                    widget.configure(
                        state=(
                            "disabled"
                            if processing or not self.repos_config
                            else "normal"
                        )
                    )
                else:
                    widget.configure(state=state)

        if self.update_button and self.update_button.winfo_exists():
            self.update_button.configure(
                text="Processing..." if processing else "Update"
            )

    def start_update_process(self):
        """Initiates the manifest update process in a new thread."""
        if self.is_processing:
            return

        original_lua_path = self.selected_file_path.get()
        output_dir = self.output_folder_path.get()

        if not original_lua_path:
            messagebox.showerror(
                "Input Missing", "Please select or drop a .lua file first."
            )
            return
        if not os.path.isfile(original_lua_path):
            messagebox.showerror(
                "Input Error", f"Selected file does not exist:\n{original_lua_path}"
            )
            self.selected_file_path.set("")
            self._show_dnd_placeholder()
            return

        if not output_dir:
            if self.default_output_dir:
                output_dir = self.default_output_dir
                self.output_folder_path.set(output_dir)
                self.update_status(f"Using default output: {output_dir}", "lightblue")
            else:
                messagebox.showerror(
                    "Output Missing", "Please select an output folder."
                )
                return
        try:
            os.makedirs(output_dir, exist_ok=True)
        except OSError as e:
            messagebox.showerror(
                "Output Error", f"Could not create output directory:\n{output_dir}\n{e}"
            )
            return

        self.set_processing_state(True)
        self.update_status("Starting update process...", "lightblue")

        threading.Thread(
            target=self._update_thread_target,
            args=(original_lua_path, output_dir),
            daemon=True,
        ).start()

    def _update_thread_target(self, original_lua_path, output_base_dir):
        """Core logic for updating manifests, run in a background thread."""
        game_id = None

        temp_base_dir = os.path.join(
            os.getenv("TEMP", "/tmp"),
            f"lua_manifest_updater_{os.getpid()}_{int(time.time())}",
        )
        temp_extract_dir, downloaded_zip_path, temp_updated_lua_path, final_zip_path = (
            None,
            None,
            None,
            None,
        )
        extracted_manifest_paths = []
        success = False
        final_save_path = ""

        try:
            self.update_status(
                f"Reading file: {os.path.basename(original_lua_path)}", "orange"
            )
            try:
                if not os.path.isfile(original_lua_path):
                    self.update_status(
                        f"Error: Input file disappeared: {os.path.basename(original_lua_path)}",
                        "red",
                    )
                    return
                with open(original_lua_path, "r", encoding="utf-8") as f:
                    content = f.read()
                game_id = get_game_id_from_content(content)
                if not game_id:
                    self.update_status(
                        "Error: Game ID not found in the Lua file.", "red"
                    )
                    return
                self.update_status(f"Found Game ID: {game_id}", "lightblue")
            except Exception as e:
                self.update_status(f"Error reading input Lua file: {e}", "red")
                return

            temp_extract_dir = os.path.join(temp_base_dir, f"extracted_{game_id}")
            downloaded_zip_path = os.path.join(
                temp_base_dir, f"downloaded_{game_id}.zip"
            )
            final_zip_name = f"{game_id}.zip"
            final_zip_path = os.path.join(output_base_dir, final_zip_name)
            final_save_path = final_zip_path

            if os.path.exists(temp_base_dir):
                delete_item(temp_base_dir)
            os.makedirs(temp_base_dir, exist_ok=True)
            os.makedirs(temp_extract_dir, exist_ok=True)

            selected_repo_display_name = self.selected_repo_key.get()
            repo_path_to_use = self.repos_config.get(
                selected_repo_display_name, "Fairyvmos/BlankTMing"
            )

            url = f"https://github.com/{repo_path_to_use}/archive/refs/heads/{game_id}.zip"
            self.update_status(
                f"Using repo: {repo_path_to_use} for branch {game_id}", "lightblue"
            )

            if not download_file(url, downloaded_zip_path, self.update_status):

                self.update_status(
                    f"Download from GitHub ({repo_path_to_use}, branch {game_id}) failed.",
                    "red",
                )

                return

            extracted_manifest_paths = extract_files_gui(
                downloaded_zip_path, temp_extract_dir, self.update_status
            )
            if extracted_manifest_paths is None:
                return

            if not extracted_manifest_paths:
                self.update_status(
                    "No manifest files found in the archive to process.", "orange"
                )

            temp_updated_lua_path = update_lua_file_gui(
                original_lua_path,
                extracted_manifest_paths,
                game_id,
                temp_base_dir,
                self.update_status,
            )
            if not temp_updated_lua_path:
                return

            if not zip_files_gui(
                final_zip_path,
                temp_updated_lua_path,
                game_id,
                extracted_manifest_paths,
                self.update_status,
            ):
                return

            success = True

        except Exception as e:
            self.update_status(f"An unexpected error occurred: {e}", "red")
            import traceback

            traceback.print_exc()
            success = False
        finally:
            self.update_status("Cleaning up temporary files...", "gray")
            time.sleep(0.1)
            if temp_base_dir and os.path.exists(temp_base_dir):
                delete_item(temp_base_dir)

            final_msg = (
                f"Process completed successfully!\nSaved in: {final_save_path}"
                if success
                else "Update process failed. Check messages for errors."
            )
            final_color = "lime" if success else "red"

            if not success and (
                "Error" in self.status_message.get()
                or "failed" in self.status_message.get()
            ):
                final_msg = self.status_message.get()

            try:
                self.after(0, lambda: self.update_status(final_msg, final_color))
                self.current_game_id = None
                self.after(100, lambda: self.set_processing_state(False))
            except tk.TclError:
                print("App window closed, final UI updates skipped.")


if __name__ == "__main__":
    try:

        root_test = TkinterDnD.Tk()
        root_test.withdraw()
        label_test = tk.Label(root_test, text="TestDND")
        label_test.drop_target_register(DND_FILES)

        root_test.destroy()
    except Exception as e:
        print(f"Critical Error: Failed to initialize TkinterDnD: {e}")
        print(
            "This usually means 'python-tkdnd2' is not installed correctly or its dependencies are missing."
        )

        root_err = tk.Tk()
        root_err.withdraw()
        messagebox.showerror(
            "Dependency Error",
            "Failed to load Drag and Drop library (TkinterDnD).\n"
            "Please ensure 'python-tkdnd2' is installed correctly for your Python environment.\n"
            "The application will now close.",
        )
        root_err.destroy()
        sys.exit(1)

    app = App()
    app.mainloop()

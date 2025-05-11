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
APP_VERSION = "1.0.2"
WINDOW_WIDTH = 550
WINDOW_HEIGHT = 830
DEFAULT_OUTPUT_SUBDIR = "Updated Files"
TELEGRAM_LINK = "https://t.me/FairyRoot"


def _get_depot_manifest_ids_from_steamui(game_id, status_callback):
    """Fetches depot_id and manifest_gid pairs from steamui.com for a given game_id."""
    status_callback(
        f"Special Mode: Fetching manifest list for Game ID {game_id}...", "yellow"
    )
    url = f"https://steamui.com/get_appinfo.php?appid={game_id}"
    reponse_text = None
    depotid_manifestid_list = []

    try:
        reponse = requests.get(url, timeout=15)
        reponse.raise_for_status()
        reponse_text = reponse.text
    except requests.exceptions.Timeout:
        status_callback(
            f"Special Mode Error: Request timed out for game ID {game_id}.", "red"
        )
        return []
    except requests.exceptions.HTTPError as http_err:
        status_callback(
            f"Special Mode Error: HTTP error for game ID {game_id}: {http_err}", "red"
        )
        return []
    except requests.exceptions.RequestException as req_err:
        status_callback(
            f"Special Mode Error: Request error for game ID {game_id}: {req_err}", "red"
        )
        return []

    if not reponse_text or not reponse_text.strip():
        status_callback(
            f"Special Mode Warning: Empty reponse for game ID {game_id}.", "orange"
        )
        return []

    pattern_std = r'"(?P<depotid>\d+)"\s*\{\s*"manifests"\s*\{\s*"public"\s*\{\s*"gid"\s*"(?P<manifestgid>\d+)"'

    pattern_dlc = r'"(?P<depotid_dlc>\d+)"\s*\{\s*"dlcappid"\s*"(?P<dlcappid>\d+)"\s*"manifests"\s*\{\s*"public"\s*\{\s*"gid"\s*"(?P<manifestgid_dlc>\d+)"'

    matches_std = re.finditer(pattern_std, reponse_text)
    for match in matches_std:
        depotid = match.group("depotid")
        manifestgid = match.group("manifestgid")
        depotid_manifestid_list.append((depotid, manifestgid))

    matches_dlc = re.finditer(pattern_dlc, reponse_text)
    for match in matches_dlc:
        depotid = match.group("depotid_dlc")
        manifestgid = match.group("manifestgid_dlc")
        depotid_manifestid_list.append((depotid, manifestgid))

    if not depotid_manifestid_list:
        status_callback(
            f"Special Mode: No depot/manifest IDs found for Game ID {game_id}.",
            "orange",
        )
    else:
        status_callback(
            f"Special Mode: Found {len(depotid_manifestid_list)} manifest(s) to download for Game ID {game_id}.",
            "lightblue",
        )
    return depotid_manifestid_list


def get_game_id_from_content(content):
    """Extracts game ID from manifest content."""
    match = re.search(r'addappid\s*\(\s*(\d+|"(\d+)")', content)
    if match:
        game_id = match.group(2) if match.group(2) else match.group(1)
        return game_id
    else:
        return None


def download_file(url, filename, status_callback):
    """Downloads a file, updating status via callback."""
    try:
        status_callback(f"Downloading: {os.path.basename(filename)}...", "orange")
        reponse = requests.get(url, verify=False, stream=True, timeout=30)
        reponse.raise_for_status()
        with open(filename, "wb") as f:
            for chunk in reponse.iter_content(chunk_size=8192):
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
        status_callback(f"Error downloading file: {e}", "red")
        return False
    except Exception as e:
        status_callback(f"Error during download: {e}", "red")
        return False


def extract_files_gui(filename, extract_dir, status_callback):
    """Extracts manifest files, updating status via callback."""
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
    """Deletes a file or directory, without status updates."""
    try:
        if os.path.exists(item_path):
            if os.path.isfile(item_path):
                os.remove(item_path)
            elif os.path.isdir(item_path):
                shutil.rmtree(item_path)
            return True
        return False
    except Exception as e:
        print(f"Warn: Error deleting {os.path.basename(item_path)}: {e}")
        return False


def update_lua_file_gui(
    original_lua_path, extracted_manifest_paths, game_id, temp_dir, status_callback
):
    """Updates the lua file content based on extracted manifest IDs."""
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
    """Zips the updated lua and extracted manifests."""
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
                    f"Error: Temporary updated Lua file not found for zipping.", "red"
                )
                return False

            manifest_added = False
            for manifest_path in extracted_manifest_paths:
                if os.path.exists(manifest_path):
                    zip_ref.write(manifest_path, os.path.basename(manifest_path))
                    manifest_added = True

            if not manifest_added:
                status_callback(
                    "Warning: No extracted .manifest files were added to the zip.",
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
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.selected_file_path = ctk.StringVar()
        self.repos_config = {}
        self.selected_repo_key = ctk.StringVar()
        self.special_mode_var = ctk.BooleanVar(value=True)

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
        self.configure(bg="#2E2E2E")
        self.resizable(False, False)

        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self.main_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.main_frame.pack(pady=20, padx=40, fill="both", expand=True)

        self.header_frame = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        self.header_frame.pack(pady=(10, 15), fill="x")

        try:
            img_path = "imgs/FairyRoot.png"
            original_image = Image.open(img_path).convert("RGBA")
            size = (100, 100)

            mask = Image.new("L", size, 0)
            draw = ImageDraw.Draw(mask)
            draw.ellipse((0, 0) + size, fill=255)

            masked_image = ImageOps.fit(original_image, size, centering=(0.5, 0.5))
            masked_image.putalpha(mask)

            self.fairyroot_image = CTkImage(
                light_image=masked_image, dark_image=masked_image, size=size
            )

            self.image_label = ctk.CTkLabel(
                self.header_frame, text="", image=self.fairyroot_image
            )
            self.image_label.pack(side="left", padx=(0, 15))

        except FileNotFoundError:
            print(f"Warning: Header image not found at {img_path}")
            self.image_label = ctk.CTkLabel(
                self.header_frame, text="[IMG]", width=size[0], height=size[1]
            )
            self.image_label.pack(side="left", padx=(0, 15))
        except Exception as e:
            print(f"Error loading header image: {e}")
            self.image_label = ctk.CTkLabel(
                self.header_frame, text="[ERR]", width=size[0], height=size[1]
            )
            self.image_label.pack(side="left", padx=(0, 15))

        self.text_frame = ctk.CTkFrame(self.header_frame, fg_color="transparent")
        self.text_frame.pack(side="left", fill="x", expand=True)

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
            font=ctk.CTkFont(size=18),
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

        self.select_prompt_label = ctk.CTkLabel(
            self.main_frame,
            text="Select a lua file or drag and drop it",
            text_color="gray",
        )
        self.select_prompt_label.pack(pady=(10, 5))

        self.select_file_button = ctk.CTkButton(
            self.main_frame,
            text="Select File",
            command=self.select_file,
            width=200,
            height=40,
            font=ctk.CTkFont(size=14),
        )
        self.select_file_button.pack(pady=5)

        self.repo_label = ctk.CTkLabel(
            self.main_frame, text="Select Repository:", text_color="gray"
        )
        self.repo_label.pack(pady=(10, 0))

        dropdown_values = (
            list(self.repos_config.keys()) if self.repos_config else ["N/A"]
        )
        self.repo_dropdown = ctk.CTkOptionMenu(
            self.main_frame,
            variable=self.selected_repo_key,
            values=dropdown_values,
            command=self.on_repo_select,
            width=200,
            height=40,
            font=ctk.CTkFont(size=14),
        )
        if not self.repos_config:
            self.repo_dropdown.set("N/A")
            self.repo_dropdown.configure(state="disabled")
        elif self.special_mode_var.get():
            self.repo_dropdown.configure(state="disabled")

        self.repo_dropdown.pack(pady=5)

        self.special_mode_checkbox = ctk.CTkCheckBox(
            self.main_frame,
            text="Special Mode (Direct Manifest Download)",
            variable=self.special_mode_var,
            command=self._on_toggle_special_mode,
            font=ctk.CTkFont(size=12),
        )
        self.special_mode_checkbox.pack(pady=(5, 10))

        self.output_center_frame = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        self.output_center_frame.pack(pady=(15, 5), fill="x")

        self.output_inner_frame = ctk.CTkFrame(
            self.output_center_frame, fg_color="transparent"
        )
        self.output_inner_frame.pack(anchor="center")

        self.output_label = ctk.CTkLabel(
            self.output_inner_frame,
            text="Output Folder:",
            text_color="gray",
            anchor="w",
        )
        self.output_label.pack(side="left", padx=(0, 10))

        self.browse_button = ctk.CTkButton(
            self.output_inner_frame,
            text="Browse",
            command=self.select_output_folder,
            width=100,
            height=30,
        )
        self.browse_button.pack(side="left")

        self.output_path_label = ctk.CTkLabel(
            self.main_frame,
            textvariable=self.output_folder_path,
            text_color="green",
            wraplength=WINDOW_WIDTH - 60,
            anchor="center",
            justify="center",
            font=ctk.CTkFont(size=11),
        )
        self.output_path_label.pack(pady=(0, 15), fill="x")

        self.update_button = ctk.CTkButton(
            self.main_frame,
            text="Update",
            command=self.start_update_process,
            width=200,
            height=45,
            font=ctk.CTkFont(size=16, weight="bold"),
        )
        self.update_button.pack(pady=5)

        self.telegram_button = ctk.CTkButton(
            self.main_frame,
            text="Telegram",
            command=self.join_telegram,
            width=200,
            height=45,
            font=ctk.CTkFont(size=16),
        )
        self.telegram_button.pack(pady=5)

        self.status_label = ctk.CTkLabel(
            self.main_frame,
            textvariable=self.status_message,
            wraplength=WINDOW_WIDTH - 60,
            font=ctk.CTkFont(size=12),
            text_color="lightgreen",
        )
        self.status_label.pack(pady=(10, 5))

        self.dnd_frame = ctk.CTkFrame(
            self.main_frame,
            border_width=2,
            border_color="#5D5FEF",
            fg_color="#333333",
            corner_radius=15,
        )
        self.dnd_frame.pack(pady=(5, 10), fill="both", expand=True)
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
        """Loads repository configuration from repo.json."""
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

            for name, path in self.repos_config.items():
                if path == default_repo_path_target:
                    key_to_select_by_default = name
                    break

            if not key_to_select_by_default:

                if default_repo_path_target not in self.repos_config:
                    self.repos_config[default_repo_path_target] = (
                        default_repo_path_target
                    )

                key_to_select_by_default = default_repo_path_target

        except FileNotFoundError:
            if hasattr(self, "update_status"):
                self.update_status("repo.json not found. Creating default.", "orange")

            default_data_to_write = {"FairyRoot": "Fairyvmos/BlankTMing"}
            try:
                with open("repo.json", "w", encoding="utf-8") as f:
                    json.dump(default_data_to_write, f, indent=4)

                self.repos_config = {"FairyRoot": "Fairyvmos/BlankTMing"}
                key_to_select_by_default = "FairyRoot"
            except Exception as e_write:
                if hasattr(self, "update_status"):
                    self.update_status(f"Error creating repo.json: {e_write}", "red")

                self.repos_config = {"Fallback_Default": "Fairyvmos/BlankTMing"}
                key_to_select_by_default = "Fallback_Default"

        except json.JSONDecodeError:
            if hasattr(self, "update_status"):
                self.update_status("Error decoding repo.json. Using fallback.", "red")
            self.repos_config = {"Fallback_JsonError": "Fairyvmos/BlankTMing"}
            key_to_select_by_default = "Fallback_JsonError"
        except Exception as e:
            if hasattr(self, "update_status"):
                self.update_status(f"Error loading repos: {e}", "red")
            self.repos_config = {"Fallback_GeneralError": "Fairyvmos/BlankTMing"}
            key_to_select_by_default = "Fallback_GeneralError"

        if key_to_select_by_default and key_to_select_by_default in self.repos_config:
            self.selected_repo_key.set(key_to_select_by_default)
        elif self.repos_config:
            self.selected_repo_key.set(list(self.repos_config.keys())[0])
        else:
            self.selected_repo_key.set("N/A")

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
        """Handles repository selection change."""
        repo_path = self.repos_config.get(selected_display_name)
        if repo_path:
            if hasattr(self, "update_status"):
                self.update_status(f"Repository: {selected_display_name}", "lightblue")
        else:
            if hasattr(self, "update_status"):
                self.update_status(
                    f"Unknown repository: {selected_display_name}", "orange"
                )

    def _on_toggle_special_mode(self):
        """Handles the special mode checkbox toggle."""
        if self.special_mode_var.get():
            self.repo_dropdown.configure(state="disabled")
            if hasattr(self, "update_status"):
                self.update_status(
                    "Special Mode Activated: Repository dropdown disabled.", "yellow"
                )
        else:
            self.repo_dropdown.configure(state="normal")
            if hasattr(self, "update_status"):
                self.update_status(
                    "Special Mode Deactivated: Repository dropdown enabled.",
                    "lightblue",
                )

            if (
                self.selected_repo_key.get()
                and self.selected_repo_key.get() in self.repos_config
            ):
                self.repo_dropdown.set(self.selected_repo_key.get())
            elif self.repos_config:
                self.repo_dropdown.set(list(self.repos_config.keys())[0])
            else:
                self.repo_dropdown.set("N/A")

    def _clear_dnd_area(self):
        """Removes existing widgets from the DND frame."""
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
        Uses CTkTextbox for description (scrollable if needed).
        Only adds refresh clickability for actual errors.
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
            is_actual_error = (
                "error" in error_message.lower()
                or "could not find" in error_message.lower()
                or "failed" in error_message.lower()
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
        """Fetches game info from Steam widget in a background thread."""
        widget_url = f"https://store.steampowered.com/widget/{game_id}/"
        headers = {
            "Host": "store.steampowered.com",
            "Sec-Ch-Ua": "Chromium;v=135, Not-A.Brand;v=8",
            "Sec-Ch-Ua-Mobile": "?0",
            "Sec-Ch-Ua-Platform": "Windows",
            "Accept-Language": "en-US,en;q=0.9",
            "Upgrade-Insecure-Requests": "1",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
            "Sec-Fetch-Site": "cross-site",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-User": "?1",
            "Sec-Fetch-Dest": "iframe",
            "Sec-Fetch-Storage-Access": "active",
            "Referer": "https://steamui.com/",
            "Accept-Encoding": "gzip, deflate, br",
            "Priority": "u=0, i",
            "Connection": "keep-alive",
        }
        image_url = None
        description = None
        error_msg = None
        ctk_image = None

        try:
            reponse = requests.get(
                widget_url, headers=headers, timeout=10, verify=False
            )
            reponse.raise_for_status()
            soup = BeautifulSoup(reponse.text, "html.parser")
            desc_div = soup.find("div", class_="desc")

            if desc_div:
                img_tag = desc_div.find("img", class_="capsule")
                if img_tag and img_tag.get("src"):
                    image_url = img_tag["src"]
                link_tag = desc_div.find("a")
                if link_tag:
                    desc_text_nodes = link_tag.find_next_siblings(string=True)
                    description = "".join(
                        node.strip() for node in desc_text_nodes
                    ).strip()
                    if not description:
                        description = link_tag.get_text(strip=True)
                elif not description:
                    description = desc_div.get_text(separator=" ", strip=True)
                    if img_tag:
                        img_text_pattern = re.escape(img_tag.get_text(strip=True))
                        if img_text_pattern:
                            description = re.sub(
                                r"\s*" + img_text_pattern + r"\s*", " ", description
                            ).strip()

                if not description:
                    description = f"Game ID: {game_id}"

            else:
                error_msg = f"Game info not found for ID: {game_id}"

            if image_url:
                try:
                    img_reponse = requests.get(image_url, timeout=10, verify=False)
                    img_reponse.raise_for_status()
                    pil_image = Image.open(io.BytesIO(img_reponse.content))
                    target_width = 184
                    scale = target_width / pil_image.width
                    target_height = int(pil_image.height * scale)
                    ctk_image = ctk.CTkImage(
                        light_image=pil_image,
                        dark_image=pil_image,
                        size=(target_width, target_height),
                    )
                except Exception as img_e:
                    print(f"Error downloading/processing image: {img_e}")
                    ctk_image = None

        except requests.exceptions.RequestException as e:
            print(f"Network error fetching game info: {e}")
            error_msg = "Network error fetching game info."
        except Exception as e:
            print(f"Error parsing game info: {e}")
            error_msg = "Error parsing game info."

        try:
            self.after(
                0, self._update_dnd_area_display, ctk_image, description, error_msg
            )
        except tk.TclError:
            print("App closed before game info update could be scheduled.")

    def _start_fetch_game_info(self, filepath):
        """Reads file, gets ID, and starts the fetch thread."""
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
                thread = threading.Thread(
                    target=self._fetch_game_info_thread, args=(game_id,), daemon=True
                )
                thread.start()
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
        """Handles the click event on the error message to retry fetching."""
        if self.is_processing:
            print("Main update process is running, cannot fetch game info now.")
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
            print("App closed before status update could be scheduled.")

    def select_file(self):
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
        if self.is_processing:
            return
        filepaths_str = event.data.strip()
        if filepaths_str.startswith("{") and filepaths_str.endswith("}"):
            filepath = filepaths_str[1:-1]
        else:
            filepath = filepaths_str

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
        try:
            webbrowser.open_new_tab(TELEGRAM_LINK)
            self.update_status("Opening Telegram link...", "lightblue")
        except Exception as e:
            self.update_status(f"Error opening Telegram link: {e}", "red")
            messagebox.showerror("Error", f"Could not open Telegram link:\n{e}")

    def set_processing_state(self, processing):
        self.is_processing = processing
        state = "disabled" if processing else "normal"
        widgets_to_toggle = [
            getattr(self, "select_file_button", None),
            getattr(self, "browse_button", None),
            getattr(self, "update_button", None),
            getattr(self, "repo_dropdown", None),
            getattr(self, "special_mode_checkbox", None),
        ]
        try:
            if processing:
                if hasattr(self, "dnd_frame") and self.dnd_frame.winfo_exists():
                    self.dnd_frame.drop_target_unregister()
                if (
                    hasattr(self, "dnd_placeholder_label")
                    and self.dnd_placeholder_label
                    and self.dnd_placeholder_label.winfo_exists()
                ):
                    self.dnd_placeholder_label.drop_target_unregister()
            else:
                if hasattr(self, "dnd_frame") and self.dnd_frame.winfo_exists():
                    self.dnd_frame.drop_target_register(DND_FILES)
                if (
                    hasattr(self, "dnd_placeholder_label")
                    and self.dnd_placeholder_label
                    and self.dnd_placeholder_label.winfo_exists()
                ):
                    self.dnd_placeholder_label.drop_target_register(DND_FILES)
        except tk.TclError:
            print("Warning: Error toggling drop target registration.")

        for widget in widgets_to_toggle:
            if widget and widget.winfo_exists():

                if (
                    widget == self.repo_dropdown
                    and state == "normal"
                    and self.special_mode_var.get()
                ):
                    widget.configure(state="disabled")
                else:
                    widget.configure(state=state)

        update_button = getattr(self, "update_button", None)
        if update_button and update_button.winfo_exists():
            update_button.configure(text="Processing..." if processing else "Update")

    def start_update_process(self):
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
                messagebox.showerror("Input Missing", "Please select an output folder.")
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

        thread = threading.Thread(
            target=self._update_thread_target,
            args=(original_lua_path, output_dir),
            daemon=True,
        )
        thread.start()

    def _update_thread_target(self, original_lua_path, output_base_dir):
        """The actual update logic run in the background thread."""
        game_id = None
        temp_base_dir = os.path.join(
            os.getenv("TEMP", "/tmp"), f"luaandstmanifest_updater_{os.getpid()}"
        )
        temp_extract_dir = None
        downloaded_zip_path = None
        temp_updated_lua_path = None
        final_zip_path = None
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
                        f"Error: Input file disappeared during processing: {os.path.basename(original_lua_path)}",
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
                self.update_status(
                    f"Error reading input Lua file during update: {e}", "red"
                )
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

            if self.special_mode_var.get():
                depot_manifest_pairs = _get_depot_manifest_ids_from_steamui(
                    game_id, self.update_status
                )
                if not depot_manifest_pairs:
                    self.update_status(
                        f"Special Mode: No manifest data found for Game ID {game_id}. Cannot proceed.",
                        "red",
                    )
                    return

                extracted_manifest_paths = []
                total_manifests_to_download = len(depot_manifest_pairs)
                download_count = 0

                for idx, (depotid, manifestgid) in enumerate(depot_manifest_pairs):
                    manifest_filename = f"{depotid}_{manifestgid}.manifest"
                    self.update_status(
                        f"Special Mode: Downloading manifest {idx+1}/{total_manifests_to_download}: {manifest_filename}...",
                        "yellow",
                    )

                    special_mode_url = f"https://raw.githubusercontent.com/qwe213312/k25FCdfEOoEJ42S6/main/{manifest_filename}"
                    downloaded_manifest_path = os.path.join(
                        temp_extract_dir, manifest_filename
                    )

                    if download_file(
                        special_mode_url, downloaded_manifest_path, self.update_status
                    ):
                        if os.path.exists(downloaded_manifest_path):
                            extracted_manifest_paths.append(downloaded_manifest_path)
                            download_count += 1
                        else:
                            self.update_status(
                                f"Special Mode: Downloaded {manifest_filename} but file not found.",
                                "red",
                            )
                    else:
                        self.update_status(
                            f"Special Mode: Failed to download {manifest_filename}.",
                            "orange",
                        )

                if download_count == 0 and total_manifests_to_download > 0:
                    self.update_status(
                        f"Special Mode: Failed to download any manifests for Game ID {game_id}.",
                        "red",
                    )
                    return
                elif download_count < total_manifests_to_download:
                    self.update_status(
                        f"Special Mode: Successfully downloaded {download_count}/{total_manifests_to_download} manifests.",
                        "yellow",
                    )
                else:
                    self.update_status(
                        f"Special Mode: Successfully downloaded all {download_count} manifests.",
                        "lightgreen",
                    )

            else:
                selected_repo_display_name = self.selected_repo_key.get()
                repo_path_to_use = self.repos_config.get(
                    selected_repo_display_name, "Fairyvmos/BlankTMing"
                )
                url = f"https://github.com/{repo_path_to_use}/archive/refs/heads/{game_id}.zip"
                self.update_status(
                    f"Using repo: {repo_path_to_use} for {game_id}.zip", "lightblue"
                )

                if not download_file(url, downloaded_zip_path, self.update_status):
                    self.update_status(
                        f"Download from {repo_path_to_use} failed, trying proxy for {game_id}.zip...",
                        "orange",
                    )
                    proxy_url = url
                    if not download_file(
                        proxy_url, downloaded_zip_path, self.update_status
                    ):
                        return

                extracted_manifest_paths = extract_files_gui(
                    downloaded_zip_path, temp_extract_dir, self.update_status
                )
                if extracted_manifest_paths is None:
                    return

            if not extracted_manifest_paths:
                self.update_status("No manifest files to process.", "red")
                return

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
            self.update_status(
                f"An unexpected error occurred during update: {e}", "red"
            )
            success = False

        finally:
            self.update_status("Cleaning up temporary files...", "gray")
            time.sleep(0.5)
            if temp_base_dir and os.path.exists(temp_base_dir):
                delete_item(temp_base_dir)

            if success:
                final_msg = (
                    f"Process completed successfully!\nSaved in: {final_save_path}"
                )
                final_color = "lime"
            else:
                current_status = self.status_message.get()
                if "Error" not in current_status and "failed" not in current_status:
                    final_msg = "Update process failed."
                    final_color = "red"
                else:
                    final_msg = current_status
                    final_color = "red"

            try:
                self.after(0, lambda: self.update_status(final_msg, final_color))
                self.current_game_id = None
                self.after(100, lambda: self.set_processing_state(False))
            except tk.TclError:
                print(
                    "App closed before final status update or state reset could be scheduled."
                )


if __name__ == "__main__":
    try:
        root_test = TkinterDnD.Tk()
        label_test = tk.Label(root_test, text="Test")
        label_test.pack()
        label_test.drop_target_register(DND_FILES)
        label_test.dnd_bind("<<Drop>>", lambda e: None)
        root_test.destroy()
    except Exception as e:
        print(f"Error initializing TkinterDnD: {e}")
        print(
            "Please ensure 'python-tkdnd2' is installed correctly for your environment."
        )
        root_err = tk.Tk()
        root_err.withdraw()
        messagebox.showerror(
            "Dependency Error",
            "Failed to load Drag and Drop library (TkinterDnD).\nPlease ensure 'python-tkdnd2' is installed correctly.\nThe application will now close.",
        )
        root_err.destroy()
        sys.exit(1)

    app = App()
    app.mainloop()

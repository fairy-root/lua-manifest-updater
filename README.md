# Lua Manifest Updater (LMU)

<div align="center">
  <img src="imgs/app.png" alt="LMU Logo" width="128" height="128">
</div>

**Lua Manifest Updater (LMU)** is a feature-rich tool for update Lua files with the latest manifest IDs for Steam games.

<div align="center">
  <img src="imgs/preview.png" alt="LMU Preview">
</div>


**Note**: download the lua manifests using this tool
[Steam Depot Online](https://github.com/fairy-root/steam-depot-online)

## Features

*   **File Input:** Select `.lua` files via a file dialog or drag-and-drop.
*   **Game ID Extraction:** Automatically extracts the Steam Game ID from the selected `.lua` file.
*   **Steam Game Info:** Fetches and displays the game's capsule image and description based on the extracted Game ID. Includes a retry option on fetch errors.
*   **Repository Selection:**
    *   Allows selection of different source repositories for game manifests via a dropdown menu.
    *   The dropdown is populated from a `repo.json` configuration file (see Configuration section).
    *   The "default" repository path specified in `repo.json` is selected by default in standard mode.
*   **Standard Mode Manifest Download:**
    *   Downloads the latest manifest archive (`.zip`) for the specific game ID from the selected repository (with a proxy fallback).
    *   Extracts `.manifest` files from the downloaded archive.
*   **Special Mode (Direct Manifest Download):**
    *   Activated by a checkbox, which is **enabled by default**.
    *   When active, the repository dropdown is disabled.
    *   Fetches a list of all `depotid` and `manifestid` pairs for the given `game_id`.
    *   Attempts to download each manifest file (named `{depotid}_{manifestid}.manifest`).
*   **Lua File Update:** Updates the manifest IDs within the provided `.lua` file using the information from the obtained manifests (either extracted from a zip in standard mode or downloaded directly in special mode).
*   **Output Generation:** Creates a new `.zip` archive containing the updated `.lua` file (renamed to `<game_id>.lua`) and the relevant `.manifest` files.
*   **Custom Output:** Allows specifying a custom output directory (defaults to `Updated Files` on the Desktop).
*   **User-Friendly Interface:** Provides clear status updates and error messages throughout the process via GUI.
*   **Error Handling:** Manages potential issues like invalid file types, network errors during download, problems during extraction, or missing Game IDs.

---

## Installation

### Clone the Repository

```bash
git clone https://github.com/fairy-root/lua-manifest-updater.git
cd lua-manifest-updater
```

### Prerequisites

1. Install Python 3.8 or higher.
2. Install the required dependencies:

   ```bash
   pip install -r requirements.txt
   ```

---

## Configuration

The application uses a `repo.json` file in its root directory to manage repository sources for manifest downloads in Standard Mode.

**`repo.json` Structure:**

```json
{
  "FairyRoot": "Fairyvmos/BlankTMing",
  "AnotherRepoName": "username/another-repo",
  "YetAnother": "someuser/some-repo"
}
```

*   `"default"`: (Required) Specifies the default repository path (e.g., `"username/repository"`) to be used. The application will attempt to select a key from the list that matches this path. If no direct key matches this path, this path itself will be added as an option and selected.
*   Other keys (e.g., `"AnotherRepoName"`, `"YetAnother"`): These are user-defined names that will appear in the repository selection dropdown. The value is the GitHub repository path (`"username/repository"`).

If `repo.json` is not found, a default one will be created:
```json
{
  "FairyRoot": "Fairyvmos/BlankTMing"
}
```

---

## Usage

**Run the Tool**:

   ```bash
   python app.py
   ```

1.  **Select Lua/St File**: Use the "Select File" button or drag and drop your `.lua` file onto the designated area. The application will attempt to extract the Game ID and display game information.
2.  **Choose Operating Mode**:
    *   **Special Mode (Default)**: The "Special Mode (Direct Manifest Download)" checkbox is enabled by default. In this mode, manifests are fetched directly based on `depot_id` and `manifest_id` and downloaded from a dedicated repository. The repository dropdown will be disabled.
    *   **Standard Mode**: Uncheck the "Special Mode" checkbox. The repository dropdown will become active. Select your desired source repository from the dropdown. Manifests will be downloaded as a zip archive from this selected repository.
3.  **Select Output Folder**: (Optional) Click "Browse" to choose a custom folder for the updated files. Defaults to `Updated Files` on your Desktop.
4.  **Update**: Click the "Update" button to start the process.
5.  Follow the status messages for progress and any errors.

---

## Notes

USE a **VPN** if the download is failing.

---

## Donation

Your support is appreciated:

- **USDt (TRC20)**: `TGCVbSSJbwL5nyXqMuKY839LJ5q5ygn2uS`
- **BTC**: `13GS1ixn2uQAmFQkte6qA5p1MQtMXre6MT`
- **ETH (ERC20)**: `0xdbc7a7dafbb333773a5866ccf7a74da15ee654cc`
- **LTC**: `Ldb6SDxUMEdYQQfRhSA3zi4dCUtfUdsPou`

## Author

- **GitHub**: [FairyRoot](https://github.com/fairy-root)
- **Telegram**: [@FairyRoot](https://t.me/FairyRoot)

## Contributing

If you would like to contribute to this project, feel free to fork the repository and submit pull requests. Ensure that your code follows the existing structure, and test it thoroughly.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

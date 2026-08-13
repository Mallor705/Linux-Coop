<p align="right">
  <a href="https://github.com/mall0r/Twinverse/blob/main/README.md"><img src="https://img.shields.io/badge/en-US-darkblue.svg" alt="English"/></a>
  <a href="https://github.com/mall0r/Twinverse/blob/main/docs/README.pt-br.md"><img src="https://img.shields.io/badge/pt-BR-darkgreen.svg" alt="Portuguese"/></a>
</p>

<p align="center">
  <img src="https://raw.githubusercontent.com/mall0r/Twinverse/v1.0.0/share/icons/hicolor/scalable/apps/io.github.mall0r.Twinverse.svg" alt="Twinverse Logo" width="176" height="176">
</p>

<p align="center">
  <a href="https://github.com/mall0r/Twinverse/releases"><img src="https://img.shields.io/badge/Version-1.0.0-blue.svg" alt="Version"/></a>
  <a href="https://github.com/mall0r/Twinverse/blob/main/LICENSE"><img src="https://img.shields.io/badge/License-GPL--3.0-green.svg" alt="License"/></a>
  <a href="https://www.gtk.org/"><img src="https://img.shields.io/badge/GTK-4.0+-orange.svg" alt="GTK Version"/></a>
  <a href="https://gnome.pages.gitlab.gnome.org/libadwaita/"><img src="https://img.shields.io/badge/libadwaita-1.0+-purple.svg" alt="libadwaita Version"/></a>
</p>

<p align="center">
  <a href="https://www.python.org" target="_blank" rel="noopener noreferrer"><img src="https://img.shields.io/badge/Python-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python"/></a>
  <a href="https://www.gnu.org/software/bash/" target="_blank" rel="noopener noreferrer"><img src="https://img.shields.io/badge/Shell-4EAA25?style=for-the-badge&logo=gnu-bash&logoColor=white" alt="Shell"/></a>
  <a href="https://www.javascript.com/" target="_blank" rel="noopener noreferrer"><img src="https://img.shields.io/badge/JavaScript-F7DF1E?style=for-the-badge&logo=javascript&logoColor=black" alt="JavaScript"/></a>
  <a href="https://www.w3.org/Style/CSS/" target="_blank" rel="noopener noreferrer"><img src="https://img.shields.io/badge/CSS3-66309A?style=for-the-badge&logo=css3&logoColor=white" alt="CSS"/></a>
</p>

# What is Twinverse?

**Twinverse** is an tool for Linux/SteamOS that allows you to create and manage multiple instances of `Steam Big Picture` simultaneously. This enables multiple players to enjoy their game library on a single computer, either in split-screen mode or each with their own display, along with dedicated audio output and input devices.

<p align="center">
  <img alt="twinverse_ui" src="https://raw.githubusercontent.com/mall0r/Twinverse/v1.0.0/share/screenshots/twinverse-ui.png" />
</p>

> [!WARNING]
> This project does not support piracy; all players must own the game in their Steam libraries to be able to play it.

## ✨ Key Features

> [!NOTE]
> Mouse/Keyboard can only be assigned to one instance at a time

Twinverse is designed as a flexible solution for splitscreen gaming on Linux. Here are some of its main features:

1. **Multiple Instances:** Run multiple instances of Steam Client simultaneously

2. **Device Assignment:** Assign specific mouse, keyboard, and controller to each game instance

3. **Dedicated Audio Channels:** Direct audio from each instance to a separate audio output device

4. **Dedicated Home Directory:** Twinverse allows you to have a dedicated home directory for each instance, enabling individual customization of settings and files

5. **Shared Game Folder:** Share the Steam game directory across multiple instances, so you don’t need to download the game again for each instance, saving disk space

6. **Use Any Proton:** Twinverse lets you use any version of Proton to run your games, including custom protons like [ProtonGE](https://github.com/GloriousEggroll/proton-ge-custom)

7. **Play What You Want:** Instances are not limited to running the same game; each instance can run a different game

8. **Flexible Display Modes:** Choose between split screen (up to 4 instances per monitor) or full screen (1 instance per monitor)

---

[1920x1080-RX_6600_XT-demo](https://github.com/user-attachments/assets/e0ca4937-fd38-48cf-b56c-1c825b047572)

---

## 📦 Requirements

To use Twinverse without issues, ensure the following requirements are met:

You need to have the *native* `gamescope` and `steam` packages from your distribution installed.

For Gamescope to function correctly, based on your GPU, you will need:

  - **AMD:** Mesa 20.3 or newer
  - **Intel:** Mesa 21.2 or newer
  - **NVIDIA:** Proprietary drivers 515.43.04 or newer, or NVIDIA Open Kernel Module drivers

> [!NOTE]
> *SteamOS* (AMD) and *Bazzite* generally have all dependencies included by default.

## 📦 Installation

### Flatpak

The recommended way to install Twinverse is via Flatpak, which provides a sandboxed environment and easier updates.
<!--
**Option 1: Install from Flathub (Coming Soon)**
Once Twinverse is available on Flathub, you can install it using the following commands:

```bash
flatpak remote-add --if-not-exists flathub https://flathub.org/repo/flathub.flatpakrepo
flatpak install flathub io.github.mall0r.Twinverse
```-->

**Install from a .flatpak file**

1. **Download the Latest .flatpak file:**
   Go to the [**Releases**](https://github.com/mall0r/Twinverse/releases) page and download the latest `.flatpak` file.

2. **Install the Flatpak:**
   You can install the Flatpak with the following command:

   ```bash
   flatpak install --user Twinverse-*.flatpak
   ```

### AppImage

> [!NOTE]
> Make sure you have the `bubblewrap` package installed.

Alternatively, you can use the AppImage version. This single file works on most modern Linux distributions without requiring system installation.

1. **Download the Latest AppImage:**
   Go to the [**Releases**](https://github.com/mall0r/Twinverse/releases) page and download the latest `.AppImage` file.

2. **Make it Executable:**
   After downloading, right-click the file, go to "Properties," and check the "Allow executing file as program" box. Alternatively, you can use the terminal:

   ```bash
   chmod +x Twinverse-*.AppImage
   ```

3. **Run the Application:**
   Run the AppImage and enjoy. That's it!

#### AppImage Integration (Optional)

For better system integration (e.g., adding a menu entry), you can use a tool like **[Gear Lever](https://github.com/mijorus/gearlever)** to manage your AppImage.

### Running from Source

The `run.sh` script provides a quick way to set up a local environment and run the application. It will automatically create a virtual environment and install the necessary dependencies.

```bash
# Clone the repository
git clone https://github.com/mall0r/Twinverse.git
cd Twinverse

# Run the launch script
./run.sh
```

## 📖 How to Use?

Access our [Guide](https://github.com/mall0r/Twinverse/blob/main/docs/GUIDE.md) for more information on how to use Twinverse.

---

## ⚙️ How It Works

Twinverse uses **Gamescope** (which creates the gaming environment and manages composition) and **Bubblewrap** (bwrap – a tool for building sandbox environments) to isolate each Steam Client instance. In this project, `bwrap` is used with an extra layer of isolation on top of Gamescope, providing a more robust sandbox and allowing granular control over what should or should not be exposed or masked inside the container. This makes it possible to ignore devices unnecessary for that session or to recreate a dedicated *home* directory per instance. This allows each Steam to run in its own separate, independent environment. Thus, the instance cannot interfere with your desktop, and your desktop cannot interfere with it.

The final command line is assembled dynamically based on the user's configuration, following a nested structure where **Gamescope** is the outermost layer, which runs **`bwrap`**, which, in turn, launches **Steam**.

---

## 🛠️ For Developers

If you wish to contribute to Twinverse, please refer to the [CONTRIBUTING](./CONTRIBUTING.md) for detailed instructions on how to get started, development workflows, and code standards.

---

## 📜 License

This project is licensed under the **GNU General Public License v3.0 (GPL-3.0)**. For more details, see the [LICENSE](./LICENSE).

> [!NOTE]
> ## Legal Disclaimer
>
> Twinverse is an independent open-source project and is not affiliated with, endorsed by, or in any way officially connected to Valve Corporation or Steam.
>
> This tool acts as an orchestration layer that leverages sandboxing technologies to run multiple isolated instances of the official Steam client. Twinverse **does not modify, patch, reverse engineer, or alter** any Steam files or  its normal operation. All Steam instances launched by this tool are the official, unmodified versions provided by Valve.
>
> Users are solely responsible for complying with the terms of the Steam Subscriber Agreement.

---

## 🙏 Credits

This project was inspired by the work of:

- [NaviVani-dev](https://github.com/NaviVani-dev) and their script [dualscope.sh](https://gist.github.com/NaviVani-dev/9a8a704a31313fd5ed5fa68babf7bc3a).
- [Tau5](https://github.com/Tau5) and their project [Co-op-on-Linux](https://github.com/Tau5/Co-op-on-Linux).
- [wunnr](https://github.com/wunnr) and their project [Partydeck](https://github.com/wunnr/partydeck) (I recommend using it if you're looking for an approach closer to [Nucleus Co-op](https://github.com/SplitScreen-Me/splitscreenme-nucleus)).


# TTS Asset Extractor & Downloader

A Python script to extract asset URLs (images, models, audio, PDFs, assetbundles) from Tabletop Simulator save files (.json) and download them locally.

It categorizes files into specific folders, names them using TTS's internal cache naming convention (full sanitized URL + extension), and includes advanced features like proxy support and CDN mirroring to bypass regional blocks.

## Features

- Recursive Extraction: Scans the entire TTS JSON tree, including nested objects, decks, and embedded LuaScriptState strings.
- Categorized Downloads: Automatically sorts files into folders (Assetbundles, Audio, Images, Models, PDF, Text, etc.).
- TTS Cache Naming: Saves files using the exact sanitized URL naming convention Tabletop Simulator uses internally (e.g., httpsiimgurcomdgf5P7vjpg.jpg).
- CDN Mirroring (Bypasses 403/400 Errors):
Rewrites cloud-X.steamusercontent.com to the Akamai mirror (steamusercontent-a.akamaihd.net).
Rewrites imgur.com links to the imgur.kageurufu.net mirror.
Mirrors can be disabled via CLI flags.
- Proxy Support: Route downloads through HTTP, HTTPS, or SOCKS5 proxies.
- Resume/Skip: Automatically skips files that have already been downloaded.
- Concurrent Downloads: Uses multithreading for fast downloading.

## Prerequisites

```
Python 3.8 or higher
requests library
tqdm library
```

## Installation

Clone the repository:

```bash
git clone https://github.com/YOUR_USERNAME/tts-asset-extractor.gitcd 
tts-asset-extractor
```

Install the required Python packages:

```bash
pip install -r requirements.txt
```
*(If you plan to use SOCKS5 proxies, install with: pip install requests[socks] tqdm)*
## API Reference


```bash
  python tts_download.py <path-to-json> [options]
```



| Argument | Default | Description |
| :--- | :--- | :--- |
| `json_file` | **Required** | Path to the Tabletop Simulator `.json` save file. |
| `--out` | `assets` | Base output directory for downloaded files. |
| `--proxy` | `None` | Proxy URL (e.g., `http://user:pass@host:port` or `socks5://127.0.0.1:9050`). |
| `--workers` | `8` | Number of concurrent download threads. |
| `--list-only` | `False` | Prints the extracted URLs and their target folders without downloading. |
| `--keep-steam-cdn`| `False` | Disables Steam -> Akamai mirror rewrite (downloads directly from Steam). |
| `--keep-imgur` | `False` | Disables Imgur -> kageurufu.net mirror rewrite. |




## Usage/Examples

#### Basic Download (Mirrors Enabled by default):

```bash
  python tts_download.py dracula.json
```

#### Download to a specific folder with 16 threads:

```bash
  python tts_download.py dracula.json --out ./my_game_assets --workers 16
```

#### Download through a SOCKS5 proxy:

```bash
  python tts_download.py dracula.json --proxy socks5://127.0.0.1:9050
```

#### List URLs to see where they will go without downloading:

```bash
  python tts_download.py dracula.json --list-only
```

#### Download directly from original URLs (Disable all mirrors):

```bash
  python tts_download.py dracula.json --keep-steam-cdn --keep-imgur
```


## Output Folder Structure

The script will create the following folders inside your --out directory as needed:

```
assets/
├── Assetbundles/   (.unity3d)
├── Audio/          (.mp3)
├── Images/         (.jpg, .png)
├── Images Raw/     (.rawt)
├── Models/         (.obj)
├── Models Raw/     (.rawm)
├── PDF/            (.pdf)
└── Text/           (.txt, .lua)
```

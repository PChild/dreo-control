# Dreo Control

A small local HTTP server for controlling a Dreo ceiling fan from Stream Deck buttons or other local scripts.

The server signs in through [`pydreo-community`](https://pypi.org/project/pydreo-community/), finds the first ceiling fan on the account, and exposes a simple API at `http://127.0.0.1:8765`. It listens only on the local computer and is not accessible over the network.

## Requirements

- Windows (the included Stream Deck launchers are batch files)
- Python 3.10 or newer
- A Dreo account with a ceiling fan already configured

Install the Python dependencies:

```powershell
python -m pip install "pydreo-community>=1.11.7" python-dotenv
```

## Configuration

Create a `.env` file beside `dreo_server.py`:

```dotenv
DREO_EMAIL=you@example.com
DREO_PASSWORD=your-password
```

The `.env` file contains credentials and is excluded from Git by `.gitignore`.

## Run the server

From the project directory:

```powershell
python dreo_server.py
```

After connecting, the server prints:

```text
Listening on http://127.0.0.1:8765
```

Leave it running while using the Stream Deck buttons. Press `Ctrl+C` to stop it.

## API

Set one or more fan properties with `GET /set`:

```powershell
curl.exe "http://127.0.0.1:8765/set?fan=4&light=on&brightness=75"
```

Supported query parameters:

| Parameter | Values | Description |
| --- | --- | --- |
| `fan` | `on`, `off`, `toggle`, or a supported speed | Controls fan power or speed; toggling power preserves its level |
| `light` | `on`, `off`, or `toggle` | Controls the light without changing the fan |
| `brightness` | `1`–`100` | Sets light brightness |
| `temp` | Number supported by the device | Sets the light color temperature |

Multiple settings in one request are sent to the fan as one batch. Read the current state with:

```powershell
curl.exe "http://127.0.0.1:8765/status"
```

Toggle either power state independently:

```powershell
curl.exe "http://127.0.0.1:8765/set?fan=toggle"
curl.exe "http://127.0.0.1:8765/set?light=toggle"
```

## Stream Deck setup

The [`stream_deck_buttons`](stream_deck_buttons) directory contains several ready-made presets.

1. Keep `dreo_server.py` running.
2. In Stream Deck, add a **System → Open** action to a button.
3. Select one of the numbered `.bat` files.
4. Give the button a title such as `OFF`, `LIGHT`, `LOW`, `MED`, or `BRIGHT`.

To make a custom preset, copy `preset_template.bat`, rename it, and edit the quoted query on its final line:

```bat
call "%~dp0dreo_request.bat" "fan=3&light=off"
```

Keep the query in quotation marks so Windows treats `&` as part of the URL.

## Start automatically with Windows

Task Scheduler is the most reliable way to start the server:

1. Create a task triggered **At log on** for your Windows account.
2. Add a 30-second delay so the network is ready.
3. Set the program to the full path of `python.exe` (or `pythonw.exe` to hide the console).
4. Set the argument to the full path of `dreo_server.py`.
5. Set **Start in** to this project directory.
6. Configure the task to restart after a failure.

Running only when the user is logged on is sufficient for Stream Deck and avoids storing the account password in the scheduled task.

## Security

- The API has no authentication. Keep the server bound to `127.0.0.1` unless you add authentication first.
- Treat batch presets as commands: review downloaded presets before running them.

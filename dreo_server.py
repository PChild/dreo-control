from __future__ import annotations

from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

from dotenv import load_dotenv
from pydreo import PyDreo
from pydreo.constant import (
    BRIGHTNESS_KEY,
    COLORTEMP_KEY,
    FANON_KEY,
    LIGHTON_KEY,
    WINDLEVEL_KEY,
)
from pydreo.pydreoceilingfan import PyDreoCeilingFan

import os
import time
from typing import TypeAlias, cast


QueryParams: TypeAlias = dict[str, list[str]]
CommandValue: TypeAlias = bool | int
CommandBatch: TypeAlias = dict[str, CommandValue]
BatchSender: TypeAlias = Callable[[CommandBatch], None]


def first_value(params: QueryParams, key: str) -> str | None:
    values = params.get(key)

    if not values:
        return None

    return values[0]


def get_batch_sender(device: PyDreoCeilingFan) -> BatchSender:
    """Return pydreo-community's atomic ceiling-fan batch function.

    The library currently marks this API as protected. Keeping that access in
    this small, typed boundary avoids protected-member and unknown-type reports
    throughout the rest of the server.
    """
    sender_object: object = getattr(device, "_send_command_batch", None)

    if not callable(sender_object):
        raise SystemExit(
            "This pydreo-community version does not provide ceiling-fan "
            "command batching. Upgrade to pydreo-community 1.11.7 or newer."
        )

    return cast(BatchSender, sender_object)


load_dotenv()

email = os.getenv("DREO_EMAIL")
password = os.getenv("DREO_PASSWORD")

if email is None or password is None:
    raise SystemExit("Missing DREO_EMAIL or DREO_PASSWORD in .env")


print("Connecting to Dreo...")

dreo = PyDreo(email, password)

if not dreo.login():
    raise SystemExit("Dreo login failed")

if not dreo.load_devices():
    raise SystemExit("Could not load Dreo devices")


device = next(
    (
        device
        for device in dreo.devices
        if isinstance(device, PyDreoCeilingFan)
    ),
    None,
)

if device is None:
    raise SystemExit("No Dreo ceiling fan found")

# The isinstance check above narrows the base-device list entry for Pylance.
fan = device
send_batch = get_batch_sender(fan)


# pydreo's base metadata annotations are broader than the values returned by
# the API, so narrow those two display-only fields at the library boundary.
fan_name = cast(str | None, getattr(fan, "name", None))
fan_model = cast(str | None, getattr(fan, "model", None))

print(f"Found {fan_name} ({fan_model})")

dreo.start_transport()
time.sleep(2)

print("Dreo command transport ready.")


def build_command_batch(params: QueryParams) -> CommandBatch:
    """Validate one HTTP request and translate it to one Dreo command batch."""
    commands: CommandBatch = {}

    fan_value = first_value(params, "fan")

    if fan_value is not None:
        value = fan_value.lower()

        if value == "on":
            commands[FANON_KEY] = True

        elif value == "off":
            commands[FANON_KEY] = False

        elif value == "toggle":
            commands[FANON_KEY] = not fan.is_on

        else:
            try:
                speed = int(value)
            except ValueError as exc:
                raise ValueError(
                    "fan must be 'on', 'off', 'toggle', or a numeric speed"
                ) from exc

            speed_range = cast(
                tuple[int, int] | None,
                getattr(fan, "speed_range", None),
            )

            if speed_range is None:
                raise ValueError("Fan did not report a valid speed range")

            minimum_speed, maximum_speed = speed_range

            if not minimum_speed <= speed <= maximum_speed:
                raise ValueError(
                    f"Fan speed must be {minimum_speed}-{maximum_speed}"
                )

            # Setting a speed has always meant both selecting that speed and
            # ensuring the fan motor is on.
            commands[WINDLEVEL_KEY] = speed
            commands[FANON_KEY] = True

    light_value = first_value(params, "light")

    if light_value is not None:
        value = light_value.lower()

        if value == "on":
            commands[LIGHTON_KEY] = True

        elif value == "off":
            commands[LIGHTON_KEY] = False

        elif value == "toggle":
            commands[LIGHTON_KEY] = not fan.light_on

        else:
            raise ValueError("light must be 'on', 'off', or 'toggle'")

    brightness_value = first_value(params, "brightness")

    if brightness_value is not None:
        try:
            brightness = int(brightness_value)
        except ValueError as exc:
            raise ValueError("brightness must be an integer") from exc

        if not 1 <= brightness <= 100:
            raise ValueError("brightness must be 1-100")

        commands[BRIGHTNESS_KEY] = brightness

    temp_value = first_value(params, "temp")

    if temp_value is not None:
        try:
            color_temperature = int(temp_value)
        except ValueError as exc:
            raise ValueError("temp must be an integer") from exc

        commands[COLORTEMP_KEY] = color_temperature

    return commands


def apply_commands(params: QueryParams) -> None:
    commands = build_command_batch(params)

    if commands:
        # One submission guarantees that every setting from this HTTP request
        # ships in the same Dreo request and is applied atomically by the fan.
        send_batch(commands)


class DreoRequestHandler(BaseHTTPRequestHandler):
    def send_text(
        self,
        status: int,
        body: str,
    ) -> None:
        encoded = body.encode("utf-8")

        self.send_response(status)
        self.send_header(
            "Content-Type",
            "text/plain; charset=utf-8",
        )
        self.send_header(
            "Content-Length",
            str(len(encoded)),
        )
        self.end_headers()

        self.wfile.write(encoded)

    def do_GET(self) -> None:
        try:
            parsed = urlparse(self.path)

            if parsed.path == "/status":
                current_speed = cast(
                    int | None,
                    getattr(fan, "fan_speed", None),
                )
                body = (
                    f"fan={fan.is_on}\n"
                    f"speed={current_speed}\n"
                    f"light={fan.light_on}\n"
                    f"brightness={fan.brightness}\n"
                    f"temp={fan.color_temperature}\n"
                )

                self.send_text(200, body)
                return

            if parsed.path != "/set":
                self.send_text(404, "Not found\n")
                return

            params: QueryParams = parse_qs(
                parsed.query,
                keep_blank_values=False,
            )

            apply_commands(params)

            self.send_text(200, "OK\n")

        except ValueError as exc:
            self.send_text(
                400,
                f"Error: {exc}\n",
            )

        except Exception as exc:
            self.send_text(
                500,
                f"Internal error: {exc}\n",
            )

    def log_message(
        self,
        format: str,
        *args: object,
    ) -> None:
        # Silence BaseHTTPRequestHandler request logging.
        pass


server = HTTPServer(
    ("127.0.0.1", 8765),
    DreoRequestHandler,
)


print("Listening on http://127.0.0.1:8765")
print("Press Ctrl+C to stop.")


try:
    server.serve_forever()

except KeyboardInterrupt:
    print("\nStopping...")

finally:
    server.server_close()
    dreo.stop_transport()

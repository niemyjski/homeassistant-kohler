# Kohler for Home Assistant

Local Home Assistant integration for Kohler DTV+ shower systems.

This project talks directly to the Kohler controller over your local network and exposes shower controls, outlet controls, diagnostics, and maintenance actions inside Home Assistant.

## Status

- Supported hardware: Kohler DTV+
- Transport: local polling over HTTP
- Home Assistant setup: config flow
- HACS compatible: yes

This is an independent community project. It is not affiliated with or supported by Kohler or the Home Assistant project.

## Features

- Primary shower control exposed through Home Assistant
- Per-outlet valve entities with friendly names and mapped icons
- Dynamic polling for faster updates while the shower is running
- Active user preset selection
- Light control for installed shower lights
- Steam control when a steam module is installed
- Maintenance buttons for time sync, massage toggle, update checks, and fault resets
- Translated valve settings surfaced as entity attributes
- Diagnostic entities for firmware, connection state, and calibration codes
- Downloadable Home Assistant diagnostics that include controller and Konnect error logs

## Entities

Depending on installed hardware and configuration, the integration can create:

- `climate` and `water_heater` shower control entities
- `valve` entities for each mapped shower outlet
- `light` entities for installed light modules
- `switch` entities for steam
- `select` entities for active user presets
- `button` entities for maintenance actions
- `sensor` and `binary_sensor` entities for diagnostics and device state

## Installation

### HACS

1. Open HACS.
2. Add this repository as a custom repository.
3. Choose the `Integration` category.
4. Install `Kohler`.
5. Restart Home Assistant.

### Manual installation

1. Copy `custom_components/kohler` into your Home Assistant `custom_components` directory.
2. Restart Home Assistant.

## Configuration

1. In Home Assistant, go to `Settings > Devices & services`.
2. Click `Add Integration`.
3. Search for `Kohler`.
4. Enter the IP address or hostname of your Kohler DTV+ controller.
5. Accept the liability terms to finish setup.

## What Gets Exposed

### Primary shower control

The integration exposes the shower as both a `climate` entity and a `water_heater` entity for broader dashboard and voice-assistant compatibility.

### Outlet controls

Each installed outlet is exposed as a Home Assistant `valve` entity. The integration uses the Kohler outlet mapping information to assign friendlier names and icons when possible, for example:

- `Shower Head 1`
- `Shower Head 2`
- `Hand Shower`
- `Body Sprayer`

Valve and outlet numbers are still available as attributes for automations and debugging.

### Device settings and diagnostics

The integration surfaces translated valve settings and diagnostics such as:

- Default temperature
- Max temperature
- Cold water timeout
- Auto purge duration
- Max run time
- Connection diagnostics for interfaces, controller, valves, and optional modules
- Six-port calibration codes
- Firmware versions

Home Assistant diagnostics downloads also include:

- Current values payload
- Current system info payload
- Outlet mapping state
- Controller error log
- Konnect error log

## Safety

This integration can control live water hardware. Before enabling it:

- Make sure you understand which outlets and valves are connected.
- Be careful with automations, voice assistants, and remote access.
- Test changes while you are present.
- Treat this integration as capable of turning on water.

## Waiver of Liability

This integration can read device state and send live commands to plumbing hardware, including commands that may start water flow. By installing, configuring, or using this project, you accept responsibility for the risks involved.

The software is provided as-is, without warranty of any kind. The maintainers and contributors are not liable for injury, water damage, property damage, equipment damage, data loss, downtime, or any other loss that may result from using this integration.

By accepting the liability terms during setup, you acknowledge that:

- you understand this integration can control real water hardware
- you are responsible for testing and operating it safely
- you accept the risk of damage or injury that may result from its use
- you will not hold the maintainers or contributors liable for resulting harm or loss

## Development

Development targets the latest stable Home Assistant release and the Python
version it requires (currently Python 3.14). Home Assistant recommends its
[monthly stable releases](https://www.home-assistant.io/faq/release/).
The minimum in `requirements.txt` is a compatibility floor, not a release pin.

Use a fresh virtual environment and install the latest stable test dependencies:

```sh
python3.14 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python scripts/install_test_dependencies.py
pytest --cov=custom_components/kohler --cov-report=term --cov-report=xml tests
ruff check .
ruff format --check .
```

The installer reads current package versions from PyPI and requests those exact
Home Assistant, test-harness, and Ruff releases together. If the harness has not
caught up with Home Assistant, installation fails visibly instead of silently
testing an older release. CI uses the same installer and saves `coverage.xml`
as the `coverage` artifact. These tests use mocked devices; passing CI does not
establish physical-device behavior.

## Troubleshooting

- Confirm the controller is reachable from the Home Assistant host.
- Verify the Kohler web interface responds at the configured IP address.
- Use the integration diagnostics download in Home Assistant for a support bundle.
- Check the exported controller and Konnect error logs when diagnosing device-side faults.

## Contributing

Issues and pull requests are welcome.

If you are adding support for more Kohler hardware, improving diagnostics, or tightening entity behavior, please include:

- a short summary of the hardware or behavior being added
- local test results
- any screenshots or Home Assistant entity examples that help explain the change

### Automatic clock synchronization

Home Assistant maintains the shower clock automatically using its configured
timezone. This is enabled by default for both new and existing configurations;
no migration or setup is needed. It compares the clock data already received by
normal polling, corrects differences over 90 seconds, and disables the controller's
separate daylight-saving adjustment so seasonal changes are applied only once.
Corrections wait until the shower and steam are off and are limited to once an
hour, including failed attempts. Clock failures do not make shower entities
unavailable. A timezone or seasonal change is handled on the next eligible poll.

Clock readings and synchronization diagnostics remain internal: no ticking time
sensor, changing timestamp attributes, or automatic button presses are added to
Home Assistant history. Download integration diagnostics to inspect the last
check, measured difference, write attempt, and verified result. The controller
returns formatted text with a UTC offset, not a named timezone. Unsupported or
incomplete readings skip automatic correction; the integration never guesses a
missing offset. Manual sync can repair a malformed clock when its advertised
date/time formats are valid and include an offset.

Under **Settings → Devices & services → Kohler → Configure**, turn off
**Automatically synchronize clock** to stop future automatic corrections. This
does not restore the old time or re-enable the controller's DST adjustment. The
existing **Sync Time** button performs a manual correction with controller DST
off, even when automatic synchronization is disabled. Both paths verify the
result on the following poll rather than assuming the write succeeded.

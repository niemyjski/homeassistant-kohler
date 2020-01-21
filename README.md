# homeassistant-kohler
Kohler Integration for Home Assistant

Uses the [Kohler Python library](https://github.com/niemyjski/kohler-python) to get device data. Currently this only supports the DTV+ system.
It would be sweet to add support at a future date for other devices like the smart mirrors (currently installed but not very smart) too ;) PR's are welcomed!

I initially [filed an issue](https://github.com/home-assistant/architecture/issues/74) for a shower device type to home assistant. I spent the weekend learning python (WIP), and decided to keep on hacking to try and get a network client that could talk to Kohler! This is my first python project but was a lot of fun getting this working over the course of a weekend.

## Setup instructions

1. Install via [HACS](https://github.com/hacs/integration) by adding this repository to the HACS configuration settings.
2. Add the following to your `configuration.yml`:

```yaml
kohler:
  host: YOUR_SHOWER_IP
```

## Features
- Control your shower with Home Assistant
  - with Google Assistant, Alexa, and HomeKit!
- Control shower lights

## Coming Soon!
** NOTE** This library is very early stages and I plan on adding support for much more. PRs are welcomed!
- [Python Lib] [Try and get this nasty hack fixed](https://gist.github.com/niemyjski/6ba88dcdca7e76172c58530bac66eada)
- [DTV+] Add binary_sensor/sensors for each valves, and gadgets
- [DTV+] Add media player support (already supported by python library)
- [DTV+] Add Steam support (already supported by python library)
- [DTV+] Add device info + state attributes
- [DTV+] Add nice UI for controlling shower.
- [Mirrors] Add support for mirror lights and sensors (already installed in my house).
- [Toilet] If someone wants to send me a smart toilet I'll support that too :-)


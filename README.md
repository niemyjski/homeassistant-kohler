# homeassistant-kohler

Kohler Integration for Home Assistant

Uses the [Kohler Python library](https://github.com/niemyjski/kohler-python) to get device data. Currently this only supports the DTV+ system.
It would be sweet to add support at a future date for other devices like the smart mirrors (currently installed but not very smart) too ;) PR's are welcomed!

I initially [filed an issue](https://github.com/home-assistant/architecture/issues/74) for a shower device type to home assistant. I spent the weekend learning python (WIP), and decided to keep on hacking to try and get a network client that could talk to Kohler! This is my first python project but was a lot of fun getting this working over the course of a weekend.

## Setup instructions

1. Install via [HACS](https://github.com/hacs/integration) by adding this repository to the HACS configuration settings.
2. Add the following to your `configuration.yml`:
3. Accept the waiver of liability by reading below.

```yaml
kohler:
  host: YOUR_SHOWER_IP
  accept_liability_terms: False
```

## Features

- Control your shower with Home Assistant
  - with Google Assistant, Alexa, and HomeKit!
- Control shower lights

## Waiver Of liability

This agreement releases Blake Niemyjski from all liability relating to injuries or property damage that may occur while using this shower component (installing it, turning on water valves, reading device state, etc. By accepting this agreement, I agree to hold Blake Niemyjski entirely free from any liability, including financial responsibility for injuries or property damage incurred, regardless of whether injuries are caused by negligence.

I also acknowledge the risks involved in controlling water valves and devices. These include but are not limited to water damage, damage to home, damage to property, damage to devices, or death. I swear that I am participating voluntarily, and that all risks have been made clear to me. Additionally, I do not have any conditions that will increase my likelihood of experiencing injuries while engaging in this activity.

By accepting the terms (by setting the `accept_liability_terms` setting to `True`) I forfeit all right to bring a suit against Blake Niemyjski or any contributors for any reason. In return, I will receive the possibility to interact with your Kohler devices. I will also make every effort to obey all safety precautions as listed in the owner manuals, listed here and anything else not covered (I am accepting all responsibilities). I will ask for clarification when needed.

## Coming Soon

**NOTE** This library is very early stages and I plan on adding support for much more. PRs are welcomed!

- [Python Lib] [Try and get this nasty hack fixed](https://gist.github.com/niemyjski/6ba88dcdca7e76172c58530bac66eada)
- [DTV+] Add binary_sensor/sensors for each valves, and gadgets
- [DTV+] Add media player support (already supported by python library)
- [DTV+] Add Steam support (already supported by python library)
- [DTV+] Add device info + state attributes
- [DTV+] Add nice UI for controlling shower.
- [Mirrors] Add support for mirror lights and sensors (already installed in my house).
- [Toilet] If someone wants to send me a smart toilet I'll support that too :-)

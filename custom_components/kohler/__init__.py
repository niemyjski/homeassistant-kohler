from homeassistant.const import CONF_HOST
import homeassistant.helpers.config_validation as cv
import voluptuous as vol
import logging

DOMAIN = 'kohler'
_LOGGER = logging.getLogger(__name__)

# Validation of the user's configuration
CONFIG_SCHEMA = vol.Schema({
    DOMAIN: vol.Schema({
        vol.Required(CONF_HOST): cv.string
    })
}, extra=vol.ALLOW_EXTRA)


def setup(hass, config):
    from kohler import Kohler

    conf = config[DOMAIN]
    host = conf[CONF_HOST]

    # Setup connection with devices/cloud
    kohler = Kohler(kohlerHost=host)

    try:
        values = kohler.values()
        systemInfo = kohler.systemInfo()

        hass.data[DOMAIN] = {
            "kohler": kohler,
            "kohler_init_values": values,
            "kohler_init_system_info": systemInfo
        }
    except:
        _LOGGER.error("Unable to retrieve data from Kohler server")
        return False

    hass.helpers.discovery.load_platform('light', DOMAIN, {}, config)
    hass.helpers.discovery.load_platform('water_heater', DOMAIN, {}, config)
    return True


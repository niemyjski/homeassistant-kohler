import json
import requests
from requests.exceptions import ConnectionError
import logging

from .const import CONF_ACCEPT_LIABILITY_TERMS, DOMAIN, DATA_KOHLER

_LOGGER = logging.getLogger(__name__)

CONTENT_TYPE_JSON = "application/json"
CONTENT_TYPE_TEXT_PLAIN = "text/plain"

class Kohler:
    def __init__(self, kohlerHost):
        self._baseUrl = f"http://{kohlerHost}"

    def btDisconnect(self):
        url = f"{self._baseUrl}/bt_disconnect.cgi"
        return self.fetch(url, None, CONTENT_TYPE_TEXT_PLAIN)

    def checkUpdates(self):
        url = f"{self._baseUrl}/check_updates.cgi"
        return self.fetch(url)

    def ftpStatus(self):
        url = f"{self._baseUrl}/ftp_status.cgi"
        return self.fetch(url)

    def idInterface(self, index):
        params = {
            "index": index
        }

        url = f"{self._baseUrl}/id_interface.cgi"
        return self.fetch(url, params)

    def languages(self):
        url = f"{self._baseUrl}/languages.cgi"
        return self.fetch(url)

    def lightOff(self, module):
        params = {
            "module": module  # light number
        }

        url = f"{self._baseUrl}/light_off.cgi"
        return self.fetch(url, params, CONTENT_TYPE_TEXT_PLAIN)

    def lightOn(self, module=1, intensity=100):
        # min: 0, max: 100, interval: 1
        params = {
            "module": module,  # light number
            "intensity": intensity
        }

        url = f"{self._baseUrl}/light_on.cgi"
        return self.fetch(url, params, CONTENT_TYPE_TEXT_PLAIN)

    def lightModule(self, module=2, intensity=100):
        # min: 0, max: 100, interval: 1
        params = {
            "module": module,  # light number
            "intensity": intensity
        }

        url = f"{self._baseUrl}/light_module.cgi"
        return self.fetch(url, params, CONTENT_TYPE_TEXT_PLAIN)

    def musicOff(self, volume=100):
        params = {
            "volume": volume
        }
        url = f"{self._baseUrl}/music_off.cgi"
        return self.fetch(url, params, CONTENT_TYPE_TEXT_PLAIN)

    def musicOn(self, volume=100):
        # min: 0, max: 100, interval: 1
        params = {
            "volume": volume
        }
        url = f"{self._baseUrl}/music_on.cgi"
        return self.fetch(url, params, CONTENT_TYPE_TEXT_PLAIN)

    def powercleanCheck(self):
        url = f"{self._baseUrl}/powerclean_check.cgi"
        return self.fetch(url)

    def rainOff(self, value):
        url = f"{self._baseUrl}/rain_off.cgi"
        return self.fetch(url, None, CONTENT_TYPE_TEXT_PLAIN)

    def rainOn(self, mode, color, effect):
        # min: 0, max: 100, interval: 1
        params = {
            "mode": mode,
            "color": color,
            "effect": effect
        }
        url = f"{self._baseUrl}/rain_on.cgi"
        return self.fetch(url, params, CONTENT_TYPE_TEXT_PLAIN)

    def removeModule(self, module):
        params = {
            "module": module
        }

        url = f"{self._baseUrl}/remove_module.cgi"
        return self.fetch(url, params)

    def resetDefault(self):
        url = f"{self._baseUrl}/reset_default.cgi"
        return self.fetch(url)

    def resetFactory(self):
        url = f"{self._baseUrl}/reset_factory.cgi"
        return self.fetch(url, None, CONTENT_TYPE_TEXT_PLAIN)

    def resetUsers(self):
        url = f"{self._baseUrl}/reset_users.cgi"
        return self.fetch(url)

    def saveDT(self):
        url = f"{self._baseUrl}/saveDT.cgi"
        return self.fetch(url, None, CONTENT_TYPE_TEXT_PLAIN)

    def saveUI(self, index):
        params = {
            "index": index
        }

        url = f"{self._baseUrl}/saveUI.cgi"
        return self.fetch(url, params)

    def saveVariable(self, index, value, **kwargs):
        params = {
            "index": index,
            "value": value
        }

        url = f"{self._baseUrl}/save_variable.cgi"
        return self.fetch(url, {**kwargs, **params}, CONTENT_TYPE_TEXT_PLAIN)

    def setDevice(self, value):
        url = f"{self._baseUrl}/set_device.cgi"
        return self.fetch(url, {"value": value})

    def steamOff(self, value):
        url = f"{self._baseUrl}/steam_off.cgi"
        return self.fetch(url, None, CONTENT_TYPE_TEXT_PLAIN, 10)

    def steamOn(self, temp=110, time=10):
        params = {
            "temp": temp,
            "time": time
        }
        url = f"{self._baseUrl}/steam_on.cgi"
        return self.fetch(url, params, CONTENT_TYPE_TEXT_PLAIN, 3)

    def stopUser(self):
        url = f"{self._baseUrl}/stop_user.cgi"
        return self.fetch(url, None, CONTENT_TYPE_TEXT_PLAIN, 10)

    def stopShower(self):
        url = f"{self._baseUrl}/stop_shower.cgi"
        return self.fetch(url, None, CONTENT_TYPE_TEXT_PLAIN, 10)

    def startUser(self, user=1):
        params = {
            "user": user
        }

        url = f"{self._baseUrl}/start_user.cgi"
        return self.fetch(url, params, CONTENT_TYPE_TEXT_PLAIN)

    def systemInfo(self):
        url = f"{self._baseUrl}/system_info.cgi"
        return self.fetch(url)

    def values(self):
        url = f"{self._baseUrl}/values.cgi"
        return self.fetch(url)

    def quickShower(self,
                    valve_num=1,
                    valve1_outlet=1,
                    valve1_massage=0,
                    valve1_temp=100,
                    valve2_outlet=0,
                    valve2_massage=0,
                    valve2_temp=100):

        params = {
            "valve_num": valve_num,
            "valve1_outlet": valve1_outlet,
            "valve1_massage": valve1_massage,
            "valve1_temp": f"{int(valve1_temp)}.0",
            "valve2_outlet": valve2_outlet,
            "valve2_massage": valve2_massage,
            "valve2_temp": f"{int(valve2_temp)}.0"
        }
        url = f"{self._baseUrl}/quick_shower.cgi"
        return self.fetch(url, params, CONTENT_TYPE_TEXT_PLAIN, 3)

    def fetch(self, url, params=None, contentType=CONTENT_TYPE_JSON, timeout=1):
        try:
            _LOGGER.info(f"Doing HTTP get from {url} with {params}.")
            response = requests.get(url, params=params, timeout=timeout)
        except ConnectionError as ex:
            if len(ex.args) < 1:
                raise

            #HACK: gist.github.com/niemyjski/6ba88dcdca7e76172c58530bac66eada
            responseText = ex.args[0].args[1].line
            if contentType == CONTENT_TYPE_JSON:
                return json.loads(responseText)

            return responseText
        else:
            if contentType == CONTENT_TYPE_JSON:
                return response.json()

            return response.text

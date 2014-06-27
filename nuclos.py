import configparser
import json
import locale
import logging
import urllib.request

# TODO: allow logging to a file (specified in settings file).
# TODO: allow changing the log level. Remove the debug option then.


class NuclosSettings:
    def __init__(self, filename):
        self.config = configparser.ConfigParser()
        self.config.read(filename)

    @property
    def ip(self):
        return self.config.get("server", "ip", fallback="localhost")

    @property
    def port(self):
        return self.config.getint("server", "port", fallback=80)

    @property
    def instance(self):
        return self.config.get("server", "instance", fallback="nuclos")

    @property
    def username(self):
        return self.config.get("nuclos", "username", fallback="nuclos")

    @property
    def password(self):
        return self.config.get("nuclos", "password", fallback="")

    @property
    def locale(self):
        default_locale = locale.getlocale()[0]
        return self.config.get("nuclos", "locale", fallback=default_locale)

    @property
    def debug(self):
        return self.config.getboolean("nuclos", "debug", fallback=False)

    @property
    def handle_http_errors(self):
        return self.config.getboolean("nuclos", "handle_http_errors", fallback=True)


class NuclosException(Exception):
    pass


class NuclosAPI:
    def __init__(self, settings):
        self.settings = settings
        self.session_id = None

    @classmethod
    def from_ini_file(cls, filename):
        settings = NuclosSettings(filename)
        return cls(settings)

    def login(self):
        """
        Log in to the Nuclos server.

        :return: True is successful, False otherwise.
        """
        # TODO: Check whether nuclos version >= 4.0, exception if not.

        login_data = {
            "username": self.settings.username,
            "password": self.settings.password,
            "locale": self.settings.locale
        }

        # TODO: This might change soon. Response won't be a string then but a JSON object containing the session id.
        answer = self._request("login", login_data, auto_login=False, json_answer=False)
        if answer:
            self.session_id = answer
            logging.info("Successfully logged in to the Nuclos server.")
            return True
        return False

    def logout(self):
        pass

    def reconnect(self):
        self.logout()
        # TODO: clear caches.

    def _request(self, path, data=None, auto_login=True, json_answer=True):
        """
        Send a request to the Nuclos server.

        :param path: The path to open.
        :param data: The data to add. If this is given the request will automatically be a POST request.
        :param auto_login: Try to log in automatically.
        :param json_answer: Parse the servers answer as JSON.
        :return: The answer of the server. None in case of an error.
        """
        if not self.session_id and auto_login:
            self.login()

        url = self._build_url(path)
        request = urllib.request.Request(url)
        if data:
            request.data = json.dumps(data).encode("utf-8")
            request.add_header("Content-Type", "application/json")
        if self.session_id:
            request.add_header("sessionid", self.session_id)

        logging.debug("Sending request: '{}' with data '{}'.".format(request.get_full_url(), request.data))
        try:
            result = urllib.request.urlopen(request)
            answer = result.read().decode()
            logging.debug("Answer: {}".format(answer))
            if not json_answer:
                return answer
            try:
                return json.loads(answer)
            except ValueError:
                logging.error("Invalid JSON in '{}'.".format(answer))
                return None
        except urllib.request.URLError as e:
            if e.code == 401 and auto_login:
                logging.info("Unauthorized. Trying to log in again.")
                self.session_id = None
                if self.login():
                    return self._request(path, data, auto_login=False, json_answer=json_answer)
            logging.error("HTTP Error {}: {}".format(e.code, e.reason))
            if not self.settings.handle_http_errors:
                raise e

    def _build_url(self, path):
        return "http://{}:{}/{}/rest/{}".format(self.settings.ip, self.settings.port, self.settings.instance, path)


class AbstractNuclosEntity:
    pass


class NuclosEntity(AbstractNuclosEntity):
    pass


class NuclosEntityProxy(AbstractNuclosEntity):
    pass

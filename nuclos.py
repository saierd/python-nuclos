import collections
import configparser
import functools
import json
import locale
import logging
import urllib.request


class NuclosSettings:
    def __init__(self, filename):
        self.config = configparser.ConfigParser(interpolation=None)
        self.config.read(filename)

        log_level_config = self.config.get("nuclos", "log_level", fallback="INFO").upper()
        log_level = getattr(logging, log_level_config, None)
        if not isinstance(log_level, int):
            raise ValueError("Unknown log level '{}'.".format(log_level_config))
        log_format = self.config.get("nuclos", "log_format", fallback="%(levelname)s %(asctime)s\t%(message)s")
        log_format = bytes(log_format, "utf-8").decode("unicode_escape")
        date_format = self.config.get("nuclos", "log_date_format", fallback="%d.%m.%Y %H:%M:%S")
        date_format = bytes(date_format, "utf-8").decode("unicode_escape")
        log_file = self.config.get("nuclos", "log_file", fallback="")

        logging.basicConfig(filename=log_file, datefmt=date_format, format=log_format, level=log_level)

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
    def handle_http_errors(self):
        return self.config.getboolean("nuclos", "handle_http_errors", fallback=True)


class Cached:
    cached = []

    def __init__(self, f):
        self.f = f
        self.cache = {}
        Cached.cached.append(self)

    @classmethod
    def clear(cls):
        for cache in Cached.cached:
            cache.clear_cache()

    def clear_cache(self):
        self.cache = {}

    def __call__(self, *args):
        if not isinstance(args, collections.Hashable):
            return self.f(*args)
        if not args in self.cache:
            self.cache[args] = self.f(*args)
        return self.cache[args]

    def __get__(self, instance, _):
        return functools.partial(self.__call__, instance)


class NuclosException(Exception):
    pass


class NuclosVersionException(NuclosException):
    pass


class NuclosAPI:
    def __init__(self, settings):
        self.settings = settings
        self.session_id = None

    @classmethod
    def from_ini_file(cls, filename):
        settings = NuclosSettings(filename)
        return cls(settings)

    @property
    @Cached
    def version(self):
        return self._request("version", auto_login=False, json_answer=False)

    @property
    @Cached
    def db_version(self):
        return self._request("dbversion", auto_login=False, json_answer=False)

    def require_version(self, *version):
        """
        Check whether the version of the Nuclos server is at least the given one.

        :param version: A list of numbers specifying the required version.
        :return: True if the server version is high enough, False otherwise.
        """
        version_string = self.version.split(" ")[0]
        version_parts = [int(x) for x in version_string.split(".")]

        for v, req in zip(version_parts, version):
            if v < req:
                return False
        return True

    def login(self):
        """
        Log in to the Nuclos server.

        :return: True is successful, False otherwise.
        """
        if not self.require_version(4, 3):
            raise NuclosVersionException("Need at least Nuclos 4.3 to use this version of the REST API.")

        login_data = {
            "username": self.settings.username,
            "password": self.settings.password,
            "locale": self.settings.locale
        }

        # TODO: This might change soon. Response won't be a string then but a JSON object containing the session id.
        answer = self._request("", login_data, auto_login=False, json_answer=False)
        if answer:
            self.session_id = answer
            logging.info("Logged in to the Nuclos server.")
            return True
        return False

    def logout(self):
        """
        Log out from the Nuclos server.

        :return: True if successful, False otherwise.
        """
        if not self.session_id:
            return True

        answer = self._request("logout")
        if not answer is None:
            self.session_id = None
            logging.info("Logged out from the Nuclos server.")
            return True
        return False

    def reconnect(self):
        """
        Reconnect to the server. This will also clear caches.
        """
        self.logout()
        Cached.clear()

    def get_entity(self, name):
        pass

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
            if not self.login():
                return None

        url = self._build_url(path)
        request = urllib.request.Request(url)
        if data:
            request.data = json.dumps(data).encode("utf-8")
            request.add_header("Content-Type", "application/json")
        if self.session_id:
            request.add_header("sessionid", self.session_id)

        logging.debug("Request: '{}' with data '{}'.".format(request.get_full_url(), request.data))
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
            return None

    def _build_url(self, path):
        return "http://{}:{}/{}/rest/{}".format(self.settings.ip, self.settings.port, self.settings.instance, path)


class Entity:
    pass


class AbstractEntityInstance:
    pass


class EntityInstance(AbstractEntityInstance):
    pass


class EntityProxy(AbstractEntityInstance):
    pass

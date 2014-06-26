import configparser
import json
import locale
import urllib.request


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

    def _debug_message(self, message):
        if self.settings.debug:
            print(message)

    def login(self):
        pass

    def logout(self):
        pass

    def reconnect(self):
        self.logout()
        # TODO: clear caches.


class AbstractNuclosEntity:
    pass


class NuclosEntity(AbstractNuclosEntity):
    pass


class NuclosEntityProxy(AbstractNuclosEntity):
    pass

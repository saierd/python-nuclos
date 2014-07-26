"""
Copyright (c) 2014 Daniel Saier

This project is licensed under the terms of the MIT license. See the LICENSE file.
"""

import sys

if sys.version_info[0] != 3 or sys.version_info[1] < 3:
    print("This library needs at least Python 3.3")
    sys.exit(1)

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
    def from_settings_file(cls, filename):
        settings = NuclosSettings(filename)
        return cls(settings)

    @property
    @Cached
    def version(self):
        return self.request("version", auto_login=False, json_answer=False)

    @property
    @Cached
    def db_version(self):
        return self.request("dbversion", auto_login=False, json_answer=False)

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

        answer = self.request("", login_data, auto_login=False)
        if answer:
            self.session_id = answer["session_id"]
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

        answer = self.request("", method="DELETE", json_answer=False)
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

    @property
    @Cached
    def _business_objects(self):
        """
        Get a list of all available business objects.

        :return: See the Nuclos bometalist response.
        """
        return self.request("bo")

    @Cached
    def _get_bo_meta_id(self, name):
        """
        Get the meta id of a business object by its name. This method is not case sensitive.

        :param name: The name of the business object to find.
        :return: The meta id of this business object. None if it does not exist.
        """
        name = name.lower()

        for bo in self._business_objects:
            if bo["name"].lower() == name:
                return bo["bo_meta_id"]

        # Allow replacing spaces in the name by underscores.
        if "_" in name:
            return self._get_bo_meta_id(name.replace("_", " "))
        return None

    @Cached
    def _bo_meta_id_exists(self, bo_meta_id):
        """
        Check whether a business object with the given meta id exists.

        :param bo_meta_id: The meta id to search for.
        :return: True if there is a business object with the given meta id. False otherwise.
        """
        for bo in self._business_objects:
            if bo["bo_meta_id"] == bo_meta_id:
                return True
        return False

    @Cached
    def get_business_object(self, bo_meta_id):
        """
        Get a business object by its meta id.

        :param bo_meta_id: The meta id of the business object to find.
        :return: A BusinessObject object. None if the business object does not exist.
        """
        if self._bo_meta_id_exists(bo_meta_id):
            return BusinessObject(self, bo_meta_id)
        return None

    def get_business_object_by_name(self, name):
        """
        Get a business object by its name.

        :param name: The name of the business object to find.
        :return: A BusinessObject object. None if the business object does not exist.
        """
        bo_meta_id = self._get_bo_meta_id(name)
        if bo_meta_id:
            return self.get_business_object(bo_meta_id)
        return None

    def __getattr__(self, name):
        bo = self.get_business_object_by_name(name)
        if bo:
            return bo
        raise AttributeError("Unknown business object '{}'.".format(name))

    def __getitem__(self, name):
        if isinstance(name, str):
            bo = self.get_business_object_by_name(name)
            if bo:
                return bo
            raise IndexError("Unknown business object '{}'.".format(name))
        raise TypeError("Invalid argument type.")

    @property
    @Cached
    def business_objects(self):
        return [self.get_business_object(bo["bo_meta_id"]) for bo in self._business_objects]

    def request(self, path, data=None, method=None, auto_login=True, json_answer=True):
        """
        Send a request to the Nuclos server.

        :param path: The path to open.
        :param data: The data to add. If this is given the request will automatically be a POST request.
        :param method: The HTTP method to use. If not set this will be GET or POST, depending on the data.
        :param auto_login: Try to log in automatically in case of a 401 error.
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
        if method:
            request.method = method
        if method and request.data and not method in ["POST", "PUT"]:
            logging.warning("Overriding the POST method while sending data!")
        if self.session_id:
            request.add_header("sessionid", self.session_id)

        logging.debug("Sending {} request to {}.".format(request.get_method(), request.get_full_url()))
        if request.data:
            logging.debug("Sending data {}.".format(request.data))

        try:
            result = urllib.request.urlopen(request)
            answer = result.read().decode()
            if answer:
                logging.debug("Received answer {}".format(answer))
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
                    return self.request(path, data=data, method=method, auto_login=False, json_answer=json_answer)
            logging.error("HTTP Error {}: {}".format(e.code, e.reason))
            if self.settings.handle_http_errors:
                return None
            raise e

    def _build_url(self, path):
        return "http://{}:{}/{}/rest/{}".format(self.settings.ip, self.settings.port, self.settings.instance, path)


class BOMeta:
    def __init__(self, nuclos, bo_meta_id):
        self.nuclos = nuclos
        self.bo_meta_id = bo_meta_id
        self.data = self.nuclos.request("bo/meta/{}".format(self.bo_meta_id))

    @property
    def name(self):
        return self.data["name"]

    @property
    def can_update(self):
        return self.data["update"]

    @property
    def can_insert(self):
        return self.data["insert"]

    @property
    def can_delete(self):
        return self.data["delete"]

    @property
    @Cached
    def attributes(self):
        return [BOMetaAttribute(a) for a in self.data["attributes"]]


class BOMetaAttribute:
    def __init__(self, data):
        self.data = data

    @property
    def name(self):
        return self.data["name"]

    @property
    def bo_attr_id(self):
        return self.data["bo_attr_id"]

    @property
    def writeable(self):
        return not self.data["readonly"]

    @property
    def is_reference(self):
        return self.data["reference"]


class BusinessObject:
    def __init__(self, nuclos, bo_meta_id):
        self.nuclos = nuclos
        self.bo_meta_id = bo_meta_id

    @property
    @Cached
    def meta(self):
        return BOMeta(self.nuclos, self.bo_meta_id)


class _BOInstance:
    pass


class BOInstance(_BOInstance):
    pass


class BOProxy(_BOInstance):
    pass

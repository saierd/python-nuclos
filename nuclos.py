"""
Copyright (c) 2014 Daniel Saier

This project is licensed under the terms of the MIT license. See the LICENSE file.
"""

# TODO: HTTPS Support.
# TODO: Do not catch the NuclosHTTPException but let the user handle it instead? Write this down in the last part of
#       the documentation.

import sys

if sys.version_info[0] != 3 or sys.version_info[1] < 3:
    print("This library needs at least Python 3.3!")
    sys.exit(1)

import collections
import configparser
import functools
import json
import locale
import logging
import urllib.request

VERSION_ROUTE = "version"
DB_VERSION_ROUTE = "dbversion"
LOGIN_ROUTE = ""
LOGOUT_ROUTE = ""
BO_LIST_ROUTE = "bo_metas"
BO_META_ROUTE = "bo_metas/{}"
BO_INSTANCE_LIST_ROUTE = "bo_metas/{}/bos"
BO_INSTANCE_ROUTE = "bo_metas/{}/bos/{}"


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


class NuclosAuthenticationException(NuclosException):
    pass


class NuclosHTTPException(NuclosException):
    def __init__(self, exception):
        self.code = exception.code
        self.reason = exception.reason
        super().__init__("HTTP Exception: {} - {}".format(self.code, self.reason))


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
        return self.request(VERSION_ROUTE, auto_login=False, json_answer=False)

    @property
    @Cached
    def db_version(self):
        return self.request(DB_VERSION_ROUTE, auto_login=False, json_answer=False)

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

        :raises: NuclosVersionException if the server version is too low to use the API.
        :raises: NuclosAuthenticationException if the login was not successful.
        """
        if not self.require_version(4, 3):
            raise NuclosVersionException("You need at least Nuclos 4.3 to use this version of the REST API.")

        login_data = {
            "username": self.settings.username,
            "password": self.settings.password,
            "locale": self.settings.locale
        }

        answer = self.request(LOGIN_ROUTE, data=login_data, auto_login=False)
        if answer:
            self.session_id = answer["session_id"]
            logging.info("Logging in to the Nuclos server.")
        else:
            raise NuclosAuthenticationException("Login failed!")

    def logout(self):
        """
        Log out from the Nuclos server.

        :return: True if successful, False otherwise.
        """
        if not self.session_id:
            return True

        answer = self.request(LOGOUT_ROUTE, method="DELETE", json_answer=False)
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
        return self.request(BO_LIST_ROUTE)

    @Cached
    def _get_bo_meta_id(self, name):
        """
        Get the meta id of a business object by its name. This method is not case sensitive.

        :param name: The name of the business object to find.
        :return: The meta id of this business object. None if it does not exist.
        """
        name = name.lower()

        if self._business_objects:
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
        if self._business_objects:
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

    def request(self, path, parameters=None, data=None, method=None, auto_login=True, json_answer=True):
        """
        Send a request to the Nuclos server.

        :param path: The path to open.
        :param parameters: A dictionary of parameters to add to the request URL.
        :param data: The data to add. If this is given the request will automatically be a POST request.
        :param method: The HTTP method to use. If not set this will be GET or POST, depending on the data.
        :param auto_login: Try to log in automatically in case of a 401 error.
        :param json_answer: Parse the servers answer as JSON.
        :return: The answer of the server. None in case of an error.
        :raise: URLError in case of an HTTP error. Returns None instead if the 'handle_http_errors' option is set.
        """
        if not self.session_id and auto_login:
            self.login()

        url = self._build_url(path, parameters)
        request = urllib.request.Request(url)
        if json_answer:
            request.add_header("Accept", "application/json")
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
        except urllib.request.HTTPError as e:
            if e.code == 401 and auto_login:
                logging.info("Unauthorized. Trying to log in again.")
                self.session_id = None
                self.login()
                return self.request(path, data=data, method=method, auto_login=False, json_answer=json_answer)
            elif e.code == 403:
                raise NuclosAuthenticationException()
            else:
                logging.error("HTTP Error {}: {}".format(e.code, e.reason))
                raise NuclosHTTPException(e)

    def _build_url(self, path, parameters=None):
        """
        Build an URL for a request to the Nuclos server.

        :param path: The path to request.
        :param parameters: URL parameters.
        :return: The complete server URL.
        """
        if not parameters:
            parameters = {}
        param = "&".join("{}={}".format(str(k), str(parameters[k])) for k in parameters)

        url = "http://{}:{}/{}/rest/{}".format(self.settings.ip, self.settings.port, self.settings.instance, path)
        if param:
            url += "?" + param

        return url


class BusinessObjectMeta:
    def __init__(self, nuclos, bo_meta_id):
        self._nuclos = nuclos
        self.bo_meta_id = bo_meta_id

    @property
    @Cached
    def _data(self):
        return self._nuclos.request(BO_META_ROUTE.format(self.bo_meta_id))

    @property
    def name(self):
        return self._data["name"]

    @property
    def can_update(self):
        return self._data["update"]

    @property
    def can_insert(self):
        return self._data["insert"]

    @property
    def can_delete(self):
        return self._data["delete"]

    @property
    @Cached
    def attributes(self):
        return [AttributeMeta(a) for a in self._data["attributes"].values()]

    def get_attribute(self, bo_attr_id):
        """
        Find the metadata for an attribute of this business object.

        :param bo_attr_id: The attribute id to find.
        :return: A BOMetaAttribute object. None if the attribute does not exist.
        """
        for attr in self.attributes:
            if attr.bo_attr_id == bo_attr_id:
                return attr
        return None

    def get_attribute_by_name(self, name):
        """
        Find the metadata for an attribute of this business object by its name.

        :param name: The name to search for.
        :return: A BOMetaAttribute object. None if the attribute does not exist.
        """
        name = name.lower()

        for attr in self.attributes:
            if attr.name.lower() == name:
                return attr

        # Allow replacing spaces in attribute names by underscores.
        if "_" in name:
            return self.get_attribute_by_name(name.replace("_", " "))
        return None

    def __getattr__(self, name):
        attr = self.get_attribute_by_name(name)
        if attr:
            return attr
        raise AttributeError("Unknown attribute '{}'.".format(name))

    def __getitem__(self, name):
        if isinstance(name, str):
            attr = self.get_attribute_by_name(name)
            if attr:
                return attr
            raise IndexError("Unknown attribute '{}'.".format(name))
        raise TypeError("Invalid argument type.")


class AttributeMeta:
    def __init__(self, data):
        self._data = data

    @property
    def name(self):
        return self._data["name"]

    @property
    def bo_attr_id(self):
        return self._data["bo_attr_id"]

    @property
    def type(self):
        return self._data["type"]

    @property
    def is_writeable(self):
        return not self._data["readonly"]

    @property
    def is_nullable(self):
        return self._data["nullable"]

    @property
    def is_unique(self):
        return self._data["unique"]

    @property
    def is_reference(self):
        return self._data["reference"]


class BusinessObject:
    def __init__(self, nuclos, bo_meta_id):
        self._nuclos = nuclos
        self.bo_meta_id = bo_meta_id

    @property
    @Cached
    def meta(self):
        return BusinessObjectMeta(self._nuclos, self.bo_meta_id)

    def get(self, bo_id=None):
        """
        Get the instance with the given id.

        :param bo_id: The id to load. If it is None, this will create a new instance.
        :return: The business object instance.
        """
        if bo_id is None and not self.meta.can_insert:
            raise NuclosException("Insert of business object {} not allowed.".format(self.meta.name))
        return BusinessObjectInstance(self._nuclos, self, bo_id)

    def list(self, search=None, limit=0, offset=0, sort=None):
        """
        Get a list of instances for this business object.

        :param search: A text to search for.
        :param limit: The maximum number of instances to load.
        :param offset: The number of instances to skip.
        :return: A list of BusinessObjectInstance objects.
        """
        parameters = {}
        if search:
            parameters["search"] = search
        if limit:
            parameters["chunksize"] = limit
        if offset or limit:
            parameters["offset"] = offset
        if sort:
            parameters["sort"] = sort

        data = self._nuclos.request(BO_INSTANCE_LIST_ROUTE.format(self.bo_meta_id), parameters=parameters)

        return [self.get(bo["bo_id"]) for bo in data["bos"]]

    def search(self, text):
        """
        Search for instances which match the given text.

        :param text: The search text.
        :return: A list of instances matching the search text.
        """
        return self.list(search=text)

    def create(self):
        """
        Create a new instance of this business object.

        :return: A business object instance which is new and can be saved to the database.
        """
        return self.get()


class BusinessObjectInstance:
    # TODO: Support getting and setting reference attributes and subforms.
    # TODO: Check metadata for attributes (is_writeable, is_nullable).
    # TODO: Check if required attributes are given.
    # TODO: Support status and process.
    def __init__(self, nuclos, business_object, bo_id=None):
        self._nuclos = nuclos
        self._business_object = business_object
        self._bo_id = bo_id
        self._data = None
        self._deleted = False
        self._updated_attribute_data = {}

        self._initialized = True

    @property
    @Cached
    def _url(self):
        if not self._bo_id:
            raise NuclosException("Attempting to access data of an uninitialized business object instance.")
        return BO_INSTANCE_ROUTE.format(self._business_object.bo_meta_id, self._bo_id)

    @property
    def data(self):
        if not self._bo_id:
            raise NuclosException("Attempting to access data of an uninitialized business object instance.")
        if self._deleted:
            raise NuclosException("Cannot access data of a deleted instance.")
        if not self._data:
            self._data = self._nuclos.request(self._url)
        return self._data

    @property
    def title(self):
        return self.data["_title"]

    def is_new(self):
        return self._bo_id is None

    def refresh(self):
        if self._deleted:
            raise NuclosException("Cannot refresh a deleted instance.")
        self._data = None
        self._updated_attribute_data = {}

    def delete(self):
        """
        Delete this instance.

        :return: True if successful.
        """
        if self._deleted:
            return True
        if self.is_new():
            raise NuclosException("Cannot delete an unsaved instance.")
        if not self._business_object.meta.can_delete:
            raise NuclosException("Deletion of business object {} not allowed.".format(self._business_object.meta.name))
        try:
            self._nuclos.request(self._url, method="DELETE", json_answer=False)
            self._deleted = True
            return True
        except NuclosHTTPException:
            return False

    def save(self):
        """
        Save this instance.

        :return: True if successful.
        """
        if self._deleted:
            raise NuclosException("Cannot save a deleted instance.")
        if not self._updated_attribute_data:
            return True
        if self.is_new():
            # Insert.
            if not self._business_object.meta.can_insert:
                raise NuclosException(
                    "Insert of business object {} not allowed.".format(self._business_object.meta.name))
            try:
                url = BO_INSTANCE_LIST_ROUTE.format(self._business_object.meta.bo_meta_id)
                result = self._nuclos.request(url, data=self._update_data(), method="POST")
                if result:
                    self._bo_id = result["bo_id"]
                    self._data = result
                    self._updated_attribute_data = {}
                    return True
            except NuclosHTTPException:
                return False
        else:
            # Update.
            if not self._business_object.meta.can_update:
                raise NuclosException(
                    "Update of business object {} not allowed.".format(self._business_object.meta.name))
            try:
                result = self._nuclos.request(self._url, data=self._update_data(), method="PUT")
                if result:
                    self._data = result
                    self._updated_attribute_data = {}
                    return True
            except NuclosHTTPException:
                return False
        return False

    def _update_data(self):
        # TODO: Refactor this method.
        # TODO: Change this to use the new format once it is implemented in Nuclos.
        #       See http://www.nuclos.de/de/forum/sonstiges/5348-rest-layout-bzw-bo-meta?start=6#6923
        data = {
            "bo_meta_id": self._business_object.meta.bo_meta_id,
            "bo_values": self._updated_attribute_data
        }
        if self.is_new():
            data["_flag"] = "insert"
        else:
            data["_flag"] = "update"
            data["bo_id"] = self._bo_id
        return data

    def get_attribute(self, bo_attr_id):
        """
        Get the value of an attribute.

        :param bo_attr_id: The attribute id to get the value of.
        :return: The attributes value.
        :raise: AttributeError if the attribute does not exist.
        """
        if bo_attr_id in self._updated_attribute_data:
            # There is unsaved local data for this attribute.
            return self._updated_attribute_data[bo_attr_id]
        elif bo_attr_id in self.data["bo_values"]:
            return self.data["bo_values"][bo_attr_id]
        raise AttributeError("Unknown attribute '{}'.".format(bo_attr_id))

    def get_attribute_by_name(self, name):
        """
        Get the value of an attribute by its name.

        :param name: The name of the attribute to search.
        :return: The attribute value.
        :raise: AttributeError if the attribute does not exist.
        """
        attr = self._business_object.meta.get_attribute_by_name(name)
        if attr:
            return self.get_attribute(attr.bo_attr_id)
        raise AttributeError("Unknown attribute '{}'.".format(name))

    def __getattr__(self, name):
        return self.get_attribute_by_name(name)

    def __getitem__(self, name):
        if isinstance(name, str):
            return self.get_attribute_by_name(name)
        raise TypeError("Invalid argument type.")

    def set_attribute(self, bo_attr_id, value):
        """
        Update an attribute.

        :param bo_attr_id: The attribute to set.
        :param value: The new value of the attribute.
        """
        # TODO: Check for datatypes and similar?
        self._updated_attribute_data[bo_attr_id] = value

    def set_attribute_by_name(self, name, value):
        """
        Update an attribute by its name.

        :param name: The name of the attribute to search.
        :param value: The value to set the attribute to.
        :raise: AttributeError if the attribute does not exist.
        """
        attr = self._business_object.meta.get_attribute_by_name(name)
        if attr:
            return self.set_attribute(attr.bo_attr_id, value)
        raise AttributeError("Unknown attribute '{}'.".format(name))

    def __setattr__(self, name, value):
        if not "_initialized" in self.__dict__ or name in self.__dict__:
            super().__setattr__(name, value)
        else:
            self.set_attribute_by_name(name, value)

    def __setitem__(self, name, value):
        if isinstance(name, str):
            return self.set_attribute_by_name(name, value)
        raise TypeError("Invalid argument type.")

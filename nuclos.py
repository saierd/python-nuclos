"""
Copyright (c) 2014-2021 Daniel Saier

This project is licensed under the terms of the MIT license. See the LICENSE file.
"""
__version__ = "1.7"

# TODO: Support SSL.

import sys

if sys.version_info[0] < 3 or (sys.version_info[0] == 3 and sys.version_info[1] < 3):
    print("This library needs at least Python 3.3!")
    sys.exit(1)

import base64
import collections
import configparser
import functools
import json
import locale
import logging
import os
import shutil
import urllib.request
import urllib.parse

VERSION_ROUTE = "version"
LOGIN_ROUTE = ""
LOGOUT_ROUTE = ""
BO_LIST_ROUTE = "bos"
BO_META_ROUTE = "boMetas/{}"
BO_INSTANCE_LIST_ROUTE = "bos/{}"
BO_INSTANCE_ROUTE = "bos/{}/{}"
BO_DEPENDENCY_LIST_ROUTE = "bos/{}/{}/subBos/{}"
BO_DEPENDENCY_META_ROUTE = "boMetas/{}/subBos/{}"
STATE_CHANGE_ROUTE = "boStateChanges/{}/{}/{}"
DOCUMENT_ROUTE = "boDocuments/{}/{}/documents/{}"

HTTP_PROTOCOL = "http"


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
        if args not in self.cache:
            # noinspection PyArgumentList
            self.cache[args] = self.f(*args)
        return self.cache[args]

    def __get__(self, instance, _):
        return functools.partial(self.__call__, instance)


class NuclosException(Exception):
    pass


class NuclosValueException(NuclosException):
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
    def __init__(self, setting_file):
        """
        :param setting_file: The setting file to use.
        """
        self.settings = NuclosSettings(setting_file)
        self.session_id = None

        self.bo_namespaces = []

    @property
    @Cached
    def version(self):
        return self.request(VERSION_ROUTE, auto_login=False, json_answer=False)

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
        if not self.require_version(4, 7):
            raise NuclosVersionException("You need at least Nuclos 4.7 to use this version of the REST API.")

        login_data = {
            "username": self.settings.username,
            "password": self.settings.password,
            "locale": self.settings.locale
        }

        answer = self.request(LOGIN_ROUTE, data=login_data, auto_login=False)
        if answer:
            self.session_id = answer["sessionId"]
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
        if answer is not None:
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
                    return bo["boMetaId"]

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
                if bo["boMetaId"] == bo_meta_id:
                    return True
        return False

    @Cached
    def get_business_object(self, bo_meta_id, check_existence=True):
        """
        Get a business object by its meta id.

        :param bo_meta_id: The meta id of the business object to find.
        :param check_existence: Whether to check if the requested business object exists.
        :return: A BusinessObject object. None if the business object does not exist.
        """
        if not check_existence or self._bo_meta_id_exists(bo_meta_id):
            return BusinessObject(self, bo_meta_id)
        return None

    def add_business_object_namespace(self, namespace):
        """
        Add a (Java/Nuclet) namespace in which we search for business objects. This is a workaround
        for some versions of Nuclos which don't properly include the business object names for all
        business ojects in the meta data.

        :param namespace: The Java/Nuclet namespace as is it used by the Nuclos REST API
                          (e.g. `com.company` should be specified as `com_company`).
        """
        self.bo_namespaces.append(namespace)

    def get_business_object_by_name(self, name):
        """
        Get a business object by its name.

        :param name: The name of the business object to find.
        :return: A BusinessObject object. None if the business object does not exist.
        """
        bo_meta_id = self._get_bo_meta_id(name)
        if bo_meta_id:
            return self.get_business_object(bo_meta_id)

        # Try to guess the business object from Nuclet namespaces. This is a workaround for a Nuclos
        # bug, see the the add_business_object_namespace method above.
        for namespace in self.bo_namespaces:
            for name in [name, name.capitalize()]:
                candidate_meta_id = namespace + "_" + name
                if self._bo_meta_id_exists(candidate_meta_id):
                    return self.get_business_object(candidate_meta_id)

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
        return [self.get_business_object(bo["boMetaId"]) for bo in self._business_objects]

    def request(self, path, parameters=None, data=None, method=None, auto_login=True, json_answer=True, filename=None):
        """
        Send a request to the Nuclos server.

        :param path: The path to open.
        :param parameters: A dictionary of parameters to add to the request URL.
        :param data: The data to add. If this is given the request will automatically be a POST request.
        :param method: The HTTP method to use. If not set this will be GET or POST, depending on the data.
        :param auto_login: Try to log in automatically in case of a 401 error.
        :param json_answer: Parse the servers answer as JSON.
        :param filename: A file to save the downloaded data in.
        :return: The answer of the server. None in case of an error.
        :raise: URLError in case of an HTTP error. Returns None instead if the 'handle_http_errors' option is set.
        """
        if not self.session_id and auto_login:
            self.login()

        url = path
        if url.startswith("//"):
            url = HTTP_PROTOCOL + ":" + url
        if not url.startswith(HTTP_PROTOCOL):
            url = self._build_url(path, parameters)
        request = urllib.request.Request(url)
        if json_answer:
            request.add_header("Accept", "application/json")
        if data:
            request.data = json.dumps(data).encode("utf-8")
            request.add_header("Content-Type", "application/json")
        if method:
            request.method = method
        if method and request.data and method not in ["POST", "PUT"]:
            logging.warning("Overriding the POST method while sending data!")
        if self.session_id:
            request.add_header("Cookie", "JSESSIONID=" + str(self.session_id))

        logging.debug("Sending {} request to {}.".format(request.get_method(), request.get_full_url()))
        if request.data:
            logging.debug("Sending data {}.".format(request.data))

        try:
            result = urllib.request.urlopen(request)

            if filename is not None:
                with open(filename, "wb") as f:
                    shutil.copyfileobj(result, f)
                    return None

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

    def download_file(self, path, filename):
        return self.request(path, json_answer=False, filename=filename)

    def _build_url(self, path, parameters=None):
        """
        Build an URL for a request to the Nuclos server.

        :param path: The path to request.
        :param parameters: URL parameters.
        :return: The complete server URL.
        """

        def quote_all(s):
            return urllib.parse.quote(s, safe="")

        def quote(s):
            return urllib.parse.quote(s)

        if not parameters:
            parameters = {}
        param = "&".join("{}={}".format(quote_all(str(k)), quote_all(str(parameters[k]))) for k in parameters)

        if not path.startswith("/"):
            path = "/" + path

        url = "{}://{}:{}/{}/rest{}".format(HTTP_PROTOCOL, quote(self.settings.ip), self.settings.port,
                                              quote(self.settings.instance), quote(path))
        if param:
            url += "?" + param

        return url


class BusinessObjectMeta:
    def __init__(self, nuclos, bo_meta_id):
        self._nuclos = nuclos
        self.bo_meta_id = bo_meta_id

    @property
    def nuclos(self):
        return self._nuclos

    @property
    @Cached
    def _data(self):
        return self._nuclos.request(BO_META_ROUTE.format(self.bo_meta_id))

    @property
    def name(self):
        return self._data["name"]

    @property
    def can_update(self):
        # TODO: This data is currently not available.
        return True

    @property
    def can_insert(self):
        # TODO: This data is currently not available.
        return True

    @property
    def can_delete(self):
        # TODO: This data is currently not available.
        return True

    @property
    @Cached
    def attributes(self):
        return [AttributeMeta(self, a) for a in self._data["attributes"].values()]

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
    def __init__(self, business_object, data):
        self._business_object = business_object
        self._data = data

    @property
    def name(self):
        return self._data["name"]

    @property
    def bo_attr_id(self):
        return self._data["boAttrId"]

    def data_index(self):
        """
        :return: The key of the data dictionary used for this attribute.
        """
        data_index = self.bo_attr_id
        if data_index.startswith(self._business_object.bo_meta_id):
            data_index = data_index[len(self._business_object.bo_meta_id) + 1:]

        return data_index

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

    @property
    def is_document(self):
        return self.type.lower() == "document"

    @property
    def _referenced_bo_id(self):
        return self._data["referencingBoMetaId"]

    def referenced_bo(self):
        return self._business_object.nuclos.get_business_object(self._referenced_bo_id)


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

    def list(self, search=None, offset=0, limit=0, sort=None, where=None, fetch_all=False):
        """
        Get a result of instances for this business object.

        :param search: A text to search for.
        :param offset: The number of instances to skip.
        :param limit: The maximum number of instances to load.
        :param sort: An attribute (or the name of an attribute) to sort by.
        :param where: A query string to filter the attributes.
        :param fetch_all: Whether all instances should be fetched.
        :return: A result of BusinessObjectInstance objects.
        """
        if fetch_all:
            # Get at least 100 items at once when fetching all instances.
            limit = max(limit, 100)

        parameters = {}
        if search is not None:
            parameters["search"] = search
        if limit:
            parameters["chunksize"] = limit
        if offset or limit:
            parameters["offset"] = offset
        current_offset = offset

        # TODO: Allow multiple sort arguments and decreasing sorts.
        if sort is not None:
            # Allow to give a name of an attribute for sorting.
            if isinstance(sort, str):
                attr = self.meta.get_attribute_by_name(sort)
                if attr:
                    sort = attr

            if isinstance(sort, AttributeMeta):
                parameters["orderBy"] = sort.bo_attr_id
            else:
                parameters["orderBy"] = sort

        if where is not None:
            parameters["where"] = where

        result = []

        while True:
            data = self._nuclos.request(BO_INSTANCE_LIST_ROUTE.format(self.bo_meta_id), parameters=parameters)
            result.extend([self.get(bo["boId"]) for bo in data["bos"]])

            if not fetch_all or data["all"]:
                break

            current_offset += limit + 1
            parameters["offset"] = current_offset

        return result

    def list_all(self, **kwargs):
        """
        Get a list of all instances.

        :param kwargs: Other arguments the list method accepts.
        :return: A list of all instances matching the
        """
        return self.list(fetch_all=True, **kwargs)

    def get_one(self, *args, **kwargs):
        """
        Get the first list element.

        :param args: Arguments which the list method accepts.
        :param kwargs: Arguments which the list method accepts.
        :return: The first instance found or None if there is none.
        """
        result = self.list(*args, **kwargs)
        if result:
            return result[0]
        return None

    def search(self, text, **kwargs):
        """
        Search for instances which match the given text.

        :param text: The search text.
        :param kwargs: Other arguments the list method accepts.
        :return: A list of instances matching the search text.
        """
        return self.list(search=text, **kwargs)

    def search_all(self, text, **kwargs):
        """
        Search for all instances which match the given text.

        :param text: The search text.
        :param kwargs: Other arguments the list method accepts.
        :return: A list of instances matching the search text.
        """
        return self.list_all(search=text, **kwargs)

    def search_one(self, text, **kwargs):
        """
        Find a single instance.

        :param text: The search text.
        :param kwargs: Other arguments the list method accepts.
        :return: The instance found or None if there is no result.
        """
        result = self.search(text, **kwargs)
        if result:
            return result[0]
        return None

    def create(self):
        """
        Create a new instance of this business object.

        :return: A business object instance which is new and can be saved to the database.
        """
        return self.get()


class BusinessObjectInstance:
    # TODO: Call business rules.
    # TODO: Generators.
    def __init__(self, nuclos, business_object, bo_id=None):
        self._nuclos = nuclos
        self._business_object = business_object
        self._bo_id = bo_id
        self._data = None
        self._deleted = False
        self._updated_attribute_data = {}

        self._initialized = True

    @property
    def _url(self):
        if not self._bo_id:
            raise NuclosException("Attempting to access data of an uninitialized business object instance.")
        return BO_INSTANCE_ROUTE.format(self._business_object.bo_meta_id, self._bo_id)

    @property
    def meta(self):
        return self._business_object.meta

    @property
    def id(self):
        return self._bo_id

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
    def _is_initialized(self):
        return self._data is not None

    @property
    def title(self):
        return self.data["title"]

    @property
    def current_state_name(self):
        try:
            return self.data["attributes"]["nuclosState"]["name"]
        except IndexError:
            return None

    @property
    def current_state_number(self):
        try:
            return self.data["attributes"]["nuclosStateNumber"]
        except IndexError:
            return None

    def _get_state_id(self, number):
        def number_for_state(state):
            # Older versions of the REST API include the state number in the JSON data.
            if "number" in state:
                return state["number"]
            
            # Newer versions don't contain it anymore. Try to extract the number from the ID.
            state_id = state["nuclosStateId"]
            state_number = state_id[state_id.rindex("_") + 1:]
            if state_number.isdigit():
                return int(state_number)
            
            return None

        for next_state in self.data["nextStates"]:
            if number_for_state(next_state) == number:
                return next_state["nuclosStateId"]
        raise NuclosValueException("Unknown state '{}'.".format(number))

    def _get_state_id_by_name(self, name):
        name = name.lower()

        for next_state in self.data["nextStates"]:
            if next_state["name"].lower() == name:
                return next_state["nuclosStateId"]
        raise NuclosValueException("Unknown state '{}'.".format(name))

    def _change_to_state(self, state_id):
        url = STATE_CHANGE_ROUTE.format(self._business_object.bo_meta_id, self.id, state_id)
        self._nuclos.request(url, json_answer=False)

        self.refresh()

    def change_to_state(self, number):
        """
        Change the current state to another one given by its number. This will refresh the instance, unsaved changes
        will be discarded.

        :param number: The number of the state.
        """
        self._change_to_state(self._get_state_id(number))

    def change_to_state_by_name(self, name):
        """
        Change the current state to another one given by its name. This will refresh the instance, unsaved changes
        will be discarded.

        :param name: The name of the state.
        """
        self._change_to_state(self._get_state_id_by_name(name))

    @property
    def process(self):
        if "nuclosProcess" in self._updated_attribute_data:
            return self._updated_attribute_data["nuclosProcess"]["name"]

        try:
            return self.data["attributes"]["nuclosProcess"]["name"]
        except IndexError:
            return None

    def set_process(self, name):
        process_id = self._business_object.bo_meta_id + "_" + name.replace(" ", "")

        self._updated_attribute_data["nuclosProcess"] = {
            "id": process_id,
            "name": name
        }

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
            raise NuclosAuthenticationException(
                "Deletion of business object {} not allowed.".format(self._business_object.meta.name))
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
                raise NuclosAuthenticationException(
                    "Insert of business object {} not allowed.".format(self._business_object.meta.name))
            try:
                url = BO_INSTANCE_LIST_ROUTE.format(self._business_object.meta.bo_meta_id)
                result = self._nuclos.request(url, data=self._update_data(), method="POST")
                if result:
                    self._bo_id = result["boId"]
                    self._data = result
                    self._updated_attribute_data = {}
                    return True
            except NuclosHTTPException:
                return False
        else:
            # Update.
            if not self._business_object.meta.can_update:
                raise NuclosAuthenticationException(
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
        """
        :return: The data to send to the server in order to update this instance.
        """
        data = {
            "boMetaId": self._business_object.meta.bo_meta_id,
            "attributes": self._updated_attribute_data
        }
        if self.is_new():
            data["_flag"] = "insert"
        else:
            data["_flag"] = "update"
            data["boId"] = self._bo_id
            data["version"] = self.data["version"]
        return data

    def download_document_by_id(self, bo_attr_id, filename=None):
        """
        Download a file.

        :param bo_attr_id: The id of the document attribute.
        :param filename: The path where the file should be saved to.
        """
        if filename is None:
            filename = self.get_attribute(bo_attr_id)

        url = DOCUMENT_ROUTE.format(self.meta.bo_meta_id, self.id, bo_attr_id)
        return self._nuclos.download_file(url, filename)

    def download_document(self, name, filename=None):
        """
        Download a file.

        :param name: The name of the document attribute.
        :param filename: The path where the file should be saved to.
        """
        attr = self._business_object.meta.get_attribute_by_name(name)
        if attr:
            return self.download_document_by_id(attr.bo_attr_id, filename)
        raise AttributeError("Unknown attribute '{}'.".format(name))

    def _dependency_list_url(self, dependency_id):
        if not self._bo_id:
            raise NuclosException("Attempting to access data of an uninitialized business object instance.")
        return BO_DEPENDENCY_LIST_ROUTE.format(self.meta.bo_meta_id, self.id, dependency_id)

    @property
    @Cached
    def _dependency_metas(self):
        deps = self.data["subBos"]
        metas = {}

        for dep in deps:
            metas[dep] = self._nuclos.request(deps[dep]["links"]["boMeta"]["href"])

        return metas

    def _get_dependency_meta(self, dependency_id):
        if dependency_id in self._dependency_metas:
            return self._dependency_metas[dependency_id]
        raise AttributeError("Unknown dependency '{}'.".format(dependency_id))

    def _get_dependency_id_by_name(self, name):
        name = name.lower()

        for dep in self._dependency_metas:
            if self._get_dependency_meta(dep)["name"].lower() == name:
                return dep

        # Allow replacing spaces in attribute names by underscores.
        if "_" in name:
            return self._get_dependency_id_by_name(name.replace("_", " "))
        return None

    def _get_dependency_bo(self, dependency_id):
        meta = self._get_dependency_meta(dependency_id)
        referenced_bo_id = meta["boMetaId"]
        return self._nuclos.get_business_object(referenced_bo_id, False)

    def create_dependency(self, dependency_id):
        """
        Create a new dependent instance.

        :param dependency_id: The id of the dependency.
        :return: A new instance.
        """
        dependency_bo = self._get_dependency_bo(dependency_id)
        ref_attr_id = self._get_dependency_meta(dependency_id)["refAttrId"]

        new_bo = dependency_bo.create()
        new_bo.set_attribute(ref_attr_id, self)
        return new_bo

    def create_dependency_by_name(self, name):
        """
        Create a new dependent instance.

        :param name: The name of the dependent business object.
        :return: A new instance.
        """
        dependency_id = self._get_dependency_id_by_name(name)
        if dependency_id is not None:
            return self.create_dependency(dependency_id)
        raise AttributeError("Unknown dependency '{}'.".format(name))

    def get_dependencies(self, dependency_id):
        """
        Get a list of referenced business objects.

        :param dependency_id: The id of the dependency.
        :return: A list of referenced business objects.
        """
        dependency_bo = self._get_dependency_bo(dependency_id)

        refs = self._nuclos.request(self._dependency_list_url(dependency_id))
        return [BusinessObjectInstance(self._nuclos, dependency_bo, bo["boId"]) for bo in refs["bos"]]

    def get_dependencies_by_name(self, name):
        """
        Get a list of dependent business objects by its name.

        :param name: The name of the dependent business object.
        :return: A list of referenced business objects.
        """
        dependency_id = self._get_dependency_id_by_name(name)
        if dependency_id is not None:
            return self.get_dependencies(dependency_id)
        raise AttributeError("Unknown dependency '{}'.".format(name))

    def get_attribute(self, bo_attr_id):
        """
        Get the value of an attribute.

        :param bo_attr_id: The id of the attribute we want to get the value of.
        :return: The attribute's value.
        :raise: AttributeError if the attribute does not exist.
        """
        attr = self._business_object.meta.get_attribute(bo_attr_id)
        if attr is None:
            raise AttributeError("Unknown attribute '{}'.".format(bo_attr_id))

        data_index = attr.data_index()

        if data_index in self._updated_attribute_data:
            # There is unsaved local data for this attribute.
            data = self._updated_attribute_data[data_index]
        elif data_index in self.data["attributes"]:
            data = self.data["attributes"][data_index]
        else:
            # The attribute is null.
            if attr.type == "Boolean":
                return False
            return None

        if attr.is_document and data is not None:
            return data["name"]
        elif attr.is_reference:
            if data is not None and data["id"] is not None:
                return attr.referenced_bo().get(data["id"])
            return None
        return data

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
        # Allow creation of dependent objects with instance.create_<name>()
        if name.startswith("create_"):
            cname = name[7:]
            if not self._get_dependency_id_by_name(cname) is None:
                def create_dependency():
                    return self.create_dependency_by_name(cname)

                return create_dependency

        try:
            return self.get_attribute_by_name(name)
        except AttributeError as e:
            try:
                return self.get_dependencies_by_name(name)
            except AttributeError:
                raise e

    def __getitem__(self, name):
        if isinstance(name, str):
            try:
                return self.get_attribute_by_name(name)
            except AttributeError as e:
                try:
                    return self.get_dependencies_by_name(name)
                except AttributeError:
                    raise e
        raise TypeError("Invalid argument type.")

    def set_attribute(self, bo_attr_id, value):
        """
        Update an attribute.

        :param bo_attr_id: The attribute to set.
        :param value: The new value of the attribute.
        """
        attr = self._business_object.meta.get_attribute(bo_attr_id)
        if attr is None:
            raise AttributeError("Unknown attribute '{}'.".format(bo_attr_id))

        if not attr.is_writeable:
            raise NuclosAuthenticationException("Attribute '{}' is not writeable.".format(attr.name))

        if value is None and not attr.is_nullable:
            raise NuclosAuthenticationException("Attribute '{}' is not nullable.".format(attr.name))

        if attr.is_document:
            # The attribute is a file.
            # Care: this case must be first, because document attributes are also marked as references.
            if value is not None:
                filename = value

                encoded_file = ""
                with open(filename, "rb") as f:
                    encoded_file = base64.b64encode(f.read()).decode("utf-8")

                value = {
                    "data": encoded_file,
                    "name": os.path.basename(filename)
                }
        elif attr.is_reference:
            if value is None:
                value = {
                    "id": None,
                    "name": ""
                }
            else:
                if not isinstance(value, BusinessObjectInstance):
                    raise NuclosValueException("Wrong value for reference attribute '{}'.".format(attr.name))
                if attr.referenced_bo().bo_meta_id != value._business_object.bo_meta_id:
                    raise NuclosValueException(
                        "Wrong value for reference attribute '{}', expected a business object of type '{}'.".format(
                            attr.name, attr.referenced_bo().bo_meta_id))

                value = {
                    "id": value.id,
                    "name": value.title
                }
        elif attr.type == "String" and not isinstance(value, str):
            # Don't convert None to "None".
            if value is not None:
                value = str(value)

        # TODO: Check whether the data type is correct.
        self._updated_attribute_data[attr.data_index()] = value

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
        if "_initialized" not in self.__dict__ or name in self.__dict__:
            super().__setattr__(name, value)
        else:
            self.set_attribute_by_name(name, value)

    def __setitem__(self, name, value):
        if isinstance(name, str):
            return self.set_attribute_by_name(name, value)
        raise TypeError("Invalid argument type.")

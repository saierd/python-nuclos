import os
import sys
import unittest

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from nuclos import (
    NuclosAPI,
    AttributeMeta,
    BusinessObject,
    BusinessObjectInstance,
    BusinessObjectMeta,
    NuclosException,
)

NUCLOS_VERSION_MAJOR = 4
NUCLOS_VERSION_MINOR = 20
NUCLOS_VERSION_REVISION = 1

# Note: We give most of the tests a number to make sure they are executed in the same order as they are specified. This
#       might not be the best practice but it is very convenient in this case, as the tests heavily depend on the
#       database content on the Nuclos server. Setting it up separately for every test seems to be unnecessary and not
#       very efficient.


class NuclosTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.nuclos = NuclosAPI("test.ini")


class TestConnection(NuclosTest):
    def test_version(self):
        self.assertEqual(
            self.nuclos.version,
            "{}.{}.{}".format(
                NUCLOS_VERSION_MAJOR, NUCLOS_VERSION_MINOR, NUCLOS_VERSION_REVISION
            ),
        )

    def test_require_version(self):
        self.assertTrue(
            self.nuclos.require_version(NUCLOS_VERSION_MAJOR, NUCLOS_VERSION_MINOR)
        )
        self.assertTrue(
            self.nuclos.require_version(
                NUCLOS_VERSION_MAJOR, NUCLOS_VERSION_MINOR, NUCLOS_VERSION_REVISION
            )
        )

        self.assertFalse(
            self.nuclos.require_version(
                NUCLOS_VERSION_MAJOR, NUCLOS_VERSION_MINOR, NUCLOS_VERSION_REVISION + 1
            )
        )
        self.assertFalse(
            self.nuclos.require_version(NUCLOS_VERSION_MAJOR, NUCLOS_VERSION_MINOR + 1)
        )

    def test_00_logout_without_login(self):
        self.assertIsNone(self.nuclos.session_id)
        self.assertTrue(self.nuclos.logout())
        self.assertIsNone(self.nuclos.session_id)

    def test_01_login(self):
        self.assertIsNone(self.nuclos.session_id)
        self.nuclos.login()
        self.assertIsNotNone(self.nuclos.session_id)

    def test_02_logout(self):
        self.assertIsNotNone(self.nuclos.session_id)
        self.assertTrue(self.nuclos.logout())
        self.assertIsNone(self.nuclos.session_id)

    def test_03_reconnect(self):
        self.nuclos.login()

        self.assertIsNotNone(self.nuclos.session_id)
        self.nuclos.reconnect()
        self.assertIsNone(self.nuclos.session_id)

    def test_04_auto_login(self):
        # Should automatically get logged in when accessing data.
        self.assertIsNone(self.nuclos.session_id)
        _ = self.nuclos.business_objects
        self.assertIsNotNone(self.nuclos.session_id)


class TestBusinessObjects(NuclosTest):
    def test_list(self):
        bos = self.nuclos.business_objects

        for bo in bos:
            self.assertIsInstance(bo, BusinessObject)

        # Filter out business objects from Nuclos itself
        bos = [bo for bo in bos if not bo.bo_meta_id.startswith("org_nuclos")]

        # Then there should be two objects left (customers and orders).
        self.assertEqual(len(bos), 2)

    def test_business_object_retrieval(self):
        self.assertIsInstance(self.nuclos.customer, BusinessObject)
        self.assertIsInstance(self.nuclos["customer"], BusinessObject)
        self.assertIsInstance(
            self.nuclos.get_business_object_by_name("customer"), BusinessObject
        )

        self.assertRaises(AttributeError, lambda: self.nuclos.non_existent_bo)
        self.assertRaises(IndexError, lambda: self.nuclos["non_existent_bo"])
        self.assertIsNone(self.nuclos.get_business_object_by_name("non_existent_bo"))

        self.assertRaises(TypeError, lambda: self.nuclos[0])


class TestBusinessObjectInstances(NuclosTest):
    def test_00_remove_all_data(self):
        for c in self.nuclos.customer.list_all():
            c.delete()
        for o in self.nuclos.order.list_all():
            o.delete()

    def test_01_empty_list(self):
        self.assertEqual(len(self.nuclos.customer.list()), 0)
        self.assertEqual(len(self.nuclos.customer.list_all()), 0)

        self.assertIsNone(self.nuclos.customer.get_one())

    def test_02_insertion(self):
        john_doe = self.nuclos.customer.create()
        john_doe.name = "John Doe"
        john_doe.email = "john@doe.com"
        john_doe.set_process("Business Client")
        john_doe.save()

        self.assertEqual(len(self.nuclos.customer.list_all()), 1)

        jane_doe = self.nuclos.customer.create()
        jane_doe.name = "Jane Doe"
        jane_doe.email = "jane@doe.com"
        jane_doe.save()

        self.assertEqual(len(self.nuclos.customer.list_all()), 2)

    def test_03_list(self):
        self.assertEqual(len(self.nuclos.customer.list()), 2)
        self.assertEqual(len(self.nuclos.customer.list_all()), 2)

        # Get one.
        self.assertIsInstance(self.nuclos.customer.get_one(), BusinessObjectInstance)
        self.assertIsNotNone(self.nuclos.customer.get_one())

        # Limit parameter.
        self.assertEqual(len(self.nuclos.customer.list(limit=0)), 2)
        self.assertEqual(len(self.nuclos.customer.list(limit=1)), 1)
        self.assertEqual(len(self.nuclos.customer.list(limit=2)), 2)

        # Unsorted.
        unsorted_list = self.nuclos.customer.list_all()
        self.assertCountEqual([c.name for c in unsorted_list], ["John Doe", "Jane Doe"])

        # Sort by attribute.
        sorted_list = self.nuclos.customer.list_all(
            sort=self.nuclos.customer.meta.email
        )
        self.assertEqual(sorted_list[0].name, "Jane Doe")
        self.assertEqual(sorted_list[1].name, "John Doe")

        # Sort by attribute given as a string.
        sorted_list = self.nuclos.customer.list_all(sort="email")
        self.assertEqual(sorted_list[0].name, "Jane Doe")
        self.assertEqual(sorted_list[1].name, "John Doe")

        # Where.
        where_expression = "{} = 'John Doe'".format(
            self.nuclos.customer.meta["name"].bo_attr_id
        )
        where_list = self.nuclos.customer.list_all(where=where_expression)
        self.assertEqual(len(where_list), 1)
        self.assertEqual(where_list[0].name, "John Doe")

    def test_04_search(self):
        search_list = self.nuclos.customer.search_all("John")
        self.assertEqual(len(search_list), 1)
        self.assertEqual(search_list[0].name, "John Doe")

        search_list = self.nuclos.customer.search("Jane")
        self.assertEqual(len(search_list), 1)
        self.assertEqual(search_list[0].name, "Jane Doe")

        # Search one.
        self.assertIsInstance(
            self.nuclos.customer.search_one("John"), BusinessObjectInstance
        )
        self.assertIsNone(self.nuclos.customer.search_one("Bob"))

        # No result.
        self.assertEqual(len(self.nuclos.customer.search("Bob")), 0)
        self.assertIsNone(self.nuclos.customer.search_one("Bob"))

    def test_05_delete(self):
        jane = self.nuclos.customer.search_one("Jane")

        self.assertTrue(jane.delete())
        self.assertEqual(len(self.nuclos.customer.list_all()), 1)

        # Deleting twice should not be a problem.
        self.assertTrue(jane.delete())

        # Deleting an unsaved instance should not be possible.
        new_customer = self.nuclos.customer.create()
        self.assertRaises(NuclosException, new_customer.delete)

        # Saving a deleted instance should not be possible.
        self.assertRaises(NuclosException, jane.save)

    def test_06_title(self):
        self.assertEqual(self.nuclos.customer.search_one("John").title, "John Doe")

    def test_07_attributes(self):
        john = self.nuclos.customer.search_one("John")

        self.assertEqual(john.name, "John Doe")
        self.assertEqual(john["name"], "John Doe")
        self.assertEqual(john.get_attribute_by_name("name"), "John Doe")

        self.assertRaises(AttributeError, lambda: john.non_existent_attribute)
        self.assertRaises(AttributeError, lambda: john["non_existent_attribute"])
        self.assertRaises(
            AttributeError, lambda: john.get_attribute_by_name("non_existent_attribute")
        )

        self.assertRaises(TypeError, lambda: john[0])

    def test_08_changing_attributes(self):
        john = self.nuclos.customer.search_one("John")

        john.name = "Bob"
        self.assertEqual(john.name, "Bob")

        john.save()

        bob = self.nuclos.customer.search_one("John")
        self.assertEqual(bob.name, "Bob")

        bob["name"] = "John Doe"
        bob.set_attribute_by_name("name", "John Doe")
        bob.save()

        with self.assertRaises(AttributeError):
            john.non_existent_attribute = 1
        with self.assertRaises(AttributeError):
            john["non_existent_attribute"] = 1
        with self.assertRaises(AttributeError):
            john.set_attribute_by_name("non_existent_attribute", 1)

    def test_09_refresh(self):
        john = self.nuclos.customer.search_one("John")
        john.name = "Bob"
        john.refresh()

        self.assertEqual(john.name, "John Doe")

    def test_10_reference_attributes(self):
        john = self.nuclos.customer.search_one("John")

        new_order = self.nuclos.order.create()
        new_order.number = "ORD001"
        new_order.customer = john
        new_order.save()

        self.assertIsInstance(new_order.customer, BusinessObjectInstance)

        self.assertEqual(len(self.nuclos.order.list_all()), 1)
        order = self.nuclos.order.get_one()
        self.assertIsInstance(order.customer, BusinessObjectInstance)
        self.assertEqual(order.customer.name, "John Doe")

    def test_11_create_subform_instance(self):
        john = self.nuclos.customer.search_one("John")

        new_order = john.create_order()
        self.assertIsInstance(new_order, BusinessObjectInstance)

        new_order.number = "ORD002"
        new_order.customer = john
        new_order.save()

        self.assertEqual(len(self.nuclos.order.list_all()), 2)

        new_order = john.create_dependency_by_name("order")
        self.assertIsInstance(new_order, BusinessObjectInstance)

    def test_12_subforms(self):
        john = self.nuclos.customer.search_one("John")

        johns_orders = john.order
        self.assertIsInstance(johns_orders, list)
        self.assertEqual(len(johns_orders), 2)
        self.assertIsInstance(johns_orders[0], BusinessObjectInstance)
        self.assertCountEqual([o.number for o in johns_orders], ["ORD001", "ORD002"])

        self.assertEqual(len(john["order"]), 2)
        self.assertEqual(len(john.get_dependencies_by_name("order")), 2)

        self.assertRaises(
            AttributeError,
            lambda: john.get_dependencies_by_namee("non_existent_dependency"),
        )

    def test_13_state(self):
        john = self.nuclos.customer.search_one("John")

        self.assertEqual(john.current_state_number, 10)
        self.assertEqual(john.current_state_name, "Active")

        john.change_to_state(99)
        self.assertEqual(john.current_state_number, 99)
        self.assertEqual(john.current_state_name, "Inactive")

        john.save()

        john = self.nuclos.customer.search_one("John")
        self.assertEqual(john.current_state_number, 99)
        self.assertEqual(john.current_state_name, "Inactive")

        john.change_to_state_by_name("Active")
        self.assertEqual(john.current_state_number, 10)
        self.assertEqual(john.current_state_name, "Active")

        john.save()

        john = self.nuclos.customer.search_one("John")
        self.assertEqual(john.current_state_number, 10)
        self.assertEqual(john.current_state_name, "Active")

    def test_14_process(self):
        john = self.nuclos.customer.search_one("John")

        self.assertEqual(john.process, "Business Client")

        john.set_process("Individual Client")
        self.assertEqual(john.process, "Individual Client")

        john.save()

        john = self.nuclos.customer.search_one("John")
        self.assertEqual(john.process, "Individual Client")


class TestMetaData(NuclosTest):
    def test_business_object_meta(self):
        customer_meta = self.nuclos.customer.meta

        self.assertIsInstance(customer_meta, BusinessObjectMeta)
        self.assertEqual(customer_meta.name, "Customer")
        self.assertIsInstance(customer_meta.bo_meta_id, str)

        self.assertTrue(customer_meta.can_delete)
        self.assertTrue(customer_meta.can_insert)
        self.assertTrue(customer_meta.can_update)

        john = self.nuclos.customer.search_one("John")
        self.assertIsInstance(john.meta, BusinessObjectMeta)

    def test_attribute_meta(self):
        customer_meta = self.nuclos.customer.meta

        self.assertIsInstance(customer_meta.email, AttributeMeta)
        self.assertIsInstance(customer_meta["email"], AttributeMeta)
        self.assertIsInstance(
            customer_meta.get_attribute_by_name("email"), AttributeMeta
        )

        self.assertRaises(AttributeError, lambda: customer_meta.non_existent_attribute)
        self.assertRaises(IndexError, lambda: customer_meta["non_existent_attribute"])
        self.assertIsNone(customer_meta.get_attribute_by_name("non_existent_attribute"))

        self.assertRaises(TypeError, lambda: customer_meta[0])

        # Attribute list.
        self.assertIsInstance(customer_meta.attributes, list)
        attribute_names = [a.name for a in customer_meta.attributes]
        for attr in ["Name", "Email"]:
            self.assertIn(attr, attribute_names)

        self.assertEqual(customer_meta.email.name, "Email")
        self.assertIsInstance(customer_meta.email.bo_attr_id, str)
        self.assertEqual(customer_meta.email.type, "String")
        self.assertTrue(customer_meta.email.is_nullable)
        self.assertFalse(customer_meta.email.is_reference)
        self.assertFalse(customer_meta.email.is_unique)
        self.assertTrue(customer_meta.email.is_writeable)

        # Reference attribute.
        self.assertTrue(self.nuclos.order.meta.customer.is_reference)
        self.assertIsInstance(
            self.nuclos.order.meta.customer.referenced_bo(), BusinessObject
        )


if __name__ == "__main__":
    unittest.main()

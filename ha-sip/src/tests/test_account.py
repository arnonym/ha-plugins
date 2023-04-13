import unittest
from account import Account


class AccountTest(unittest.TestCase):
    def test_is_number_in_list(self):
        self.assertEqual(Account.is_number_in_list(None, ["12345"]), False)
        self.assertEqual(Account.is_number_in_list(None, []), False)
        self.assertEqual(Account.is_number_in_list("12345", []), False)
        self.assertEqual(Account.is_number_in_list("12345", ["12345"]), True)
        self.assertEqual(Account.is_number_in_list("1234", ["12345"]), False)
        self.assertEqual(Account.is_number_in_list("123456", ["1234{*}"]), True)
        self.assertEqual(Account.is_number_in_list("123456", ["1234{?}"]), False)
        self.assertEqual(Account.is_number_in_list("12345", ["1234{?}"]), True)
        self.assertEqual(Account.is_number_in_list("12345", ["1{*}5"]), True)
        self.assertEqual(Account.is_number_in_list("12345", ["12{?}45"]), True)
        self.assertEqual(Account.is_number_in_list("12345", ["{*}45"]), True)
        self.assertEqual(Account.is_number_in_list("12345", ["{?}345"]), False)
        self.assertEqual(Account.is_number_in_list("12345", ["{?}2345"]), True)
        self.assertEqual(Account.is_number_in_list("**620", ["**620"]), True)
        self.assertEqual(Account.is_number_in_list("**620", ["**{*}"]), True)

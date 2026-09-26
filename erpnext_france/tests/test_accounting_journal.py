import unittest

import frappe
from frappe.utils import getdate

from erpnext_france.tests.utils import (
	french_company,
	other_company,
	pay,
	submitted_purchase_invoice,
	test_supplier,
)


class TestAccountingJournal(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		cls.company = french_company()

	def test_gl_entries_link_to_an_existing_journal(self):
		"""Since journals are named `{journal_code}-{company}`, GL entries must store the name."""
		pi = submitted_purchase_invoice(self.company)
		journals = frappe.get_all(
			"GL Entry", filters={"voucher_no": pi.name, "is_cancelled": 0}, pluck="accounting_journal"
		)
		self.assertTrue(journals)
		for journal in journals:
			self.assertTrue(frappe.db.exists("Accounting Journal", journal), journal)

	def fec_rows(self, voucher_no):
		from importlib import import_module

		fec = import_module(
			"erpnext_france.erpnext_france.report.fichier_des_ecritures_comptables_[fec]."
			"fichier_des_ecritures_comptables_[fec]"
		)
		fiscal_year = frappe.db.get_value(
			"Fiscal Year",
			{"year_start_date": ("<=", getdate()), "year_end_date": (">=", getdate())},
			["name", "year_start_date", "year_end_date"],
			as_dict=True,
		)
		return [
			row
			for row in fec.get_result(
				self.company, fiscal_year.name, fiscal_year.year_start_date, fiscal_year.year_end_date, 0
			)
			if voucher_no is None or row[8] == voucher_no
		]

	def purchase_journal(self):
		return frappe.db.get_value(
			"Accounting Journal",
			{"company": self.company, "type": "Purchase"},
			["journal_code", "journal_name"],
			as_dict=True,
		)

	def assert_fec_journal(self, voucher_no):
		journal = self.purchase_journal()
		rows = self.fec_rows(voucher_no)
		self.assertTrue(rows)
		for row in rows:
			self.assertEqual(row[0], journal.journal_code)
			self.assertEqual(row[1], journal.journal_name)

	def test_fec_shows_journal_code_and_label(self):
		self.assert_fec_journal(submitted_purchase_invoice(self.company).name)

	def test_fec_reads_entries_that_hold_the_bare_code(self):
		"""Entries posted since 6357514 may hold the bare journal code, an orphan link
		that an immutable ledger cannot correct: the FEC must still read them."""
		pi = submitted_purchase_invoice(self.company)
		frappe.db.sql(
			"update `tabGL Entry` set accounting_journal = %s where voucher_no = %s",
			(self.purchase_journal().journal_code, pi.name),
		)
		self.assert_fec_journal(pi.name)


class TestAccountingJournalAdjustment(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		cls.company = french_company()

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.set_value("Company", self.company, "accounts_frozen_till_date", None)

	def adjust(self, pi):
		from erpnext_france.erpnext_france.doctype.accounting_journal.accounting_journal import (
			accounting_journal_adjustment,
		)

		journal = frappe.db.get_value("Accounting Journal", {"company": self.company, "type": "Purchase"})
		accounting_journal_adjustment("Purchase Invoice", frappe.as_json([pi.name]), journal)

	def test_adjustment_is_refused_in_a_frozen_period(self):
		pi = submitted_purchase_invoice(self.company)
		frappe.db.set_value("Company", self.company, "accounts_frozen_till_date", getdate())
		with self.assertRaises(frappe.ValidationError):
			self.adjust(pi)

	def test_adjustment_reads_the_freezing_date_of_the_voucher_company(self):
		"""Another company's frozen period must not block, nor allow, this one."""
		other = other_company()
		pi = submitted_purchase_invoice(self.company)
		frappe.db.set_value("Company", other, "accounts_frozen_till_date", getdate())
		try:
			self.adjust(pi)
		finally:
			frappe.db.set_value("Company", other, "accounts_frozen_till_date", None)

	def test_adjustment_requires_rights_on_the_voucher(self):
		pi = submitted_purchase_invoice(self.company)
		user = "journal-no-rights@example.com"
		if not frappe.db.exists("User", user):
			frappe.get_doc(
				{"doctype": "User", "email": user, "first_name": "No rights", "send_welcome_email": 0}
			).insert(ignore_permissions=True)
		frappe.set_user(user)
		with self.assertRaises(frappe.PermissionError):
			self.adjust(pi)


class TestFecColumns(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		cls.company = french_company()

	def test_compte_lib_is_the_account_label(self):
		"""CompteLib is the account's label, not ERPNext's document name (number and abbr)."""
		pi = submitted_purchase_invoice(self.company)
		rows = TestAccountingJournal.fec_rows(self, pi.name)
		self.assertTrue(rows)
		accounts = frappe.get_all("GL Entry", filters={"voucher_no": pi.name}, pluck="account")
		labels = set(frappe.get_all("Account", filters={"name": ("in", accounts)}, pluck="account_name"))
		for row in rows:
			self.assertIn(row[5], labels)


class TestFecLettering(unittest.TestCase):
	"""EcritureLet/DateLet: entries are lettered only when their group balances."""

	@classmethod
	def setUpClass(cls):
		cls.company = french_company()

	def supplier_rows(self, pi):
		payable = frappe.db.get_value("Purchase Invoice", pi.name, "credit_to")
		number = frappe.db.get_value("Account", payable, "account_number")
		rows = TestAccountingJournal.fec_rows(self, pi.name)
		return [row for row in rows if row[4].startswith(number)]

	def test_unpaid_invoice_is_not_lettered(self):
		pi = submitted_purchase_invoice(self.company)
		for row in self.supplier_rows(pi):
			self.assertEqual((row[13], row[14]), ("", ""))

	def test_partly_paid_invoice_is_not_lettered(self):
		pi = submitted_purchase_invoice(self.company, amount=100)
		pay(pi, 40)
		for row in self.supplier_rows(pi):
			self.assertEqual((row[13], row[14]), ("", ""))

	def test_fully_paid_invoice_is_lettered(self):
		pi = submitted_purchase_invoice(self.company, amount=100)
		pay(pi, 100)
		rows = self.supplier_rows(pi)
		self.assertTrue(rows)
		for row in rows:
			self.assertEqual(row[13], pi.name)
			self.assertTrue(row[14])


class TestFecOpeningEntries(unittest.TestCase):
	"""The FEC of a fiscal year opens with the balances carried forward (journal AN)."""

	@classmethod
	def setUpClass(cls):
		cls.company = french_company()
		year = getdate().year
		cls.supplier = test_supplier(f"_Test AN Supplier {frappe.generate_hash(length=6)}")
		cls.pi = submitted_purchase_invoice(
			cls.company, amount=100, posting_date=f"{year - 1}-06-15", supplier=cls.supplier
		)
		cls.rows = [row for row in TestAccountingJournal.fec_rows(cls, None) if row[0] == "AN"]

	def test_opening_entries_carry_the_unpaid_supplier_balance(self):
		supplier_rows = [row for row in self.rows if row[6] == self.supplier]
		self.assertEqual(len(supplier_rows), 1)
		row = supplier_rows[0]
		self.assertEqual(row[3], f"{getdate().year}0101")
		self.assertEqual((row[11], row[12]), ("0,00", "100,00"))
		self.assertEqual(row[10], "A nouveau")

	def test_opening_journal_balances(self):
		def amount(value):
			return round(float(value.replace(",", ".")), 2)

		self.assertTrue(self.rows)
		self.assertEqual(
			round(sum(amount(row[11]) for row in self.rows), 2),
			round(sum(amount(row[12]) for row in self.rows), 2),
		)

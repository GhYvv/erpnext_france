# Copyright (c) 2018, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

import re

import frappe
from frappe import _
from frappe.utils import flt, format_datetime, getdate
from frappe.utils.data import get_datetime_in_timezone
from pypika import Order

COLUMNS = [
	{
		"label": _("JournalCode"),
		"fieldname": "JournalCode",
		"fieldtype": "Data",
		"width": 90,
	},
	{
		"label": _("JournalLib"),
		"fieldname": "JournalLib",
		"fieldtype": "Data",
		"width": 90,
	},
	{
		"label": _("EcritureNum"),
		"fieldname": "EcritureNum",
		"fieldtype": "Data",
		"width": 90,
	},
	{
		"label": _("EcritureDate"),
		"fieldname": "EcritureDate",
		"fieldtype": "Date",
		"width": 90,
	},
	{
		"label": _("CompteNum"),
		"fieldname": "CompteNum",
		"fieldtype": "Link",
		"options": "Account",
		"width": 100,
	},
	{
		"label": _("CompteLib"),
		"fieldname": "CompteLib",
		"fieldtype": "Link",
		"options": "Account",
		"width": 200,
	},
	{
		"label": _("CompAuxNum"),
		"fieldname": "CompAuxNum",
		"fieldtype": "Data",
		"width": 90,
	},
	{
		"label": _("CompAuxLib"),
		"fieldname": "CompAuxLib",
		"fieldtype": "Data",
		"width": 90,
	},
	{
		"label": _("PieceRef"),
		"fieldname": "PieceRef",
		"fieldtype": "Data",
		"width": 90,
	},
	{
		"label": _("PieceDate"),
		"fieldname": "PieceDate",
		"fieldtype": "Date",
		"width": 90,
	},
	{
		"label": _("EcritureLib"),
		"fieldname": "EcritureLib",
		"fieldtype": "Data",
		"width": 90,
	},
	{
		"label": "Débit",
		"fieldname": "Debit",
		"fieldtype": "Data",
		"width": 90,
	},
	{
		"label": "Crédit",
		"fieldname": "Credit",
		"fieldtype": "Data",
		"width": 90,
	},
	{
		"label": _("EcritureLet"),
		"fieldname": "EcritureLet",
		"fieldtype": "Data",
		"width": 90,
	},
	{
		"label": _("DateLet"),
		"fieldname": "DateLet",
		"fieldtype": "Date",
		"width": 90,
	},
	{
		"label": _("ValidDate"),
		"fieldname": "ValidDate",
		"fieldtype": "Date",
		"width": 90,
	},
	{
		"label": _("Montantdevise"),
		"fieldname": "Montantdevise",
		"fieldtype": "Data",
		"width": 90,
	},
	{
		"label": _("Idevise"),
		"fieldname": "Idevise",
		"fieldtype": "Data",
		"width": 90,
	},
	{
		"label": _("Due Date"),
		"fieldname": "DateLimitReglmt",
		"fieldtype": "Date",
		"width": 90,
	},
	{
		"label": _("Num Facture"),
		"fieldname": "NumFacture",
		"fieldtype": "Data",
		"width": 90,
	},
	{
		"label": _("Export Date"),
		"fieldname": "ExportDate",
		"fieldtype": "Datetime",
		"width": 90,
	},
	{
		"label": _("GL Entry"),
		"fieldname": "GlName",
		"fieldtype": "Link",
		"options": "GL Entry",
		"width": 0,
	},
]


def execute(filters=None):
	validate_filters(filters)
	return COLUMNS, get_result(
		company=filters["company"],
		fiscal_year=filters["fiscal_year"],
		from_date=filters["from_date"],
		to_date=filters["to_date"],
		hide_already_exported=True if filters.get("hide_already_exported") else False,
	)


def validate_filters(filters):
	if not filters.get("company"):
		frappe.throw(_("{0} is mandatory").format(_("Company")))

	if not filters.get("fiscal_year"):
		frappe.throw(_("{0} is mandatory").format(_("Fiscal Year")))


def get_gl_entries(company, fiscal_year, from_date, to_date, hide_already_exported):
	company_doc = frappe.get_doc("Company", company)
	gle = frappe.qb.DocType("GL Entry")
	sales_invoice = frappe.qb.DocType("Sales Invoice")
	purchase_invoice = frappe.qb.DocType("Purchase Invoice")
	journal_entry = frappe.qb.DocType("Journal Entry")
	payment_entry = frappe.qb.DocType("Payment Entry")
	customer = frappe.qb.DocType("Customer")
	supplier = frappe.qb.DocType("Supplier")
	employee = frappe.qb.DocType("Employee")

	debit = frappe.query_builder.functions.Sum(gle.debit).as_("debit")
	credit = frappe.query_builder.functions.Sum(gle.credit).as_("credit")
	debit_currency = frappe.query_builder.functions.Sum(gle.debit_in_account_currency).as_("debitCurr")
	credit_currency = frappe.query_builder.functions.Sum(gle.credit_in_account_currency).as_("creditCurr")

	query = (
		frappe.qb.from_(gle)
		.left_join(sales_invoice)
		.on(gle.voucher_no == sales_invoice.name)
		.left_join(purchase_invoice)
		.on(gle.voucher_no == purchase_invoice.name)
		.left_join(journal_entry)
		.on(gle.voucher_no == journal_entry.name)
		.left_join(payment_entry)
		.on(gle.voucher_no == payment_entry.name)
		.left_join(customer)
		.on(gle.party == customer.name)
		.left_join(supplier)
		.on(gle.party == supplier.name)
		.left_join(employee)
		.on(gle.party == employee.name)
		.select(
			gle.posting_date.as_("GlPostDate"),
			gle.name.as_("GlName"),
			gle.account,
			gle.transaction_date,
			gle.export_date.as_("ExportDate"),
			debit,
			credit,
			debit_currency,
			credit_currency,
			gle.accounting_entry_number,
			gle.voucher_type,
			gle.voucher_no,
			gle.against_voucher_type,
			gle.against_voucher,
			gle.account_currency,
			gle.against,
			gle.party_type,
			gle.party,
			gle.accounting_journal,
			gle.remarks,
			sales_invoice.name.as_("InvName"),
			sales_invoice.title.as_("InvTitle"),
			sales_invoice.posting_date.as_("InvPostDate"),
			sales_invoice.due_date.as_("InvDueDate"),
			purchase_invoice.name.as_("PurName"),
			purchase_invoice.title.as_("PurTitle"),
			purchase_invoice.posting_date.as_("PurPostDate"),
			purchase_invoice.due_date.as_("PurDueDate"),
			journal_entry.cheque_no.as_("JnlRef"),
			journal_entry.posting_date.as_("JnlPostDate"),
			journal_entry.title.as_("JnlTitle"),
			payment_entry.name.as_("PayName"),
			payment_entry.posting_date.as_("PayPostDate"),
			payment_entry.title.as_("PayTitle"),
			customer.customer_name,
			customer.name.as_("cusName"),
			supplier.supplier_name,
			supplier.name.as_("supName"),
			employee.employee_name,
			employee.name.as_("empName"),
		)
		.where(
			(gle.company == company)
			& (gle.fiscal_year == fiscal_year)
			& (gle.posting_date >= from_date)
			& (gle.posting_date <= to_date)
		)
	)

	if hide_already_exported:
		query = query.where(gle.export_date.isnull())

	current_order = Order.desc
	if company_doc.type_export_fec == "Standard FEC Export":
		current_order = Order.asc

	query = (
		query.groupby(gle.voucher_type, gle.voucher_no, gle.account, gle.name, gle.accounting_entry_number)
		.orderby(gle.posting_date, order=current_order)
		.orderby(gle.voucher_no, gle.accounting_entry_number)
	)

	return query.run(as_dict=True)


OPENING_JOURNAL = ("AN", "A nouveaux")


def get_result(company, fiscal_year, from_date, to_date, hide_already_exported):
	data = get_opening_entries(company, fiscal_year, from_date) + list(
		get_gl_entries(company, fiscal_year, from_date, to_date, hide_already_exported)
	)

	result = []

	company_currency = frappe.get_cached_value("Company", company, "default_currency")
	account_code_length = frappe.db.get_value("Company", company, "account_code_length") or 0
	accounts = frappe.get_all(
		"Account",
		filters={"Company": company},
		fields=["name", "account_number", "account_name"],
	)
	# GL entries link to the journal by name (`{journal_code}-{company}`);
	# entries posted before that naming hold the code, which was the name.
	journals = {}
	for j in frappe.get_all(
		"Accounting Journal",
		filters={"company": company},
		fields=["name", "journal_code", "journal_name"],
	):
		journals.setdefault(j.journal_code, j)
		journals[j.name] = j
	lettering_cache = {}

	for d in data:
		journal = journals.get(d.get("accounting_journal"))
		if d.get("is_carried_forward"):
			JournalCode, JournalLib = OPENING_JOURNAL
		elif journal:
			JournalCode, JournalLib = journal.journal_code, journal.journal_name
		else:
			JournalCode = d.get("accounting_journal") or re.split("-|/|[0-9]", d.get("voucher_no"))[0]
			JournalLib = None
		EcritureNum = d.get("accounting_entry_number")
		GlName = d.get("GlName")

		DateLimitReglmt = ""
		NumFacture = ""
		EcritureDate = format_datetime(d.get("GlPostDate"), "yyyyMMdd")
		ExportDate = format_datetime(d.get("ExportDate"), "yyyy-MM-dd HH:mm")
		PieceDate = EcritureDate

		account_number = [
			{"account_number": account.account_number, "account_name": account.account_name}
			for account in accounts
			if account.name == d.get("account") and account.account_number
		]
		if account_number:
			original = account_number[0]["account_number"]
			# Apply zero-padding as suffix if configured
			if account_code_length > 0 and len(original) < account_code_length:
				CompteNum = original.ljust(account_code_length, "0")
			else:
				CompteNum = original
			CompteLib = account_number[0]["account_name"]
		else:
			frappe.throw(
				_(
					"Account number for account {0} is not available.<br> Please setup your Chart of Accounts correctly."
				).format(d.get("account"))
			)

		if d.get("party_type") == "Customer":
			party_accounts = frappe.get_all(
				"Party Account",
				filters={"Company": company, "parent": d.get("cusName"), "parenttype": "Customer"},
				fields=["subledger_account"],
			)
			if party_accounts and party_accounts[0].get("subledger_account"):
				CompAuxNum = party_accounts[0].get("subledger_account")
			else:
				CompAuxNum = d.get("cusName")

			CompAuxLib = d.get("customer_name")

		elif d.get("party_type") == "Supplier":
			party_accounts = frappe.get_all(
				"Party Account",
				filters={"Company": company, "parent": d.get("supName"), "parenttype": "Supplier"},
				fields=["subledger_account"],
			)
			if party_accounts and party_accounts[0].get("subledger_account"):
				CompAuxNum = party_accounts[0].get("subledger_account")
			else:
				CompAuxNum = d.get("supName")
			CompAuxLib = d.get("supplier_name")

		elif d.get("party_type") == "Employee":
			CompAuxNum = d.get("empName")
			CompAuxLib = d.get("employee_name")

		elif d.get("party_type") == "Student":
			CompAuxNum = d.get("stuName")
			CompAuxLib = d.get("student_name")

		elif d.get("party_type") == "Member":
			CompAuxNum = d.get("memName")
			CompAuxLib = d.get("member_name")

		else:
			CompAuxNum = ""
			CompAuxLib = ""

		ValidDate = format_datetime(d.get("GlPostDate"), "yyyyMMdd")

		PieceRef = d.get("voucher_no") or "Sans Reference"
		# PieceRefType = d.get("voucher_type") or "Sans Reference"

		if d.get("voucher_type") == "Sales Invoice":
			NumFacture = d.get("voucher_no")
			DateLimitReglmt = format_datetime(d.get("InvDueDate"), "yyyyMMdd")
			PieceDate = format_datetime(d.get("InvPostDate"), "yyyyMMdd")

		if d.get("voucher_type") == "Purchase Invoice":
			NumFacture = d.get("voucher_no")
			DateLimitReglmt = format_datetime(d.get("PurDueDate"), "yyyyMMdd")
			PieceDate = format_datetime(d.get("PurPostDate"), "yyyyMMdd")

		# EcritureLib is the reference title unless it is an opening entry
		if d.get("is_opening") == "Yes":
			EcritureLib = _("Opening Entry Journal")
		elif d.get("remarks") and d.get("remarks").lower() not in ("no remarks", _("no remarks")):
			EcritureLib = d.get("remarks")
		elif d.get("voucher_type") == "Sales Invoice":
			EcritureLib = d.get("InvTitle")
		elif d.get("voucher_type") == "Purchase Invoice":
			EcritureLib = d.get("PurTitle")
		elif d.get("voucher_type") == "Journal Entry":
			EcritureLib = d.get("JnlTitle")
		elif d.get("voucher_type") == "Payment Entry":
			EcritureLib = d.get("PayTitle")
		else:
			EcritureLib = d.get("voucher_type")

		EcritureLib = " ".join((EcritureLib or "").splitlines())

		debit = "{:.2f}".format(d.get("debit")).replace(".", ",")

		credit = "{:.2f}".format(d.get("credit")).replace(".", ",")

		if d.debit == d.credit == 0:
			continue

		Idevise = d.get("account_currency")

		EcritureLet, DateLet = get_lettering(d, to_date, lettering_cache)

		Montantdevise = None
		if Idevise != company_currency:
			Montantdevise = (
				"{:.2f}".format(d.get("debitCurr")).replace(".", ",")
				if d.get("debitCurr") != 0
				else "{:.2f}".format(d.get("creditCurr")).replace(".", ",")
			)
		else:
			Montantdevise = (
				"{:.2f}".format(d.get("debit")).replace(".", ",")
				if d.get("debit") != 0
				else "{:.2f}".format(d.get("credit")).replace(".", ",")
			)

		row = [
			JournalCode,
			JournalLib,
			EcritureNum,
			EcritureDate,
			CompteNum,
			CompteLib,
			CompAuxNum,
			CompAuxLib,
			PieceRef,
			PieceDate,
			EcritureLib,
			debit,
			credit,
			EcritureLet,
			DateLet or "",
			ValidDate,
			Montantdevise,
			Idevise,
			DateLimitReglmt,
			NumFacture,
			ExportDate,
			GlName,
		]

		result.append(row)

	return result


def get_lettering(d, to_date, cache):
	"""(EcritureLet, DateLet) of an entry.

	Entries are lettered only when their group (account, party, invoice they
	settle) balances at the end of the export: a partly paid invoice is not
	lettered. DateLet is the date of the group's latest entry.
	"""
	if not d.get("against_voucher") or not d.get("party"):
		return "", ""
	key = (d.get("account"), d.get("party"), d.get("against_voucher_type"), d.get("against_voucher"))
	if key not in cache:
		gle = frappe.qb.DocType("GL Entry")
		balance, count, last_date = (
			frappe.qb.from_(gle)
			.select(
				frappe.query_builder.functions.Sum(gle.debit - gle.credit),
				frappe.query_builder.functions.Count(gle.name),
				frappe.query_builder.functions.Max(gle.posting_date),
			)
			.where(
				(gle.account == key[0])
				& (gle.party == key[1])
				& (gle.against_voucher_type == key[2])
				& (gle.against_voucher == key[3])
				& (gle.is_cancelled == 0)
				& (gle.posting_date <= to_date)
			)
		).run()[0]
		settled = count and count > 1 and abs(flt(balance)) < 0.005
		cache[key] = (key[3], format_datetime(last_date, "yyyyMMdd")) if settled else ("", "")
	return cache[key]


def get_opening_entries(company, fiscal_year, from_date):
	"""The balances carried forward (journal AN), when the export starts the fiscal year.

	ERPNext closes the income statement (Period Closing Voucher) but posts no
	opening entries: the FEC of a fiscal year must still open with the
	balance-sheet balances brought forward, per account and per party. If the
	previous year was not closed, its unallocated result is carried to the
	result account (120 profit, 129 loss) so that the journal balances.
	"""
	year_start = frappe.db.get_value("Fiscal Year", fiscal_year, "year_start_date")
	if not year_start or (from_date and getdate(from_date) > getdate(year_start)):
		return []

	gle = frappe.qb.DocType("GL Entry")
	account = frappe.qb.DocType("Account")
	Sum = frappe.query_builder.functions.Sum
	balances = (
		frappe.qb.from_(gle)
		.join(account)
		.on(gle.account == account.name)
		.select(
			gle.account,
			gle.party_type,
			gle.party,
			gle.account_currency,
			Sum(gle.debit - gle.credit).as_("balance"),
			Sum(gle.debit_in_account_currency - gle.credit_in_account_currency).as_("balance_currency"),
		)
		.where(
			(gle.company == company)
			& (gle.is_cancelled == 0)
			& (gle.posting_date < year_start)
			& (account.root_type.isin(["Asset", "Liability", "Equity"]))
		)
		.groupby(gle.account, gle.party_type, gle.party, gle.account_currency)
	).run(as_dict=True)

	lines = [b for b in balances if abs(flt(b.balance)) >= 0.005]
	result = -flt(sum(flt(b.balance) for b in lines), 2)
	if abs(result) >= 0.005:
		lines.append(
			frappe._dict(
				account=_result_account(company, loss=result > 0),
				account_currency=frappe.get_cached_value("Company", company, "default_currency"),
				balance=result,
				balance_currency=result,
			)
		)

	entry_number = f"{OPENING_JOURNAL[0]}{getdate(year_start).year}"
	return [_carried_forward_entry(line, year_start, entry_number) for line in lines]


def _result_account(company, loss):
	"""Result account: 129 for a loss, 120 for a profit, else any 12 account."""
	for prefix in ("129" if loss else "120", "12"):
		name = frappe.db.get_value(
			"Account",
			{"company": company, "is_group": 0, "account_number": ("like", f"{prefix}%")},
			"name",
			order_by="account_number asc",
		)
		if name:
			return name
	frappe.throw(_("No result account (12) found to carry forward the previous year's result."))


def _carried_forward_entry(line, year_start, entry_number):
	balance = flt(line.balance, 2)
	balance_currency = flt(line.balance_currency, 2)
	entry = frappe._dict(
		is_carried_forward=1,
		GlPostDate=year_start,
		account=line.account,
		account_currency=line.account_currency,
		debit=max(balance, 0),
		credit=max(-balance, 0),
		debitCurr=max(balance_currency, 0),
		creditCurr=max(-balance_currency, 0),
		accounting_entry_number=entry_number,
		voucher_no=OPENING_JOURNAL[0],
		remarks="A nouveau",
		party_type=line.party_type,
		party=line.party,
	)
	if line.party_type == "Supplier":
		entry.update(
			supName=line.party, supplier_name=frappe.db.get_value("Supplier", line.party, "supplier_name")
		)
	elif line.party_type == "Customer":
		entry.update(
			cusName=line.party, customer_name=frappe.db.get_value("Customer", line.party, "customer_name")
		)
	elif line.party_type == "Employee":
		entry.update(
			empName=line.party, employee_name=frappe.db.get_value("Employee", line.party, "employee_name")
		)
	return entry

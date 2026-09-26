# Copyright (c) 2021, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

from typing import Any, NewType

import frappe
from erpnext.setup.utils import set_defaults_for_tests
from frappe.core.doctype.report.report import get_report_module_dotted_path
from frappe.utils.data import now_datetime


def before_tests():
	frappe.clear_cache()
	# complete setup if missing
	from frappe.desk.page.setup_wizard.setup_wizard import setup_complete

	if not frappe.db.a_row_exists("Company"):
		current_year = now_datetime().year
		setup_complete(
			{
				"currency": "EUR",
				"full_name": "Test User",
				"company_name": "Mon Plaisir Fruité",
				"timezone": "Europe/Paris",
				"company_abbr": "MPF",
				"industry": "Manufacturing",
				"country": "France",
				"fy_start_date": f"{current_year}-01-01",
				"fy_end_date": f"{current_year}-12-31",
				"language": "french",
				"company_tagline": "Testing",
				"email": "test@test.com",
				"password": "test",
				"chart_of_accounts": "France - Plan Comptable General 2025 avec code",
			}
		)

	frappe.db.sql("delete from `tabItem Price`")

	_enable_all_roles_for_admin()

	set_defaults_for_tests()

	frappe.db.commit()


def _enable_all_roles_for_admin():
	from frappe.desk.page.setup_wizard.setup_wizard import add_all_roles_to

	all_roles = set(frappe.db.get_values("Role", pluck="name"))
	admin_roles = set(
		frappe.db.get_values("Has Role", {"parent": "Administrator"}, fieldname="role", pluck="role")
	)

	if all_roles.difference(admin_roles):
		add_all_roles_to("Administrator")


# Fixtures for tests that post real accounting entries. They build their own
# French company instead of relying on ERPNext's global test records.

TEST_COMPANY = "ERPNext France Test SAS"
CHART = "France - Plan Comptable General 2025 avec code"


def french_company():
	company = frappe.db.get_value("Company", {"country": "France"}, "name")
	if not company:
		company = (
			frappe.get_doc(
				{
					"doctype": "Company",
					"company_name": TEST_COMPANY,
					"abbr": "EFT",
					"country": "France",
					"default_currency": "EUR",
					"create_chart_of_accounts_based_on": "Standard Template",
					"chart_of_accounts": CHART,
				}
			)
			.insert(ignore_permissions=True)
			.name
		)
	_ensure_fiscal_year(company)
	if not frappe.db.get_value("Company", company, "round_off_account"):
		frappe.db.set_value("Company", company, "round_off_account", _leaf(company, "Expense"))
	frappe.db.commit()
	return company


def _leaf(company, root_type):
	return frappe.db.get_value("Account", {"company": company, "root_type": root_type, "is_group": 0}, "name")


def _ensure_fiscal_year(company):
	year = now_datetime().year
	start, end = f"{year}-01-01", f"{year}-12-31"
	name = frappe.db.get_value("Fiscal Year", {"year_start_date": start, "year_end_date": end}, "name")
	if not name:
		frappe.get_doc(
			{"doctype": "Fiscal Year", "year": str(year), "year_start_date": start, "year_end_date": end}
		).insert(ignore_permissions=True)
		return
	fy = frappe.get_doc("Fiscal Year", name)
	if fy.companies and company not in [row.company for row in fy.companies]:
		fy.append("companies", {"company": company})
		fy.save(ignore_permissions=True)


def test_supplier(name="_Test France Supplier"):
	if not frappe.db.exists("Supplier", name):
		doc = frappe.get_doc(
			{
				"doctype": "Supplier",
				"supplier_name": name,
				"supplier_group": frappe.db.get_value("Supplier Group", {"is_group": 0}, "name"),
			}
		)
		if not frappe.db.a_row_exists("Categorie Comptable Tiers"):
			frappe.get_doc({"doctype": "Categorie Comptable Tiers", "nom": "_Test"}).insert(
				ignore_permissions=True
			)
		doc.categorie_comptable_tiers = frappe.db.get_value("Categorie Comptable Tiers", {}, "name")
		doc.insert(ignore_permissions=True)
	return name


def test_service_item(company, code="_Test France Service"):
	if frappe.db.exists("Item", code):
		doc = frappe.get_doc("Item", code)
	else:
		doc = frappe.get_doc(
			{
				"doctype": "Item",
				"item_code": code,
				"item_group": frappe.db.get_value("Item Group", {"is_group": 0}, "name"),
				"stock_uom": "Nos",
				"is_stock_item": 0,
			}
		)
	row = next((d for d in doc.item_defaults if d.company == company), None) or doc.append(
		"item_defaults", {"company": company}
	)
	if not row.expense_account:
		row.expense_account = _leaf(company, "Expense")
	doc.save(ignore_permissions=True)
	return code


def submitted_purchase_invoice(company, amount=100):
	pi = frappe.get_doc(
		{
			"doctype": "Purchase Invoice",
			"company": company,
			"supplier": test_supplier(),
			"bill_no": frappe.generate_hash(length=10),
			"items": [{"item_code": test_service_item(company), "qty": 1, "rate": amount}],
		}
	)
	pi.insert(ignore_permissions=True)
	pi.submit()
	return pi

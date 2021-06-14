# Copyright (c) 2021, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

from erpnext.hr.doctype.attendance.attendance import get_overtime_type
import frappe
from frappe import _
from frappe.utils import get_datetime, getdate
from erpnext.payroll.doctype.payroll_entry.payroll_entry import get_start_end_dates
from erpnext.payroll.doctype.gratuity.gratuity import get_salary_structure
from frappe.model.document import Document
class OvertimeSlip(Document):
	def on_submit(self):
		if self.status == "Pending":
			frappe.throw(_("Overtime Slip with Status 'Approved' or 'Rejected' are allowed for Submission"))

	@frappe.whitelist()
	def get_emp_and_overtime_details(self):
		overtime_based_on = frappe.db.get_single_value("Payroll Settings", "overtime_based_on")
		records = []
		if overtime_based_on == "Attendance":
			records = self.get_attendance_record()
			if len(records):
				self.create_overtime_details_row_for_attendance(records)
		elif overtime_based_on == "Timesheet":
			records = self.get_timesheet_record()
			if len(records):
				self.create_overtime_details_row_for_timesheet(records)
		else:
			frappe.throw(_('Select "Calculate Overtime Hours Based On" in Payroll Settings'))

		if len(self.overtime_details):
			self.total_overtime_duration = sum([int(detail.overtime_duration) for detail in self.overtime_details])

		if not len(records):
			self.overtime_details = []
			frappe.msgprint(_("No {0} records found for Overtime").format(overtime_based_on))

	def create_overtime_details_row_for_attendance(self, records):
		self.overtime_details = []
		for record in records:
			if record.standard_working_time:
				standard_working_time = record.standard_working_time
			else:
				standard_working_time = frappe.db.get_single_value("HR Settings", "standard_working_hours") * 3600
				if not standard_working_time:
					frappe.throw(_('Please Set "Standard Working Hours" in HR settings'))

			if record.overtime_duration:
				self.append("overtime_details", {
					"reference_document_type": "Attendance",
					"reference_document": record.name,
					"date": record.attendance_date,
					"overtime_type": record.overtime_type,
					"overtime_duration": record.overtime_duration,
					"standard_working_time": standard_working_time,
				})

	def create_overtime_details_row_for_timesheet(self, records):
		self.overtime_details = []
		from math import modf

		standard_working_time = frappe.db.get_single_value("HR Settings", "standard_working_hours") * 3600
		if not standard_working_time:
			frappe.throw(_('Please Set "Standard Working Hours" in HR settings'))


		for record in records:
			if record.overtime_hours:
				overtime_hours = modf(record.overtime_hours)
				record.overtime_hours = overtime_hours[1]*3600 + overtime_hours[0]*60
				self.append("overtime_details", {
					"reference_document_type": "Timesheet",
					"reference_document": record.name,
					"date": record.overtime_on,
					"start_date": record.start_date,
					"end_date": record.end_date,
					"overtime_type": record.overtime_type,
					"overtime_duration": record.overtime_hours,
					"standard_working_time": standard_working_time
				})

	def get_attendance_record(self):
		if self.from_date and self.to_date:
			records = frappe.db.sql("""SELECT overtime_duration, name, attendance_date, overtime_type, standard_working_time
				FROM `TabAttendance`
				WHERE
					attendance_date >= %s AND attendance_date <= %s
					AND employee = %s
					AND docstatus = 1 AND status= 'Present'
					AND (
						overtime_duration IS NOT NULL OR overtime_duration != '00:00:00.000000'
					)
			""", (getdate(self.from_date), getdate(self.to_date), self.employee), as_dict=1, debug = 1)
			return records
		return []

	def get_timesheet_record(self):
		if self.from_date and self.to_date:

			"""SELECT Orders.OrderID, Customers.CustomerName, Orders.OrderDate
			FROM Orders
			INNER JOIN Customers ON Orders.CustomerID=Customers.CustomerID;"""

			records = frappe.db.sql("""SELECT ts.name, ts.start_date, ts.end_date, tsd.overtime_on, tsd.overtime_type, tsd.overtime_hours
				FROM `TabTimesheet` AS ts
				INNER JOIN `tabTimesheet Detail` As tsd ON tsd.parent = ts.name
				WHERE
					ts.docstatus = 1
					AND end_date > %(from_date)s AND end_date <= %(to_date)s
					AND start_date >= %(from_date)s AND start_date < %(to_date)s
					AND employee = %(employee)s
					AND (
						total_overtime_hours IS NOT NULL OR total_overtime_hours != 0
					)
			""", {"from_date": get_datetime(self.from_date), "to_date": get_datetime(self.to_date),"employee": self.employee}, as_dict=1, debug = 1)
			return records
		return []

@frappe.whitelist()
def get_standard_working_hours(employee, date):
	shift_assignment = frappe.db.sql('''SELECT shift_type FROM `tabShift Assignment`
		WHERE employee = %(employee)s
		AND start_date < %(date)s
		and (end_date > %(date)s or end_date is NULL or end_date = "") ''', {
			"employee": employee, "date": get_datetime(date)}
		, as_dict=1, debug=1)

	standard_working_time = 0


	fetch_from_shift = frappe.db.get_single_value("Payroll Settings", "fetch_standard_working_hours_from_shift_type")

	if len(shift_assignment) and fetch_from_shift:
		standard_working_time = frappe.db.get_value("Shift Type", shift_assignment[0].shift_type, "standard_working_time")
	elif not len(shift_assignment) and fetch_from_shift:
		shift = frappe.db.get_value("Employee", employee, "default_shift")
		if shift:
			standard_working_time = frappe.db.get_value("Shift Type", shift, "standard_working_time")
		else:
			frappe.throw(_("Set Default Shift in Employee:{0}").format(employee))
	elif not fetch_from_shift:
		standard_working_time = frappe.db.get_single_value("HR Settings", "standard_working_hours") * 3600
		if not standard_working_time:
			frappe.throw(_('Please Set "Standard Working Hours" in HR settings'))

	return standard_working_time

@frappe.whitelist()
def get_frequency_and_dates(employee, date):
	salary_structure = get_salary_structure(employee)
	if salary_structure:
		payroll_frequency = frappe.db.get_value('Salary Structure', salary_structure, 'payroll_frequency')
		date_details = get_start_end_dates(payroll_frequency, date, frappe.db.get_value('Employee', employee, 'company'))
		return [date_details, payroll_frequency]
	else:
		frappe.throw(_("No Salary Structure Assignment found for Employee: {0}").format(employee))


# Summer Camp Lunch Package Registration

## 1. Customer Statement of Requirements

The Summer Camp Lunch Package Registration system will be a web application designed for parents or guardians whose children attend summer camp at Tucker Road Ice Rink. The purpose of the application is to make ordering summer camp lunches easier and to help the ice rink café organize and track lunch orders.

The summer camp operates four days per week for three weeks, creating a total of twelve available lunch days. Parents will be able to purchase a lunch package for four days, six days, or all twelve days. Each camper may receive only one lunch per camp day. The available meals will include chicken tenders with fries and a drink for $11, cheese pizza with fries and a drink for $11, and pepperoni pizza with fries and a drink for $12.

Parents will use the application to register their camper, select a package, choose meals for the available camp days, review their selections, and submit an order. They will also be able to track the number of lunches ordered, the number completed, and the number of lunch days remaining. Café employees will use the system to review daily orders and mark lunches as completed. Administrators will be able to manage meal options, camp dates, package limits, and order information.

## 2. Requirements Specification

### Functional Requirements

1. The system shall allow a parent or guardian to register a camper.

2. The system shall allow a parent or guardian to enter contact information.

3. The system shall display the available four-day, six-day, and twelve-day lunch packages.

4. The system shall display each meal option and its price.

5. The system shall allow parents to select one lunch for each eligible camp day.

6. The system shall prevent parents from ordering more lunches than their selected package allows.

7. The system shall prevent a camper from receiving more than one lunch on the same day.

8. The system shall calculate the total cost of an order based on the selected meals.

9. The system shall allow parents to review their selections before submitting an order.

10. The system shall save camper, package, meal, and order information in a database.

11. The system shall allow parents to view the number of lunches ordered, completed, and remaining.

12. The system shall allow café employees to view lunch orders for each camp day.

13. The system shall allow café employees to mark an order as completed.

14. The system shall allow an administrator to manage camp dates, meal choices, prices, and package limits.

### Nonfunctional Requirements

1. The application shall provide a clear and easy-to-use interface.

2. The application shall be accessible through a web browser on computers, tablets, and mobile devices.

3. The application shall validate required information before accepting an order.

4. The application shall protect parent, camper, and order information from unauthorized access.

5. The application shall store information accurately and retrieve it when requested.

6. The application shall respond to normal user actions within a reasonable amount of time.

7. The application shall provide clear error messages when information is missing or invalid.

8. The application shall be organized so that future developers can maintain and update it.

## 3. Data and Storage Blueprint

### Data Input

The system will primarily use manual data entry. Parents or guardians will enter their contact information, camper information, package selection, camp dates, and meal choices through online forms. Café employees will manually update an order when a lunch has been prepared or completed. Administrators will enter and update meal options, prices, package limits, and camp dates.

The application will not require an outside dataset during the first iteration. The data will be created through user activity within the application.

### Database or Storage

The application will use a hosted PostgreSQL database through Supabase. A hosted database will allow the deployed web application to connect to the same database through its URL. This is more appropriate than storing the information only in a local SQLite file because the data must remain available when the application is accessed online.

The database is expected to include tables for users, campers, lunch packages, meals, camp dates, orders, and daily lunch selections. Relationships between these tables will allow the system to connect each parent to a camper, each camper to an order, and each order to its selected meals and camp dates.

The application will use HTML and CSS for the user interface, Python with Flask for the application logic, and PostgreSQL through Supabase for data storage. GitHub will be used for version control, documentation, Issues, branches, and sprint tracking.

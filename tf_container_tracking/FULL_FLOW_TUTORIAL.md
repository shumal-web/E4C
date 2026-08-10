# Container, Serial, and Dispatch Flow Tutorial

## 1. Purpose of This Document
This document explains the full flow that has been built in the project.

It starts from:

1. product setup
2. sales order planning
3. container serial planning
4. case or piece serial planning
5. sales order approval
6. container tracking
7. dispatch tickets
8. inventory documents
9. internal transfer sales order filtering

The goal is simple: after reading this document, a new team member should understand what the system does, why it was built, and how the screens connect to each other.

### Screenshot Note
The screenshots in this document come from the local `e4c` test database.

Because this is a test database:

1. some names are test names
2. some field values are sample values
3. a few screenshots use different sample orders so the document can show a cleaner example of the full flow

---

## 2. What This System Is Trying to Do
This project is turning a normal sales and inventory flow into a logistics flow.

The client does not only want to sell a product. They want to:

1. plan containers on the sales order
2. plan the cases or pieces that belong inside those containers
3. keep container information like port, ETA, LFD, location, chassis number, and status
4. control when operations are allowed to start
5. dispatch trucks and trailers in a controlled way
6. keep a history of those dispatch actions
7. move the correct serials in inventory without mixing them with serials from another sales order

So the system now connects Sales, Inventory, Container Tracking, and Dispatch into one flow.

---

## 3. Main Idea in Very Simple Words
Think of the flow like this:

1. A sales order is created.
2. The user adds a container product and case or piece products.
3. The user opens `Details` on those lines and plans the serials.
4. The user assigns cases or pieces to containers.
5. The sales order is confirmed.
6. The flow moves to `To Be Approved`.
7. A manager approves it.
8. After approval, the container tracking and dispatch part becomes active.
9. The team tracks the container.
10. The team creates and updates dispatch tickets.
11. Inventory documents use the same sales order context so the correct serials move through the warehouse.

---

## 4. Important Terms
| Term | Simple Meaning |
|---|---|
| Sales Order | The main order where the job starts. |
| Serial | One unique number for one tracked unit. |
| Container Product | A product line that represents a container. |
| Case or Piece Product | A product line that represents the items inside the container. |
| Container Serial Plan | The saved planning record for one container. |
| Case or Piece Serial Plan | The saved planning record for one case or one piece. |
| Container Tracking | The screen where the team tracks the container after approval. |
| Dispatch Ticket | The screen used by dispatch to manage truck movement, trailer use, and WhatsApp tracking. |
| Inventory Document | Receipt, internal transfer, or delivery order created from this flow. |
| SO Filter | The sales order reference used in transfers to show only the correct serials. |

---

## 5. Which Modules Are Doing the Work
There are two main custom modules in this solution.

### `tf_serial_quote_attributes`
This is the base serial planning layer.

It handles:

1. the `Details` wizard on sales order lines
2. planned serial rows on the quotation or sales order
3. serial attributes like length, width, height, weight, and storage fields
4. passing planned serial information into inventory operations

### `tf_container_tracking`
This is the container and dispatch layer.

It handles:

1. container-specific fields
2. case or piece to container assignment
3. container tracking dashboard
4. dispatch tickets
5. trailer, truck, and driver records
6. approval-based flow control
7. inventory document linking
8. internal transfer sales order filter support

Important note:

Dispatch was not built as a separate module. It is built inside `tf_container_tracking`.

### Where the Team Opens Each Screen
| Screen | Where to open it |
|---|---|
| Product Setup | `Sales -> Products -> Products -> open product -> Inventory tab` |
| Sales Order | `Sales -> Orders -> Quotations` or `Sales -> Orders -> Sales Orders` |
| Container Serial Wizard | Open a sales order line and click `Details` |
| Case or Piece Assignment Wizard | Open a sales order line and click `Details` |
| Container Tracking Dashboard | `Inventory -> Operations -> Container Tracking` or the `Containers` button on the sales order |
| Single Container Record | Open one row from `Container Tracking` |
| Dispatch Tickets | `Inventory -> Operations -> Dispatch -> Dispatch Tickets` or the `Dispatch Tickets` button on the sales order or container |
| Internal Transfer | `Inventory -> Operations -> Internal Transfers` |

---

## 6. Feature Summary: What Has Been Added
The current build includes these main features.

1. New products start with `Service` as the default product type.
2. Container products can be marked with `Is Container Product`.
3. Case or piece products can be marked with `Requires Container Assignment`.
4. Serial planning is done from the sales order line `Details` button.
5. Container lines store container-specific fields.
6. Case or piece lines can be assigned to specific containers.
7. Common dimensions can be entered once and applied to many case lines.
8. Case serials use the readable format requested by the client, such as `S00268-1 1 of 5`.
9. Sales order flow now uses `Draft -> To Be Approved -> Approved -> Completed`.
10. Container and dispatch actions are controlled by approval.
11. Container tracking dashboard shows one row per container.
12. Each container record stores its own status, dispatch progress, and linked documents.
13. Dispatch tickets store truck, driver, trailer, location, state, and WhatsApp audit.
14. Internal transfer form has `SO Filter` and `Container #` context.
15. Serial selection in inventory uses the sales order context so the wrong serial is not picked by mistake.

---

## 7. Step 1: Product Setup
The flow starts with product setup.

There are two important product types in this project:

1. a container product
2. a case or piece product that must belong to a container

### 7.1 Container Product
Container products are marked with `Is Container Product`.

This tells the system:

1. this line is a container line
2. it should create container serial planning rows
3. it should appear in container tracking later

![Container Product Setup](docs/images/01_product_container_setup.png)

In the screenshot above, the product is marked as a container product inside the `Container Setup` section.

### 7.2 Case or Piece Product
Case or piece products are marked with `Requires Container Assignment`.

This tells the system:

1. this line is not the container itself
2. this line must be assigned to one of the containers in the same sales order
3. the wizard should show the container distribution section

![Case Product Setup](docs/images/02_product_case_setup.png)

In the screenshot above, the product is not a container, but it is marked as requiring container assignment.

### 7.3 What Happens Automatically at Product Level
When a product is used in this logistics flow, the module makes sure it behaves like a tracked logistics item.

That means the system turns on the inventory and serial behaviour needed for:

1. serial planning
2. container assignment
3. inventory movement later

---

## 8. Step 2: Sales Order Setup
The sales order is the main document where the whole job starts.

The user adds:

1. normal service lines if needed
2. one or more container lines
3. one or more case or piece lines

The `Flow Type` also matters. In the current build, this tells the system whether the order is following an import flow or an export flow.

![Sales Order Example](docs/images/03_sales_order_approved.png)

In this example:

1. `Test CONTAINER` is the container line
2. `Dispatch Retest Case` is the case line
3. the order is already in `Approved`
4. the stat buttons for `Containers` and `Dispatch Tickets` are visible because approval is already done

### 8.1 Why the `Details` Button Matters
Each serial-tracked line gets a `Details` button on the order line.

That button opens the serial planning wizard.

This is where the user tells the system:

1. how many container serials exist
2. how many case or piece serials exist
3. which cases belong to which container
4. what the dimensions and weights are

---

## 9. Step 3: Container Serial Planning
The user clicks `Details` on the container line.

This opens the container serial planning wizard.

![Container Serial Wizard](docs/images/04_container_serial_wizard.png)

### 9.1 What the Container Wizard Does
This wizard creates one planning row for each container.

Each row can store:

1. serial number
2. container number
3. internal status
4. port to de-stuff
5. container status
6. container location
7. ETA
8. LFD
9. SSL
10. type
11. chassis number
12. PU/BK number

### 9.2 What the User Does Here
The user fills or reviews the container information row by row.

Usually:

1. quantity `3` means 3 container rows
2. each row becomes one tracked container plan
3. these rows later appear in the container tracking dashboard

### 9.3 Important Behaviour
When these rows are first created, they start as planned container records.

Later, after the sales order is approved, they become operational container tracking records.

---

## 10. Step 4: Case or Piece Planning and Container Assignment
The user clicks `Details` on the case or piece line.

Because the product requires container assignment, the wizard changes.

![Case Assignment Wizard](docs/images/05_case_assignment_wizard.png)

### 10.1 What This Wizard Shows
This wizard has two jobs.

The first job is the `Assign Cases to Containers` section.

This section lets the user say:

1. how many cases go into container 1
2. how many cases go into container 2
3. how many cases go into container 3

The second job is the serial line list below.

This section holds one row for each case or piece serial.

### 10.2 Common Attributes
On the right side, the wizard has `Common Attributes`.

This was added so the user does not have to type the same values again and again.

The user can enter:

1. length
2. width
3. height
4. dimension unit
5. weight
6. weight unit

Then the `Assign` action applies those values to the generated case rows.

### 10.3 Case Serial Naming Format
The case serial format was changed to make it more readable.

Example:

1. `S00268-1 1 of 5`
2. `S00268-1 2 of 5`
3. `S00268-1 3 of 5`
4. `S00268-2 1 of 3`
5. `S00268-3 1 of 2`

This format tells the user two things very quickly:

1. which container group the case belongs to
2. which case number it is inside that group

### 10.4 Why This Assignment Step Is Important
This step creates the real relationship between:

1. the container
2. the case or piece

Without this relationship, later logistics steps do not know which items belong to which container.

---

## 11. Step 5: Confirm and Approve the Sales Order
This is one of the most important rules in the current design.

### 11.1 Confirm Is Not the Real Operational Start
When the user confirms the sales order:

1. the sales order becomes a real sales order
2. the custom flow moves to `To Be Approved`
3. the order is still not ready for full logistics actions

### 11.2 Approval Is the Real Operational Start
When the manager clicks `Approve`:

1. the custom flow moves to `Approved`
2. container tracking becomes active
3. dispatch features become active
4. operational stat buttons become visible
5. the order is now ready for container and dispatch work

### 11.3 Why This Change Was Important
This was changed because the client wanted the logistics records to become active at approval, not just at confirmation.

That means the system now waits for approval before exposing operational actions.

---

## 12. Step 6: Container Tracking Dashboard
After approval, the user can open the `Containers` stat button on the sales order.

This opens the container tracking dashboard.

![Container Tracking Dashboard](docs/images/06_container_tracking_list.png)

### 12.1 What the Dashboard Shows
Each row is one container.

The dashboard shows:

1. sales order
2. serial
3. container number
4. dispatch progress
5. internal status
6. port to de-stuff
7. container status
8. container location
9. ETA
10. LFD
11. SSL
12. type
13. chassis number
14. PU/BK number
15. assigned piece count

### 12.2 Why This Screen Matters
This is the main operations dashboard for containers.

The team can quickly see:

1. where the container is in the process
2. how many pieces are tied to it
3. whether dispatch has started
4. whether it is still on the water, at port, ready, or already returned

---

## 13. Step 7: Single Container Tracking Record
The user can open a single container row from the dashboard.

![Container Tracking Record](docs/images/07_container_tracking_form.png)

### 13.1 What the Form Shows
This screen stores the full working state of one container.

It shows:

1. order
2. order line
3. serial number
4. container number
5. dispatch progress
6. internal status
7. container status
8. assigned pieces
9. port to de-stuff
10. location
11. ready on
12. ETA
13. LFD
14. SSL
15. type
16. chassis number
17. PU/BK number

### 13.2 What the Buttons Mean
The header buttons let the operations team move the container forward.

Examples:

1. `Import`
2. `Submit For Approval`
3. `Move To Tracking`

The stat buttons let the user jump to linked records:

1. `Inventory Docs`
2. `Dispatch Tickets`

### 13.3 What the Chatter Is Used For
The chatter on the right keeps a visible history.

This is useful because the team can see:

1. who changed a status
2. when a field changed
3. what the last important update was

---

## 14. Step 8: Dispatch Ticket Flow
Dispatch is the next layer after the container is operational.

The user opens a dispatch ticket either from the sales order, the container record, or the dispatch menu.

![Dispatch Ticket Form](docs/images/08_dispatch_ticket_form.png)

This screenshot uses another sample order because it shows a cleaner dispatch example with linked inventory documents already attached.

### 14.1 What a Dispatch Ticket Stores
A dispatch ticket stores the working instructions for one dispatch action.

It stores:

1. dispatch ticket number
2. dispatch type
3. sales order
4. container number
5. dispatch date
6. location
7. location note
8. truck
9. driver
10. trailer
11. trailer current location
12. trailer destination
13. WhatsApp sent flag
14. WhatsApp sent date
15. WhatsApp sent by
16. linked documents
17. state history

### 14.2 Dispatch States
The dispatch ticket moves through these states:

1. `Draft`
2. `Sent`
3. `In Progress`
4. `Completed`
5. `Cancelled`

### 14.3 What the Buttons Do
The buttons are very direct.

1. `Send WhatsApp` marks that the message was sent and stores the audit details.
2. `Mark In Progress` moves the ticket into active work.
3. `Complete` finishes the dispatch step.
4. `Cancel` stops the ticket.

### 14.4 Important Note About WhatsApp
In the current build, WhatsApp is manual tracking only.

That means:

1. the system stores whether the message was sent
2. the system stores who sent it
3. the system stores when it was sent
4. the system does not send a real WhatsApp message by itself yet

### 14.5 Linked Documents
The dispatch ticket can show links to:

1. receiving operation
2. internal transfer
3. delivery order

This is important because dispatch is not isolated. It is connected to warehouse documents.

---

## 15. Step 9: Inventory Documents
The logistics flow does not stop at planning or dispatch.

It also touches Inventory.

The module carries the sales order and container context into inventory documents.

That means the warehouse team can still see:

1. which sales order the transfer belongs to
2. which container it belongs to
3. what kind of flow it is

---

## 16. Step 10: Internal Transfer with Sales Order Filter
This is the transfer-side control added to stop users from picking the wrong serial.

![Internal Transfer Form](docs/images/09_internal_transfer_form.png)

This screenshot also uses another sample order because it shows the `SO Filter` field clearly.

### 16.1 What Was Added on the Internal Transfer
The internal transfer form now includes:

1. `Source Document`
2. `SO Filter`
3. `Container #`

### 16.2 Why the `SO Filter` Matters
The same product can exist in many sales orders.

Without a sales order filter, a user might choose the wrong serial from another order.

So the `SO Filter` is used to limit serial selection to the correct sales order context.

In simple words:

1. if the transfer is for sales order `S00170`
2. the system should only show serials that belong to `S00170`
3. this reduces mistakes in internal movement

### 16.3 What This Helps Prevent
This helps prevent:

1. mixing serials from different orders
2. moving the wrong case or piece
3. warehouse confusion during transfer or delivery

---

## 17. Statuses Used in the System
This project uses a few status groups. It is important to understand what each one means.

### 17.1 Sales Order Flow Status
| Status | Meaning |
|---|---|
| Draft | The order is still being prepared. |
| To Be Approved | The order is confirmed but waiting for manager approval. |
| Approved | The logistics flow is allowed to start. |
| Completed | The order flow has been fully completed. |

### 17.2 Container Internal Status
| Status | Meaning |
|---|---|
| For Approval | The container plan exists but is not active yet. |
| Pickup | The container is in pickup stage. |
| Tracking | The container is in active tracking stage. |
| Planning | The container is ready for planning and next actions. |
| Dispatch | The container is in dispatch stage. |

### 17.3 Container Status
| Status | Meaning |
|---|---|
| On the Water | The container is still in transit. |
| At Port | The container has reached the port. |
| Ready | The container is ready for the next move. |
| Ready for Return | The container is ready to go back. |
| Picked Up | The container has been picked up. |
| De Stuffed | The contents have been unloaded. |
| Returned | The container has been returned. |

### 17.4 Dispatch Progress
| Status | Meaning |
|---|---|
| Not Dispatched | No dispatch work has started yet. |
| Delivery | Delivery-side dispatch work is in progress. |
| Return | Return-side dispatch work is in progress. |
| Completed | Dispatch work is finished. |

---

## 18. What the User Does Manually and What the System Does Automatically

### 18.1 Manual User Work
The user still has to do these actions.

1. create the sales order
2. choose the right products
3. open the `Details` wizards
4. fill container fields
5. assign case quantities to containers
6. review dimensions and weights
7. confirm the sales order
8. approve the sales order
9. update container fields and statuses
10. fill dispatch ticket information
11. mark WhatsApp as sent
12. move dispatch tickets through their states

### 18.2 Automatic System Work
The system handles these parts automatically.

1. creates serial planning records from the wizard
2. saves the relationship between case or piece serials and container serials
3. changes the sales order flow to `To Be Approved` on confirmation
4. activates the operational flow after approval
5. keeps history in chatter
6. carries sales order and container context into inventory documents
7. uses the sales order filter logic in transfer serial selection

---

## 19. What Has Been Built So Far in Business Terms
If someone asks, “What did we build?”, this is the short answer.

We built a connected logistics workflow where:

1. containers are planned on the sales order
2. cases or pieces are planned and tied to those containers
3. approval controls when the operation can really start
4. containers get their own tracking screen
5. dispatch gets its own ticket screen
6. warehouse documents carry the same order and container context
7. serial movement is controlled so the wrong serial is not selected

---

## 20. Known Scope Boundary
One important boundary still exists in the current build.

The dispatch screen already has WhatsApp tracking.

But real WhatsApp sending is not integrated yet.

Right now the system only records the manual action.

If real WhatsApp sending is needed later, that will be a separate integration step.

---

## 21. Quick End-to-End Walkthrough
If you want the shortest version of the full flow, this is it.

1. Create or open the right products.
2. Mark container products with `Is Container Product`.
3. Mark case or piece products with `Requires Container Assignment`.
4. Create the sales order.
5. Add service lines if needed.
6. Add the container line.
7. Add the case or piece line.
8. Open `Details` on the container line and plan the containers.
9. Open `Details` on the case or piece line.
10. Assign the cases or pieces across the containers.
11. Apply common dimensions and weight if the lines are similar.
12. Save the wizard.
13. Confirm the sales order.
14. The order moves to `To Be Approved`.
15. Manager approves the order.
16. Container tracking and dispatch become active.
17. Open the `Containers` stat button and track each container.
18. Open the `Dispatch Tickets` area and manage dispatch work.
19. Use inventory documents to receive, transfer, and deliver the correct serials.
20. Use the `SO Filter` on internal transfer so the team only works with serials from the correct sales order.

---

## 22. Final Summary
This system is no longer just a normal sales order setup.

It is a linked flow between:

1. Sales
2. serial planning
3. container planning
4. case or piece assignment
5. approval control
6. container tracking
7. dispatch
8. inventory movement

The most important idea to remember is this:

The sales order is where planning starts, but approval is where operations really begin.

After approval, the container record becomes the main tracking record, and the dispatch ticket becomes the main movement record.

# Digidara CRM Testing Guide

Version: 1.0

Date: 2026-07-20

Product: Digidara CRM

## 1. Purpose

This document gives the testing team a practical checklist to validate Digidara CRM before product handoff. It covers setup, smoke testing, module testing, role-based access testing, integration behavior and regression checks.

## 2. Test Environment

Required software:

- Python 3.10 or newer
- Node.js 18 or newer
- npm
- MySQL Server
- MySQL Workbench or another MySQL client
- Chrome, Edge or Firefox

Recommended screen sizes:

- Desktop: 1440 x 900
- Laptop: 1366 x 768
- Tablet: 768 x 1024
- Mobile: 390 x 844

Local URLs:

- Backend: `http://localhost:5002`
- Frontend: `http://localhost:5173`
- Health check: `http://localhost:5002/api/health`

Database:

- CRM database name: `digidara_crm12`

## 3. Setup Steps

### 3.1 Backend Setup

Open PowerShell:

```powershell
cd "E:\DigiDARA AI CRM latest_riyas\backend"
venv\Scripts\activate
pip install -r requirements.txt
python seed.py
python app.py
```

Expected backend URL:

```text
http://localhost:5002
```

Health check expected response:

```json
{"app":"Digidara CRM","ok":true}
```

### 3.2 Frontend Setup

Open a second PowerShell window:

```powershell
cd "E:\DigiDARA AI CRM latest_riyas\frontend"
npm install
npm run dev
```

Expected frontend URL:

```text
http://localhost:5173
```

### 3.3 Build Verification

Before release handoff, run:

```powershell
cd "E:\DigiDARA AI CRM latest_riyas\frontend"
npm run build
```

Expected result:

- Build finishes without errors.
- `frontend/dist` is generated.

## 4. Test Accounts

Admin:

- Email: `admin@digidaratechnologies.com`
- Password: `Admin@1234`
- Expected access: all modules and actions.

Employee:

- Email: `arjun@digidaratechnologies.com`
- Password: `Emp@1234`
- Expected access: staff-scoped operational modules only.

Other seeded employees may exist:

- `sneha@digidaratechnologies.com` / `Emp@1234`
- `karthik@digidaratechnologies.com` / `Emp@1234`

## 5. Smoke Test Checklist

Run these first after every deployment or major change.

| ID | Area | Steps | Expected Result |
| --- | --- | --- | --- |
| SM-01 | Backend health | Open `/api/health` | Returns `ok: true` |
| SM-02 | Frontend load | Open `http://localhost:5173` | App loads login screen |
| SM-03 | Admin login | Log in as admin | Redirects to Dashboard |
| SM-04 | Staff login | Log out, log in as employee | Redirects to allowed CRM area |
| SM-05 | Navigation | Click each visible sidebar item | Page loads without blank screen |
| SM-06 | Theme | Toggle light/dark mode | Entire CRM theme updates |
| SM-07 | API auth | Open protected page after logout | User is redirected to login |
| SM-08 | Seed rerun | Stop backend, run `python seed.py` again | Seed completes; demo leads are not duplicated |

## 6. Authentication Tests

| ID | Test | Steps | Expected Result |
| --- | --- | --- | --- |
| AUTH-01 | Valid admin login | Use admin credentials, then enter the OTP sent to the database-registered WhatsApp number | Login succeeds and user has admin permissions |
| AUTH-02 | Valid staff login | Use employee credentials, then enter the OTP sent to the database-registered WhatsApp number | Login succeeds with staff permissions |
| AUTH-03 | Invalid password | Enter wrong password | Login fails with clear error |
| AUTH-04 | Logout | Click logout | Token/session cleared and login page shown |
| AUTH-07 | Missing registered phone | Sign in with an account whose database phone is empty | Login stops with a clear configuration message without sending an OTP |
| AUTH-08 | Invalid/expired OTP | Enter an incorrect OTP repeatedly or wait for expiry | Login is rejected and no JWT is issued |
| AUTH-09 | OTP resend | Request another OTP after the cooldown | New `staff_login_otp` message is sent and the old OTP is invalid |
| AUTH-05 | Session restore | Log in, refresh browser | User remains authenticated |
| AUTH-06 | Protected route | Clear token or logout, open `/dashboard` | Redirects to `/login` |
| AUTH-07 | Change password | Change password for a test employee | New password works; old password fails |

## 7. Role And Permission Tests

| ID | Test | Steps | Expected Result |
| --- | --- | --- | --- |
| RBAC-01 | Admin full access | Log in as admin | All configured modules are visible |
| RBAC-02 | Staff restricted access | Log in as employee | Admin-only modules/actions are hidden or blocked |
| RBAC-03 | Direct blocked URL | As staff, open `/employees` if permission is absent | 403 message or access prevented |
| RBAC-04 | Backend enforcement | Attempt restricted action from UI/API | Server rejects unauthorized action |
| RBAC-05 | Create custom role | Admin creates a role with limited page access | Role appears and can be assigned |
| RBAC-06 | Permission update | Disable a module for a custom role | User with that role loses access after re-login |
| RBAC-07 | Admin protection | Try to deactivate/demote final admin | System blocks the action |
| RBAC-08 | Self-protection | Admin tries to demote/deactivate own user | System blocks the action |

## 8. Leads Module Tests

| ID | Test | Steps | Expected Result |
| --- | --- | --- | --- |
| LEAD-01 | Load leads | Open Leads page | Counts and lead list load |
| LEAD-02 | Create course lead | Add a lead with course category | Lead appears with correct category and interest |
| LEAD-03 | Create internship lead | Add a lead with internship category | Internship fields save correctly |
| LEAD-04 | Create project lead | Add a business/project lead | Project interest saves correctly |
| LEAD-05 | Edit lead | Update phone, source, status, owner or notes | Changes persist after refresh |
| LEAD-06 | Delete lead | Delete a test lead | Lead is removed; no page crash |
| LEAD-07 | Filter leads | Use category, status, source, city and interest filters | List and counts match filters |
| LEAD-08 | Pipeline update | Move/update lead stage | Stage persists |
| LEAD-09 | Won conversion | Move lead to won as permitted user | Conversion succeeds and customer behavior is correct |
| LEAD-10 | Lost reason | Mark lead as lost with reason | Lost reason appears in reports/filtering |
| LEAD-11 | Connected-source sync | Sync configured WhatsApp, website and chatbot sources | New source records appear as leads |
| LEAD-12 | Signed intake validation | Send a missing or invalid integration signature | Request is rejected; no lead is created |
| LEAD-13 | Duplicate detection | Create/import duplicate phone/email | Duplicate view identifies possible duplicate |
| LEAD-14 | Bulk action | Select multiple leads and apply action | Only selected visible records update |
| LEAD-15 | Source retry | Submit the same source system and external ID twice | One lead is updated without duplication |
| LEAD-16 | Automatic AI classify | Create or update a lead with meaningful notes | Hot/warm/cold type, score and reason are stored automatically |
| LEAD-17 | Timeline | Open lead timeline | Activity/messages appear in chronological context |

## 9. Customers Module Tests

| ID | Test | Steps | Expected Result |
| --- | --- | --- | --- |
| CUST-01 | Load customers | Open Customers page | Overview counts and list load |
| CUST-02 | Create customer | Add a new test customer | Customer is saved |
| CUST-03 | Edit customer | Update status/contact details | Changes persist |
| CUST-04 | Delete customer | Delete a test customer | Customer removed and list refreshes |
| CUST-05 | Contact overdue | Filter contact-overdue | Customers with old/missing contact appear |
| CUST-06 | Segment filters | Filter academic/course/internship/project | Results match segment |
| CUST-07 | Customer 360 | Open customer profile | Lead, health, messages, tasks and timeline load |
| CUST-08 | Notes | Add customer note | Note appears after refresh |
| CUST-09 | Documents | Upload and open customer document | File metadata saves and download/open works |
| CUST-10 | Review request | Send review request | Success or clear integration failure shown |
| CUST-11 | Sync review | Sync review data | Success or clear integration failure shown |
| CUST-12 | Export | Export customers | CSV downloads with expected records |

## 10. Tasks And Calendar Tests

| ID | Test | Steps | Expected Result |
| --- | --- | --- | --- |
| TASK-01 | Load tasks | Open Tasks page | Task list and filters load |
| TASK-02 | Create task | Add task with due date and assignee | Task appears in list |
| TASK-03 | Staff assignment scope | As staff create task assigned to someone else | Assignment is forced to current staff user unless permitted |
| TASK-04 | Edit task | Change title, priority, due date or status | Changes persist |
| TASK-05 | Complete task | Complete a task | Status becomes completed/done |
| TASK-06 | Delete task | Delete a test task | Task removed |
| TASK-07 | Today filter | Select Today view | Only due-today tasks appear |
| TASK-08 | Overdue filter | Select Overdue view | Only overdue open tasks appear |
| TASK-09 | Calendar load | Open Calendar page | Due-dated tasks appear |
| TASK-10 | Calendar complete | Complete task from Calendar | Task is completed in Tasks page too |
| TASK-11 | Date navigation | Move between calendar ranges | Tasks update for selected range |

## 11. Dashboard And Reports Tests

| ID | Test | Steps | Expected Result |
| --- | --- | --- | --- |
| REP-01 | Dashboard load | Open Dashboard | KPI cards and charts load |
| REP-02 | Dashboard drill-down | Click clickable KPI/source/loss cards | Opens relevant filtered module |
| REP-03 | Owner report | Open Reports | Owner operating report loads |
| REP-04 | Period filter | Switch 30/90/180/365/all | Metrics refresh |
| REP-05 | Export report | Export report CSV | CSV downloads when user has export permission |
| REP-06 | Lost reasons | Add lost lead reason, refresh report | Lost reason appears in analytics |
| REP-07 | Source conversion | Check leads-by-source/source conversion sections | Counts match visible lead data |
| REP-08 | Staff report scope | Log in as staff and view allowed reporting | Data is permission-scoped or page is blocked |

## 12. Campaigns Tests

| ID | Test | Steps | Expected Result |
| --- | --- | --- | --- |
| CAMP-01 | Load campaigns | Open Campaigns | Campaign list loads |
| CAMP-02 | Create campaign | Add campaign with channel/audience/message | Campaign saved as draft/scheduled as applicable |
| CAMP-03 | Edit campaign | Change campaign details | Changes persist |
| CAMP-04 | Send campaign | Send permitted campaign | Sent count/status updates or clear integration failure |
| CAMP-05 | Schedule campaign | Schedule a future campaign | Scheduled date/status persists |
| CAMP-06 | Stats | Open campaign stats | Stats load without crash |

## 13. Communication And WhatsApp Tests

| ID | Test | Steps | Expected Result |
| --- | --- | --- | --- |
| COMM-01 | Load recipients | Open Communication | Customer recipients load by permission scope |
| COMM-02 | Search recipients | Search by name/phone/service | Matching recipients appear |
| COMM-03 | Single message | Send message to one customer | Message succeeds or clear integration failure shown |
| COMM-04 | Template replacement | Send text with `{name}` and `{service}` | Saved/sent message uses customer values |
| COMM-05 | Bulk message | Select multiple customers and send | Sent/skipped/failed counts are shown |
| COMM-06 | Message log | Open message log | Recent messages appear |
| COMM-07 | Summary create | Create AI communication summary | Summary saves with key points/next action |
| WA-01 | WhatsApp sessions | Open WhatsApp Messages | Session list loads or empty state appears |
| WA-02 | Conversation history | Select a session | Grouped history appears |
| WA-03 | Search conversations | Search contact/message | Matching sessions update |
| WA-04 | Mobile flow | Test on mobile width | List-to-chat flow is usable |

## 14. AI Feature Tests

| ID | Test | Steps | Expected Result |
| --- | --- | --- | --- |
| AI-01 | AI Chat load | Open AI Chat | Capabilities/history load |
| AI-02 | Ask summary | Ask "How many leads today?" | Structured answer appears |
| AI-03 | Ask table | Ask for a table of hot leads | Tabular output appears |
| AI-04 | Permission scope | Ask staff for CRM totals | Answer only includes staff-visible data |
| AI-05 | History | Refresh AI Chat | Previous questions reload |
| AIF-01 | Follow-up workbench | Open AI Follow-ups | Workbench data loads |
| AIF-02 | Generate follow-up | Generate for a lead | Message is generated or fallback appears |
| AIF-03 | Send follow-up | Send generated message | Status/history updates or clear integration failure |
| AIF-04 | Pause/resume | Pause and resume lead automation | Status changes correctly |
| AIF-05 | Manual follow-up | Mark manual follow-up | History records manual action |
| AIF-06 | Run engine | Run due follow-up processing | Due leads processed according to rules |

## 15. Employees And Settings Tests

| ID | Test | Steps | Expected Result |
| --- | --- | --- | --- |
| EMP-01 | Load employees | Open Employees as admin | User list and role data load |
| EMP-02 | Create employee | Create a test employee | User created with login ID |
| EMP-03 | Edit employee | Change department/branch/role/access | Changes persist |
| EMP-04 | Delete/deactivate | Remove or deactivate test employee | User is inactive or removed according to UI behavior |
| EMP-05 | Custom role | Create limited custom role | Role appears in role list |
| EMP-06 | Role permissions | Change role permission matrix | User access changes after re-login |
| SET-01 | Company settings | Update company details | Values persist |
| SET-02 | Lead options | Update course/internship/service options | Options appear in lead forms |
| SET-03 | Integration secrets | Save secret fields | Values are accepted but not exposed back in plain text |
| SET-04 | AI follow-up policy | Update interval/max count settings | Settings persist and validate |

## 16. Global Search And Notifications Tests

| ID | Test | Steps | Expected Result |
| --- | --- | --- | --- |
| SEARCH-01 | Short query | Enter one character | Search does not run or shows minimum length handling |
| SEARCH-02 | Lead search | Search seeded lead name, e.g. Priya | Lead result appears if permitted |
| SEARCH-03 | Customer search | Search seeded customer | Customer result appears if permitted |
| SEARCH-04 | Task search | Search seeded task text | Task result appears if permitted |
| SEARCH-05 | Staff scope | Search as staff | Only staff-visible records appear |
| NOTIF-01 | Bell load | Open notification bell | Newest user notifications appear |
| NOTIF-02 | Mark one read | Mark one notification read | Unread count decreases |
| NOTIF-03 | Mark all read | Mark all read | Unread count becomes zero |
| NOTIF-04 | Removed page | Open `/notifications` directly | Redirects to dashboard |

## 17. Responsive And UI Tests

| ID | Test | Steps | Expected Result |
| --- | --- | --- | --- |
| UI-01 | Desktop layout | Test at 1440 x 900 | Sidebar/topbar stable; content aligned |
| UI-02 | Laptop layout | Test at 1366 x 768 | No clipped controls or unreadable tables |
| UI-03 | Tablet layout | Test at 768 x 1024 | Navigation drawer works; forms remain usable |
| UI-04 | Mobile layout | Test at 390 x 844 | Tables become cards where expected; no page overflow |
| UI-05 | Long text | Use long names/services/notes | Text wraps without overlapping |
| UI-06 | Dialogs | Open create/edit dialogs on mobile | Dialogs fit and actions are reachable |
| UI-07 | Theme coverage | Switch light/dark on several pages | Surfaces, text and controls remain readable |

## 18. Negative And Validation Tests

| ID | Test | Steps | Expected Result |
| --- | --- | --- | --- |
| NEG-01 | Required fields | Submit empty required form | Clear validation errors |
| NEG-02 | Invalid email | Enter invalid email | Validation error |
| NEG-03 | Invalid phone | Enter invalid phone if validation applies | Error or safe handling |
| NEG-04 | Duplicate login/email | Create employee with existing email/login | Server rejects duplicate |
| NEG-05 | Unauthorized API | Call protected API without token | 401 response |
| NEG-06 | Forbidden API | Staff attempts admin-only API | 403 response |
| NEG-07 | Missing integration | Send WhatsApp/email without credentials | Clear failure, no crash |
| NEG-08 | Database unavailable | Stop MySQL and start backend | Backend reports connection/schema failure |

## 19. Regression Checklist Before Handoff

- `python seed.py` completes successfully.
- `python app.py` starts backend.
- `/api/health` returns `ok: true`.
- Admin login works.
- Staff login works.
- Frontend `npm run build` completes.
- Dashboard, Leads, Customers, Tasks, Calendar, AI Chat, AI Follow-ups, Campaigns, Communication, WhatsApp Messages, Reports, Employees and Settings load without blank screens.
- CRUD works for at least one lead, customer, task and employee test record.
- Permission restrictions work for staff.
- CSV exports download.
- Responsive checks pass on desktop, tablet and mobile.
- No browser console errors during normal navigation.
- No backend traceback appears during normal QA flow.

## 20. Bug Report Format

Use this format for every issue:

```text
Title:
Environment:
Browser:
User role:
Test case ID:
Steps to reproduce:
Expected result:
Actual result:
Screenshot/video:
Console error:
Backend error:
Severity: Critical / High / Medium / Low
```

Severity guidance:

- Critical: login blocked, app cannot start, data loss, security bypass.
- High: major module unusable, incorrect permissions, key workflow broken.
- Medium: partial workflow failure or incorrect data display.
- Low: visual issue, copy issue, minor usability problem.

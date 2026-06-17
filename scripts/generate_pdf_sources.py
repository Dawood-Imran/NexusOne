#!/usr/bin/env python3
"""Generate NexusOne synthetic PDF source documents.

The project intentionally keeps PDF generation local and dependency-free so the
setup corpus can be recreated before Postgres and ingestion exist.
"""

from __future__ import annotations

from pathlib import Path
import re
import textwrap


ROOT = Path(__file__).resolve().parents[1]
DOCUMENT_MANIFEST = ROOT / "data/generated/manifests/documents.yaml"
PERMISSION_MANIFEST = ROOT / "data/generated/manifests/permissions.yaml"
PDF_SOURCE_ROOT = ROOT / "data/generated/pdf_sources"
COMPANY = "NexusOne Technologies"


DOCUMENT_DETAILS = {
    "employee-handbook-2026": {
        "summary": "Employee-facing handbook covering probation, conduct, work hours, payroll expectations, holidays, and approved internal tools.",
        "sections": [
            ("Probation And Conduct", [
                "Standard probation is ninety calendar days unless the employment contract says otherwise.",
                "Employees are expected to follow the code of conduct, protect company information, and use approved company tools for company work.",
                "Policy questions should be sent to HR through the HR ticket queue."
            ]),
            ("Work Hours And Payroll", [
                "Core collaboration hours are 11:00 to 16:00 in the employee's primary office timezone.",
                "Payroll is processed monthly using the regional cutoff published by HR.",
                "Employees must keep HRIS profile, bank, tax, and emergency contact details current."
            ]),
            ("Internal Tools", [
                "Slack, Jira, HRIS, the Finance Portal, and the Admin Portal are available to all active employees.",
                "GitHub and AWS require additional approval because they can expose source code or production systems."
            ])
        ]
    },
    "leave-policy-2026": {
        "summary": "Employee-facing leave policy with annual, sick, parental, and region-specific request rules.",
        "sections": [
            ("Annual And Sick Leave", [
                "Annual leave must be requested in HRIS before the start date unless an emergency prevents advance notice.",
                "Sick leave longer than two working days requires supporting documentation uploaded to HRIS.",
                "Managers approve scheduling while HR verifies policy eligibility."
            ]),
            ("Parental Leave", [
                "Parental leave requests must include expected dates, region, handover owner, and required regional documents.",
                "Medical documents should be uploaded only through HRIS or an HR ticket."
            ]),
            ("Regional Rules", [
                "Pakistan, UAE, UK, and USA employees follow the regional holiday and documentation rules for their assigned work location.",
                "Work-from-abroad exceptions require manager, HR, and Admin review."
            ])
        ]
    },
    "remote-work-policy-2026": {
        "summary": "Hybrid and remote work expectations for employees across NexusOne regions.",
        "sections": [
            ("Hybrid Expectations", [
                "Employees assigned to an office should attend team anchor days when requested by their manager.",
                "Remote employees must keep a reliable internet connection and a secure workspace."
            ]),
            ("Work From Abroad", [
                "Work-from-abroad requests must be submitted before travel and include destination, dates, business reason, and coverage plan.",
                "Approval does not override tax, immigration, customer data, or security restrictions."
            ]),
            ("Equipment", [
                "Company laptops remain NexusOne property and must use the security agent.",
                "Home office monitor reimbursement follows the Finance expense policy and requires manager approval before purchase."
            ])
        ]
    },
    "expense-reimbursement-policy-2026": {
        "summary": "Employee-facing expense rules for meals, internet reimbursement, travel approval, and home office equipment.",
        "sections": [
            ("Claim Requirements", [
                "Every claim must include receipt, date, merchant, amount, category, and business purpose.",
                "Claims should be submitted in the Finance Portal before the monthly cutoff."
            ]),
            ("Common Limits", [
                "Internet reimbursement is monthly and capped by employee region.",
                "Business meals require attendee count and business purpose.",
                "Home office monitors require manager approval before purchase and are capped at the local equivalent of USD 220."
            ]),
            ("Denials", [
                "Finance may deny duplicate claims, missing receipts, personal subscriptions, unapproved software, or late claims after repeated correction requests."
            ])
        ]
    },
    "it-device-policy-2026": {
        "summary": "Employee-facing IT device policy covering laptop ownership, repairs, replacement, and battery issues.",
        "sections": [
            ("Device Ownership", [
                "Company devices remain NexusOne property and must be returned during offboarding or replacement.",
                "Employees must not lend company devices to family, friends, vendors, or unauthorized coworkers."
            ]),
            ("Repairs And Replacement", [
                "Battery failure, overheating, screen damage, and lost devices require an IT ticket.",
                "IT prioritizes replacements when the issue blocks customer work or security compliance."
            ]),
            ("Security Requirements", [
                "Devices must run disk encryption, the approved security agent, and current operating system updates.",
                "Missing security agent status may block VPN, GitHub, or AWS access."
            ])
        ]
    },
    "general-security-guidelines-2026": {
        "summary": "Company-wide security basics for MFA, passwords, phishing reporting, and internal data handling.",
        "sections": [
            ("MFA And Passwords", [
                "MFA is required for SSO, HRIS, Finance Portal, GitHub, AWS, and VPN.",
                "Employees must use the approved password manager for company credentials."
            ]),
            ("Phishing And Suspicious Activity", [
                "Report suspicious links, unexpected MFA prompts, and unusual login alerts to IT security.",
                "Do not approve an MFA prompt that you did not initiate."
            ]),
            ("Data Handling", [
                "Company documents should remain in approved tools.",
                "Restricted HR, finance, IT, executive, and CEO-only information must not be copied to public chats or personal storage."
            ])
        ]
    },
    "office-visitor-policy-2026": {
        "summary": "Office visitor and guest access policy for regional NexusOne offices.",
        "sections": [
            ("Visitor Registration", [
                "Visitors must be registered through the Admin Portal before arrival whenever possible.",
                "Registration requires visitor name, company, host, visit date, office, and business purpose."
            ]),
            ("Reception And Badges", [
                "Visitors must present photo identification and wear a guest badge while onsite.",
                "Hosts are responsible for escorting visitors and returning badges at checkout."
            ]),
            ("Restricted Areas", [
                "Server rooms, finance storage, HR case rooms, and executive meeting rooms require explicit Admin approval."
            ])
        ]
    },
    "company-holidays-2026": {
        "summary": "Regional holiday calendar for Pakistan, UAE, UK, and USA employees.",
        "sections": [
            ("Regional Calendar", [
                "Employees follow holidays for their assigned work location unless HR confirms a temporary location exception.",
                "Regional holidays are maintained in HRIS and mirrored in the public CSV source."
            ]),
            ("Company Wellness Day", [
                "NexusOne observes a company wellness day across all regions on 2026-06-12.",
                "Managers should avoid release deadlines and review deadlines on this date."
            ]),
            ("Scheduling", [
                "Customer coverage plans may require alternate coverage for teams serving multiple regions.",
                "Holiday questions should be sent to HR through an HR ticket."
            ])
        ]
    },
    "manager-handbook-2026": {
        "summary": "Manager operating guide for reviews, leave approval, team rituals, and basic people responsibilities.",
        "sections": [
            ("Manager Responsibilities", [
                "Managers own team planning, performance feedback, leave coordination, and first-level employee support.",
                "Managers must use HRIS and Jira rather than private notes for official workflow decisions."
            ]),
            ("Leave And Reviews", [
                "Managers approve leave based on coverage and handover quality while HR validates policy eligibility.",
                "Performance reviews should include evidence, examples, outcomes, and development support."
            ]),
            ("Team Rituals", [
                "Teams should maintain weekly planning, blocker review, and monthly goal check-ins.",
                "Sensitive HR issues must be routed to HR and not discussed in open team channels."
            ])
        ]
    },
    "hiring-request-process-2026": {
        "summary": "Manager hiring request workflow including headcount approval and backend engineer request details.",
        "sections": [
            ("Request Inputs", [
                "Hiring requests must include role title, department, manager, location, quarter, business reason, and budget code.",
                "Backfills require prior role reference. New roles require planned headcount or exceptional approval."
            ]),
            ("Backend Engineer Example", [
                "A backend engineer request should include service ownership need, expected stack, GitHub access, AWS access, and interview panel.",
                "Engineering manager approval is required before HR and Finance review."
            ]),
            ("Approval Flow", [
                "Managers submit requests in HRIS. HR validates job profile. Finance checks budget. Executives review exceptional or strategic roles."
            ])
        ]
    },
    "performance-improvement-plan-guide-2026": {
        "summary": "Restricted manager and HR guide for starting and documenting a performance improvement plan.",
        "sections": [
            ("When A PIP Can Start", [
                "A PIP can begin only after documented feedback, manager review, and HR consultation.",
                "The plan must describe expected outcomes, support available, check-in cadence, and evaluation date."
            ]),
            ("Documentation", [
                "Managers must include evidence from work output, role expectations, and prior feedback.",
                "Do not include medical assumptions, protected personal details, or unsupported claims."
            ]),
            ("HR Review", [
                "HR reviews the plan before employee delivery and keeps the official case record in HR systems."
            ])
        ]
    },
    "team-onboarding-checklist-2026": {
        "summary": "Manager checklist for new joiner onboarding before day one and through the first week.",
        "sections": [
            ("Before Day One", [
                "Confirm buddy, team calendar, role goals, starter tasks, and system access requirements.",
                "Engineering managers should list GitHub team, AWS account need, Jira project, and service ownership context."
            ]),
            ("First Week", [
                "Managers should run daily check-ins, explain team rituals, confirm tool access, and review security expectations.",
                "Blockers should be logged as IT, HR, Admin, or Finance tickets."
            ]),
            ("Completion", [
                "The onboarding checklist is complete after goals, tools, equipment, and manager expectations are confirmed."
            ])
        ]
    },
    "compensation-review-process-summary-2026": {
        "summary": "Manager and HR summary for compensation review, promotion input, and calibration timing.",
        "sections": [
            ("Manager Inputs", [
                "Managers submit compensation and promotion inputs after year-end performance reviews.",
                "Inputs must reference scope, impact, consistency, and role expectations."
            ]),
            ("Calibration", [
                "HR reviews consistency across teams and escalates unusual recommendations.",
                "Executives review leadership and budget-sensitive recommendations."
            ]),
            ("Employee Communication", [
                "Managers should not promise compensation outcomes before HR and Finance approval is complete."
            ])
        ]
    },
    "hr-escalation-playbook-2026": {
        "summary": "HR restricted playbook for payroll disputes, legal review, employee relations, and sensitive escalation.",
        "sections": [
            ("Payroll Disputes", [
                "HR owns employee communication and validates the employee record before Finance review.",
                "Only payroll-relevant facts should be shared with Finance."
            ]),
            ("Legal Review", [
                "Legal review is required for threats of litigation, discrimination allegations, executive employee issues, and regulatory notices.",
                "Use the fictional external counsel placeholder in test data only."
            ]),
            ("Employee Relations", [
                "Sensitive case notes must stay in the HR case record and must not appear in general ticket summaries."
            ])
        ]
    },
    "payroll-issue-handling-guide-2026": {
        "summary": "Shared HR and Finance guide for triaging payroll mistakes and adjustment requests.",
        "sections": [
            ("Triage", [
                "HR verifies employee identity, region, payroll period, and supporting documents.",
                "Finance reviews approved adjustments only after HR removes unrelated sensitive details."
            ]),
            ("Common Issues", [
                "Common payroll issues include missing bank update, incorrect tax region, unpaid leave adjustment, and delayed benefits deduction.",
                "Employees should submit issues through HR tickets rather than direct Finance messages."
            ]),
            ("Escalation", [
                "High-impact payroll errors require HR lead and Finance payroll owner review within two working days."
            ])
        ]
    },
    "employee-relations-case-guide-2026": {
        "summary": "HR sensitive guide for employee relations complaints, documentation, privacy, and case visibility.",
        "sections": [
            ("Case Intake", [
                "HR logs source, date, parties, summary, immediate risk, and requested support.",
                "Intake should avoid conclusions before review is complete."
            ]),
            ("Visibility", [
                "Only assigned HR staff, the Head of People, and approved legal reviewers can access full case notes.",
                "Managers receive only action-specific guidance unless HR authorizes more detail."
            ]),
            ("Documentation", [
                "Case notes must separate direct statements, documents reviewed, HR observations, and next actions."
            ])
        ]
    },
    "benefits-vendor-details-2026": {
        "summary": "HR restricted vendor guide for fictional insurance, wellness, and regional benefits partners.",
        "sections": [
            ("Vendor Matrix", [
                "CarePlus Fictional supports Pakistan health insurance.",
                "GulfWell Fictional supports UAE health insurance.",
                "NorthBridge Wellness supports UK wellness reimbursements."
            ]),
            ("Renewal Tracking", [
                "HR tracks vendor renewal dates in the benefits vendor CSV and escalates renewals ninety days before expiry."
            ]),
            ("Employee Questions", [
                "Employees should not contact vendor account managers directly unless HR provides an approved contact route."
            ])
        ]
    },
    "hr-ticket-triage-sop-2026": {
        "summary": "HR restricted SOP for prioritizing payroll, leave, benefits, HRIS, and employee relations tickets.",
        "sections": [
            ("Priority Rules", [
                "Employee relations and payroll-blocking issues receive priority review.",
                "Routine HRIS corrections and benefit clarifications follow standard SLA."
            ]),
            ("Assignment", [
                "Tickets are assigned based on category, region, and sensitivity.",
                "Sensitive tickets must not expose details in manager-visible summaries."
            ]),
            ("SLA", [
                "Payroll issues target three working days. Employee relations tickets target one working day for first response."
            ])
        ]
    },
    "it-security-runbook-2026": {
        "summary": "IT restricted runbook for suspected credential compromise, containment, and incident response.",
        "sections": [
            ("Credential Compromise", [
                "Disable active sessions, require MFA reset, rotate impacted tokens, and review recent access logs.",
                "Notify the incident commander for customer-impacting or production-impacting events."
            ]),
            ("Containment", [
                "Containment actions must be recorded in the IT incident ticket with time, actor, system, and result.",
                "Do not delete evidence before security review."
            ]),
            ("Recovery", [
                "Restore access only after device health, MFA reset, password rotation, and owner approval are complete."
            ])
        ]
    },
    "admin-access-recovery-guide-2026": {
        "summary": "IT restricted guide for recovering GitHub, AWS, and privileged administrator access.",
        "sections": [
            ("Identity Validation", [
                "Validate requester identity through SSO profile, manager confirmation, and existing admin roster.",
                "Recovery cannot rely on Slack message claims alone."
            ]),
            ("GitHub And AWS", [
                "GitHub admin recovery requires repository owner and IT admin approval.",
                "AWS admin recovery requires incident or service-owner reference and time-limited access."
            ]),
            ("Evidence", [
                "Attach approval, start time, end time, and privilege removal evidence to the ticket."
            ])
        ]
    },
    "device-inventory-procedure-2026": {
        "summary": "IT restricted device tracking procedure for assignment, returns, retirement, and inventory reconciliation.",
        "sections": [
            ("Assignment", [
                "Every laptop must have asset tag, assigned user, serial number placeholder, location, and security-agent status.",
                "New joiner devices should be assigned before day one when possible."
            ]),
            ("Returns", [
                "Returned devices must be checked for condition, encryption status, and offboarding wipe completion.",
                "Missing devices require IT and Admin coordination."
            ]),
            ("Retirement", [
                "Retired devices must be wiped, logged, and marked inactive in inventory before disposal."
            ])
        ]
    },
    "privileged-access-process-2026": {
        "summary": "IT restricted process for production, admin, and break-glass access approval.",
        "sections": [
            ("Standard Approval", [
                "Privileged access requires business reason, system owner, manager approval, scope, and expiration.",
                "Production access must be least privilege and time-limited."
            ]),
            ("Break-Glass", [
                "Break-glass access is allowed only for active incidents with incident commander approval.",
                "All actions must be reviewed within one working day."
            ]),
            ("Removal", [
                "Access must be removed at expiration and evidence must be attached to the ticket."
            ])
        ]
    },
    "software-access-control-policy-2026": {
        "summary": "Software access rules for Slack, Jira, GitHub, AWS, and other approved systems.",
        "sections": [
            ("Standard Tools", [
                "Slack, Jira, HRIS, Finance Portal, and Admin Portal are provisioned through SSO.",
                "GitHub and AWS need separate IT access tickets and approval."
            ]),
            ("Approval", [
                "GitHub write access requires service owner or manager approval.",
                "AWS access requires environment, account, business reason, and duration."
            ]),
            ("Restricted Appendix", [
                "Administrative and production access follows the privileged access process and is not granted through standard employee requests."
            ])
        ]
    },
    "quarterly-finance-summary-q4-2025": {
        "summary": "Restricted Q4 finance summary covering fictional revenue, gross margin, burn rate, runway, and renewal timing.",
        "sections": [
            ("Q4 Metrics", [
                "Fictional Q4 revenue was USD 4.85M with 68 percent gross margin.",
                "Monthly burn was USD 780K and runway was estimated at fifteen months."
            ]),
            ("Trend Notes", [
                "Revenue improved against Q3 but remained concentrated in two fictional enterprise renewal discussions.",
                "Engineering cloud tests and customer reporting automation increased spend variance."
            ]),
            ("Access Reminder", [
                "This report is restricted to Finance, executives, and the CEO. Unauthorized users should receive only public policy context or refusal."
            ])
        ]
    },
    "department-budget-summary-2026": {
        "summary": "Restricted department budget report for utilization, forecast spend, and variance risk.",
        "sections": [
            ("Budget Utilization", [
                "Engineering Q1 forecast is USD 735K against USD 700K allocation, creating a medium variance risk.",
                "Executive Q1 forecast is USD 360K against USD 320K allocation, creating a high variance risk."
            ]),
            ("Drivers", [
                "Engineering variance is linked to staging capacity and reporting automation.",
                "Admin variance is linked to access-card modernization and regional supplier timing."
            ]),
            ("Review", [
                "Finance reviews budget requests against committed spend, forecast spend, and revenue-risk mitigation."
            ])
        ]
    },
    "vendor-payment-aging-report-q1-2026": {
        "summary": "Restricted vendor aging report using fictional vendors and payment statuses.",
        "sections": [
            ("Aging Snapshot", [
                "CloudBridge Labs has USD 42K due at twenty-one days overdue and awaits department owner approval.",
                "Northstar Facilities has USD 18.5K due at thirty-four days overdue and awaits vendor tax correction."
            ]),
            ("Risk Handling", [
                "Vendors tied to customer delivery are flagged before payment delay.",
                "Invoices older than thirty days require Finance lead review."
            ]),
            ("Process", [
                "Finance validates invoice, purchase approval, tax status, payment timing, and reconciliation evidence."
            ])
        ]
    },
    "expense-audit-notes-q4-2025": {
        "summary": "Restricted expense audit observations for fictional policy exceptions and reimbursement categories.",
        "sections": [
            ("Audit Themes", [
                "Most exceptions involved missing receipts, late internet claims, and unapproved software subscriptions.",
                "A small set of home office monitor claims lacked manager approval before purchase."
            ]),
            ("Corrective Actions", [
                "Finance will update claim prompts and require manager approval evidence for monitor reimbursement.",
                "Repeat exceptions are escalated to the Finance lead."
            ]),
            ("Access", [
                "Employees can see public expense rules but not audit notes, exception patterns, or restricted category analysis."
            ])
        ]
    },
    "finance-ticket-handling-sop-2026": {
        "summary": "Finance restricted SOP for reimbursement, vendor payment, payroll handoff, and budget request tickets.",
        "sections": [
            ("Ticket Categories", [
                "Finance tickets include reimbursement, budget request, payroll handoff, vendor payment, and forecast question.",
                "Payroll handoff tickets require HR approval before Finance action."
            ]),
            ("SLA", [
                "Reimbursement correction first response target is two working days.",
                "Vendor payment and forecast questions are prioritized by business impact and executive sensitivity."
            ]),
            ("Visibility", [
                "Employees see only their own tickets. Finance sees the Finance queue. Managers see limited summaries when policy allows."
            ])
        ]
    },
    "board-meeting-summary-q4-2025": {
        "summary": "Executive restricted board summary with fictional action items and Q4 strategy discussion.",
        "sections": [
            ("Board Discussion", [
                "The board discussed renewal concentration, reporting automation, hiring pace, and spend governance.",
                "The CEO was asked to prepare a renewal-risk mitigation plan for Customer A and NexusRetail."
            ]),
            ("Action Items", [
                "Finance will model runway under delayed Q1 renewals.",
                "Product will present automation roadmap with support-volume impact.",
                "People will compare hiring plan with approved budget."
            ]),
            ("Access", [
                "Unauthorized users must not receive board action items or restricted source names."
            ])
        ]
    },
    "q4-revenue-risk-register-2025": {
        "summary": "Executive and Finance restricted Q4 revenue risk register with fictional account segments and mitigation owners.",
        "sections": [
            ("Top Risks", [
                "Customer A enterprise segment has USD 620K fictional revenue at risk with 0.65 probability.",
                "NexusRetail operations group has USD 410K fictional expansion risk with 0.45 probability.",
                "Partner integration cohort has USD 260K fictional implementation delay risk with 0.55 probability."
            ]),
            ("Mitigations", [
                "Weekly renewal checkpoints, reporting automation, and engineering integration ownership are the primary mitigations.",
                "Customer Success owns executive-facing renewal status updates."
            ]),
            ("Permission Test", [
                "Employees asking about Q4 revenue risks should not receive these details. The CEO should receive detailed cited context."
            ])
        ]
    },
    "company-strategy-memo-2026": {
        "summary": "Executive restricted strategy memo for 2026 priorities, expansion, automation, growth, and investment.",
        "sections": [
            ("Strategic Priorities", [
                "Reduce manual customer reporting by forty percent through workflow automation.",
                "Improve enterprise renewal readiness for Customer A, NexusRetail, and AtlasPay fictional segments.",
                "Expand selectively in UAE and UK while monitoring support capacity."
            ]),
            ("Investment Constraints", [
                "Hiring, cloud spend, and vendor commitments must align with finance review and runway assumptions.",
                "Executive hiring is reviewed separately from manager hiring requests."
            ]),
            ("Operating Model", [
                "Teams should connect project status, budget risk, and customer escalation themes in executive review."
            ])
        ]
    },
    "acquisition-opportunity-notes-2026": {
        "summary": "CEO-only fictional acquisition opportunity notes for strict user-specific permission testing.",
        "sections": [
            ("Fictional Target", [
                "HelioOps is a fictional workflow automation vendor under early evaluation.",
                "The fictional valuation range is USD 6.5M to USD 8.0M."
            ]),
            ("Evaluation", [
                "Product fit is strongest around reporting automation and internal ticket taxonomy.",
                "Key risk is customer concentration in one regional segment."
            ]),
            ("Handling Rule", [
                "Only user u006 with CEO role can access this document. Other users must not see title, target name, valuation, path, or summary."
            ])
        ]
    },
    "executive-hiring-plan-2026": {
        "summary": "Executive restricted hiring plan for leadership roles, critical hires, and growth support.",
        "sections": [
            ("Critical Roles", [
                "The fictional Chief Revenue Officer role remains under executive-only review.",
                "Customer Success leadership capacity is monitored due to enterprise renewal concentration."
            ]),
            ("Budget Alignment", [
                "Leadership hiring must be compared with department budget utilization and revenue-risk mitigation.",
                "People and Finance review role timing before executive approval."
            ]),
            ("Dependency", [
                "Manager hiring requests handle team roles. Executive hiring plan handles leadership and strategic roles."
            ])
        ]
    },
    "company-risk-register-2026": {
        "summary": "Executive restricted risk register covering legal, finance, security, and customer risks.",
        "sections": [
            ("Risk Categories", [
                "Finance risk includes delayed renewals and budget variance.",
                "Security risk includes credential compromise and privileged access misuse.",
                "Customer risk includes reporting automation delays and support handoff issues."
            ]),
            ("Controls", [
                "Finance reviews budget variance monthly.",
                "IT reviews privileged access logs after break-glass use.",
                "Customer Success reports escalation themes to executives."
            ]),
            ("Retrieval Behavior", [
                "Executives and the CEO can receive risk details. Employees should receive public summaries or refusal without restricted titles."
            ])
        ]
    },
}


def parse_inline_list(value: str) -> list[str]:
    value = value.strip()
    if value == "[]":
        return []
    if value.startswith("[") and value.endswith("]"):
        inner = value[1:-1].strip()
        if not inner:
            return []
        return [item.strip().strip('"').strip("'") for item in inner.split(",")]
    return [value]


def parse_documents() -> list[dict[str, object]]:
    documents: list[dict[str, object]] = []
    current: dict[str, object] | None = None

    for raw_line in DOCUMENT_MANIFEST.read_text(encoding="utf-8").splitlines():
        line = raw_line.rstrip()
        start = re.match(r"^  - doc_id: (.+)$", line)
        if start:
            if current:
                documents.append(current)
            current = {"doc_id": start.group(1).strip()}
            continue
        if not current:
            continue
        field = re.match(r"^    ([a-z_]+): (.+)$", line)
        if not field:
            continue
        key = field.group(1)
        value = field.group(2).strip()
        if key == "key_topics":
            current[key] = parse_inline_list(value)
        else:
            current[key] = value

    if current:
        documents.append(current)

    return [doc for doc in documents if doc.get("source_type") == "pdf"]


def parse_permission_profiles() -> dict[str, dict[str, object]]:
    profiles: dict[str, dict[str, object]] = {}
    in_profiles = False
    current_name: str | None = None
    current_field: str | None = None

    for raw_line in PERMISSION_MANIFEST.read_text(encoding="utf-8").splitlines():
        line = raw_line.rstrip()
        if line == "permission_profiles:":
            in_profiles = True
            continue
        if line == "tool_permissions:":
            break
        if not in_profiles:
            continue

        profile = re.match(r"^  ([a-z0-9_]+):$", line)
        if profile:
            current_name = profile.group(1)
            profiles[current_name] = {
                "confidentiality": "",
                "allowed_roles": [],
                "allowed_groups": [],
                "allowed_users": [],
            }
            current_field = None
            continue

        if not current_name:
            continue

        scalar = re.match(r"^    ([a-z_]+): (.+)$", line)
        if scalar:
            key = scalar.group(1)
            value = scalar.group(2).strip()
            current_field = None
            if key == "confidentiality":
                profiles[current_name][key] = value
            elif key in {"allowed_roles", "allowed_groups", "allowed_users"}:
                profiles[current_name][key] = parse_inline_list(value)
                current_field = key if value != "[]" else None
            continue

        list_start = re.match(r"^    (allowed_roles|allowed_groups|allowed_users):$", line)
        if list_start:
            current_field = list_start.group(1)
            profiles[current_name][current_field] = []
            continue

        item = re.match(r"^      - (.+)$", line)
        if item and current_field:
            profiles[current_name][current_field].append(item.group(1).strip())

    return profiles


def yaml_list(items: list[str]) -> str:
    if not items:
        return "[]"
    return "[" + ", ".join(items) + "]"


def markdown_for_document(doc: dict[str, object], profile: dict[str, object]) -> str:
    doc_id = str(doc["doc_id"])
    detail = DOCUMENT_DETAILS.get(doc_id)
    if not detail:
        raise KeyError(f"Missing PDF content for {doc_id}")

    key_topics = doc.get("key_topics", [])
    if not isinstance(key_topics, list):
        key_topics = []

    lines = [
        "---",
        f"doc_id: {doc_id}",
        f"title: {doc['title']}",
        "source_type: pdf",
        f"source_path: {doc['source_path']}",
        f"department: {doc['department']}",
        f"permission_profile: {doc['permission_profile']}",
        f"confidentiality: {profile['confidentiality']}",
        f"allowed_roles: {yaml_list(profile['allowed_roles'])}",
        f"allowed_groups: {yaml_list(profile['allowed_groups'])}",
        f"allowed_users: {yaml_list(profile['allowed_users'])}",
        f"updated_at: {doc['updated_at']}",
        "canonical: true",
        "generated: true",
        "---",
        "",
        f"# {doc['title']}",
        "",
        "## Document Control",
        "",
        f"- Company: {COMPANY}",
        f"- Document ID: {doc_id}",
        f"- Owner department: {doc['department']}",
        f"- Permission profile: {doc['permission_profile']}",
        f"- Confidentiality: {profile['confidentiality']}",
        f"- Last updated: {doc['updated_at']}",
        f"- Key topics: {', '.join(key_topics)}",
        "",
        "## Access Scope",
        "",
        f"- Allowed roles: {', '.join(profile['allowed_roles']) or 'none'}",
        f"- Allowed groups: {', '.join(profile['allowed_groups']) or 'none'}",
        f"- Allowed users: {', '.join(profile['allowed_users']) or 'none'}",
        "",
        "## Summary",
        "",
        str(detail["summary"]),
        "",
    ]

    for heading, paragraphs in detail["sections"]:
        lines.extend([f"## {heading}", ""])
        for paragraph in paragraphs:
            lines.append(f"- {paragraph}")
        lines.append("")

    lines.extend([
        "## Data Generation Notice",
        "",
        "- This is synthetic NexusOne Technologies data for local RAG, SQL, FAISS, and permission-filter testing.",
        "- Do not replace this file with real company, employee, customer, vendor, financial, HR, security, or acquisition data.",
        "",
    ])

    return "\n".join(lines)


def escape_pdf_text(value: str) -> str:
    return value.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def text_lines(markdown: str) -> list[tuple[str, int, int, int]]:
    lines: list[tuple[str, int, int, int]] = []
    for raw_line in markdown.splitlines():
        line = raw_line.strip()
        if not line or line == "---":
            lines.append(("", 10, 10, 0))
            continue
        if line.startswith("# "):
            lines.extend([("", 10, 8, 0), (line[2:], 18, 24, 0)])
            continue
        if line.startswith("## "):
            lines.extend([("", 10, 8, 0), (line[3:], 13, 18, 0)])
            continue
        if line.startswith("- "):
            wrapped = textwrap.wrap(line[2:], width=88)
            for index, wrapped_line in enumerate(wrapped):
                prefix = "- " if index == 0 else "  "
                lines.append((prefix + wrapped_line, 10, 14, 16))
            continue
        if line.startswith(("doc_id:", "title:", "source_type:", "source_path:", "department:", "permission_profile:", "confidentiality:", "allowed_", "updated_at:", "canonical:", "generated:")):
            continue
        for wrapped_line in textwrap.wrap(line, width=96):
            lines.append((wrapped_line, 10, 14, 0))
    return lines


def paginate(lines: list[tuple[str, int, int, int]]) -> list[list[tuple[str, int, int, int]]]:
    pages: list[list[tuple[str, int, int, int]]] = []
    current: list[tuple[str, int, int, int]] = []
    y = 700
    bottom = 78

    for line in lines:
        _, _, leading, _ = line
        if current and y - leading < bottom:
            pages.append(current)
            current = []
            y = 700
        current.append(line)
        y -= leading

    if current:
        pages.append(current)
    return pages


def render_stream(page_lines: list[tuple[str, int, int, int]], title: str, page_number: int, page_count: int) -> bytes:
    commands = [
        "BT /F1 9 Tf 1 0 0 1 54 742 Tm (NexusOne Technologies | Synthetic Internal Document) Tj ET",
        f"BT /F1 9 Tf 1 0 0 1 54 724 Tm ({escape_pdf_text(title)}) Tj ET",
    ]

    y = 700
    for text, size, leading, indent in page_lines:
        if text:
            commands.append(
                f"BT /F1 {size} Tf 1 0 0 1 {54 + indent} {y} Tm ({escape_pdf_text(text)}) Tj ET"
            )
        y -= leading

    footer = f"Page {page_number} of {page_count}"
    commands.append(f"BT /F1 9 Tf 1 0 0 1 54 42 Tm ({escape_pdf_text(footer)}) Tj ET")
    return ("\n".join(commands) + "\n").encode("latin-1")


def write_pdf(path: Path, title: str, markdown: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pages = paginate(text_lines(markdown))
    streams = [
        render_stream(page, title, index + 1, len(pages))
        for index, page in enumerate(pages)
    ]

    objects: list[bytes] = []
    objects.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    objects.append(b"")  # Pages object placeholder.
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")

    page_object_ids: list[int] = []
    for stream in streams:
        page_obj_id = len(objects) + 1
        content_obj_id = len(objects) + 2
        page_object_ids.append(page_obj_id)
        objects.append(
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 3 0 R >> >> /Contents {content_obj_id} 0 R >>".encode("latin-1")
        )
        objects.append(
            b"<< /Length " + str(len(stream)).encode("latin-1") + b" >>\nstream\n" + stream + b"endstream"
        )

    kids = " ".join(f"{object_id} 0 R" for object_id in page_object_ids)
    objects[1] = f"<< /Type /Pages /Kids [{kids}] /Count {len(page_object_ids)} >>".encode("latin-1")

    output = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for index, obj in enumerate(objects, start=1):
        offsets.append(len(output))
        output.extend(f"{index} 0 obj\n".encode("latin-1"))
        output.extend(obj)
        output.extend(b"\nendobj\n")

    xref_start = len(output)
    output.extend(f"xref\n0 {len(objects) + 1}\n".encode("latin-1"))
    output.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        output.extend(f"{offset:010d} 00000 n \n".encode("latin-1"))
    output.extend(
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_start}\n%%EOF\n".encode("latin-1")
    )

    path.write_bytes(output)


def main() -> None:
    documents = parse_documents()
    profiles = parse_permission_profiles()

    generated = 0
    for doc in documents:
        profile_name = str(doc["permission_profile"])
        if profile_name not in profiles:
            raise KeyError(f"Missing permission profile {profile_name}")
        markdown = markdown_for_document(doc, profiles[profile_name])

        pdf_path = ROOT / str(doc["source_path"])
        source_path = PDF_SOURCE_ROOT / pdf_path.relative_to(ROOT / "data/docs/pdf")
        source_path = source_path.with_suffix(".md")

        source_path.parent.mkdir(parents=True, exist_ok=True)
        source_path.write_text(markdown, encoding="utf-8")
        write_pdf(pdf_path, str(doc["title"]), markdown)
        generated += 1

    print(f"Generated {generated} PDF files")
    print(f"Generated {generated} Markdown source files under {PDF_SOURCE_ROOT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()

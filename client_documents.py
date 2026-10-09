"""RETEC client-operations document templates.

Static document content for the client lifecycle: the agreement clause set,
the handover checklist, and the default proposal wording. Data that varies per
project (fees, dates, scope) lives on the models in app.py and is substituted
into these templates at render time.

Nothing here is legal advice. The agreement is a business document template
that must be reviewed with a qualified Kenyan legal professional before any
commercial use -- see AGREEMENT_DISCLAIMER, which is rendered on every
agreement view.
"""

import re

# Studio identity. These are the public contact details already shown on the
# website; nothing here is invented for the document set.
RETEC_INFO = {
    'name': 'RETEC',
    'tagline': 'Biz Yako. Tech Yetu.',
    'email': 'contact.retec@gmail.com',
    'phone': '+254 114 581500',
    'whatsapp': 'https://wa.me/+254114581500',
    'website': 'https://retec.onrender.com',
}

AGREEMENT_DISCLAIMER = (
    'Template — Review with a qualified Kenyan legal professional before '
    'commercial use.'
)

AGREEMENT_NOTE = (
    'This document is a business document template, not legal advice. It has '
    'not been reviewed by a lawyer and is not claimed to be legally sufficient '
    'or legally binding in every situation. Have it reviewed by a qualified '
    'Kenyan legal professional before you rely on it for a real engagement.'
)

# Project-specific values substituted into the agreement. Anything left
# unsubstituted is rendered verbatim, which is how a draft advertises that it
# still has gaps rather than pretending to be complete.
AGREEMENT_PLACEHOLDERS = (
    'CLIENT NAME',
    'BUSINESS NAME',
    'PROJECT NAME',
    'PROJECT DESCRIPTION',
    'PROJECT FEE',
    'DEPOSIT PERCENTAGE',
    'PAYMENT TERMS',
    'PROJECT START DATE',
    'EXPECTED DELIVERY DATE',
    'SUPPORT PERIOD',
)

_PLACEHOLDER_RE = re.compile(r'\[[A-Z][A-Z0-9 _/]*\]')


def fill_placeholders(text, values):
    """Substitute ``[PLACEHOLDER]`` tokens from ``values``.

    Returns ``(text, missing)`` where ``missing`` is the sorted list of
    placeholder names that had no value. ``None`` means "not known yet": the
    token is left in the text so a draft always shows exactly what it is
    missing, while an explicit empty string is an intentional blank and
    disappears.
    """
    missing = set()

    def replace(match):
        key = match.group(0)[1:-1]
        if key not in values or values[key] is None:
            missing.add(key)
            return match.group(0)
        return str(values[key])

    return _PLACEHOLDER_RE.sub(replace, text), sorted(missing)


# ===== CLIENT SERVICES AGREEMENT =====
#
# Plain-English clause set structured for Kenyan business use. Every clause
# that needs a project-specific value uses a placeholder from
# AGREEMENT_PLACEHOLDERS. No clause is written to require specialist legal
# interpretation.

AGREEMENT_CLAUSES = [
    ('Parties',
     'This Client Services Agreement is between RETEC ("we", "us" or "RETEC"), '
     'a digital studio, and [CLIENT NAME] ("the Client")'
     '[BUSINESS_SUFFIX].'),

    ('Definitions',
     '"Project" means the work described in this agreement and in the accepted '
     'proposal for it. "Deliverables" means the items RETEC agrees to produce. '
     '"Fees" means the amount stated for the Project. "In writing" means by '
     'email or by a document signed by both parties.'),

    ('Project description',
     'The Client has asked RETEC to carry out the following project: '
     '[PROJECT NAME]. [PROJECT DESCRIPTION]'),

    ('Scope of work',
     'The work RETEC will perform is set out in the accepted proposal for this '
     'project, which is part of this agreement. Anything not described there '
     'is outside the scope until both parties agree to add it in writing.'),

    ('Deliverables',
     'RETEC will produce the Deliverables listed in the accepted proposal. '
     'Delivery formats and quantities are those stated there.'),

    ('Timeline',
     'Work is expected to start on [PROJECT START DATE] with expected delivery '
     'on [EXPECTED DELIVERY DATE]. Dates depend on the Client providing '
     'content, feedback and approvals on time. If the Client delays, delivery '
     'dates move accordingly and RETEC will say so in writing.'),

    ('Client responsibilities',
     'The Client will: choose one person who can approve decisions; supply '
     'content, images, credentials and other materials when asked; reply to '
     'requests for feedback within the agreed window; ensure they have the '
     'right to use anything they supply; and pay the Fees on time.'),

    ('RETEC responsibilities',
     'RETEC will: perform the work with reasonable skill and care; keep the '
     'Client informed about progress and any risk to the timeline; keep the '
     'Client\'s confidential information confidential as described below; and '
     'deliver the Deliverables described in the accepted proposal.'),

    ('Fees',
     'The total Fee for the Project is [PROJECT FEE]. The Fee covers only the '
     'scope described in the accepted proposal.'),

    ('Deposit',
     'A deposit of [DEPOSIT PERCENTAGE] of the Project Fee is due before work '
     'starts. Work begins once the deposit has been received.'),

    ('Payment schedule',
     'Payment terms for this Project: [PAYMENT TERMS]. Amounts are payable by '
     'the payment method both parties agree in writing.'),

    ('Late payment',
     'If an amount is overdue, RETEC may pause work until it is paid. '
     'Persistent late payment is grounds for ending the agreement under the '
     'cancellation clause below. Any additional charge for overdue amounts '
     'must be agreed in writing before it applies.'),

    ('Taxes and third-party costs',
     'Third-party costs such as hosting, domain registration, software '
     'licences, stock assets and payment-provider fees are the Client\'s cost '
     'unless the accepted proposal states that RETEC is covering them. Any '
     'taxes that legally apply to the Fees are the Client\'s '
     'responsibility.'),

    ('Revisions',
     'The number of revision rounds included in the Fees is stated in the '
     'accepted proposal. Revisions beyond that limit, or changes to work that '
     'has already been approved, are additional work and are quoted before '
     'they are done.'),

    ('Change requests',
     'The Client may ask for changes at any time. RETEC will describe the '
     'effect of the change on price and timeline in writing. Work on a change '
     'starts only after the Client accepts that description.'),

    ('Scope creep',
     'Requests that add features, pages, screens or integrations not in the '
     'accepted proposal are outside the scope. They are treated as change '
     'requests and are not absorbed silently into the existing Fee.'),

    ('Client delays',
     'If the Client does not supply materials, feedback or approval within '
     'the agreed window, the timeline extends by at least the length of the '
     'delay. If a delay continues for [DELAY WINDOW] or more, RETEC may '
     'invoice work completed so far and reschedule the remainder.'),

    ('Approval and acceptance',
     'The Client accepts a Deliverable by confirming acceptance in writing '
     '(including email). If the Client reports a genuine defect, RETEC will '
     'correct it at no cost within the support period described below.'),

    ('Cancellation',
     'Either party may end this agreement by giving written notice. On '
     'cancellation, the Client pays for work completed and any costs RETEC '
     'has already committed to (such as a paid domain or licence), and RETEC '
     'hands over the work completed up to that point.'),

    ('Refunds',
     'Payments already made are not refundable for work that has been '
     'completed. For work not yet performed, RETEC will refund the '
     'corresponding portion of the Fees, less any third-party costs already '
     'committed on the Client\'s behalf.'),

    ('Intellectual property',
     'Once the Fees have been paid in full, the Client owns the final '
     'Deliverables produced specifically for this Project, to the extent '
     'needed to use them for the Client\'s business. Until payment is '
     'complete, RETEC keeps its rights in the work.'),

    ('Pre-existing RETEC materials',
     'Tools, code libraries, components and methods that RETEC already had '
     'before this Project, or develops for general reuse, remain RETEC\'s '
     'property. Where they are used in the Deliverables, RETEC licenses them '
     'to the Client for use of the Deliverables as delivered.'),

    ('Third-party software and services',
     'Any third-party software, fonts, plugins, APIs or services used in the '
     'Project are licensed under their own terms. Those terms continue to '
     'apply after delivery, and the Client is responsible for keeping any '
     'accounts required to use them.'),

    ('Hosting and domain',
     'Unless the accepted proposal says otherwise, hosting and domain '
     'registration are arranged in the Client\'s name and paid by the Client. '
     'RETEC will document the accounts, access details and renewal dates at '
     'handover.'),

    ('Content supplied by the Client',
     'The Client is responsible for the accuracy of content, images, data and '
     'other materials the Client supplies, and confirms that RETEC may use '
     'them for the Project. RETEC is not responsible for third-party claims '
     'arising from content the Client supplied.'),

    ('Confidentiality',
     'Each party will keep the other\'s non-public information confidential '
     'and will use it only for this Project. This continues after the '
     'agreement ends, for as long as the information remains confidential.'),

    ('Data protection',
     'Each party will handle personal data in line with applicable data '
     'protection law, including the Data Protection Act, 2019 (Kenya) where it '
     'applies. If RETEC processes personal data on the Client\'s behalf, both '
     'parties will agree in writing what instructions, safeguards and roles '
     'apply.'),

    ('Security',
     'RETEC will take reasonable technical measures to protect project '
     'materials and any data it hosts for the Client. The Client is '
     'responsible for the security of its own accounts, devices and '
     'credentials, and for telling RETEC promptly if an account connected to '
     'the Project is compromised.'),

    ('Maintenance and support',
     'After delivery, RETEC will provide the support described in the accepted '
     'proposal for [SUPPORT PERIOD]. Support covers help with what was '
     'delivered; new features are additional work.'),

    ('Bug fixes and warranty',
     'During the support period, RETEC will correct genuine defects in the '
     'Deliverables at no cost. Issues caused by changes made by the Client or '
     'by third parties, or by requests for new features, are not defects and '
     'are quoted separately.'),

    ('Limitation of liability',
     'To the extent the law allows, RETEC\'s total liability under this '
     'agreement is limited to the Fees actually paid for the Project. Neither '
     'party is liable to the other for indirect or consequential loss. Nothing '
     'in this agreement limits liability in a way the law does not permit.'),

    ('Force majeure',
     'Neither party is responsible for delay or failure caused by events '
     'outside its reasonable control, such as power or internet failure, '
     'natural disaster, war, civil unrest, or the failure of a third-party '
     'service. The affected party will notify the other and both parties will '
     'agree how to proceed.'),

    ('Dispute resolution',
     'If a dispute arises, the parties will first discuss it in good faith. '
     'If that does not resolve it, either party may ask for mediation before '
     'starting legal proceedings. Both parties keep working together in good '
     'faith while this process runs, where it is practical to do so.'),

    ('Governing law and jurisdiction',
     'This agreement is governed by the laws of Kenya, and the courts of Kenya '
     'have jurisdiction over it.'),

    ('Changes to this agreement',
     'Changes are valid only if they are in writing and confirmed by both '
     'parties (email confirmation is sufficient).'),

    ('Entire agreement',
     'This agreement, together with the accepted proposal for the Project, is '
     'the entire agreement between the parties about the Project, and replaces '
     'earlier discussions or understandings about it.'),
]

# Placeholder used inside a clause body; resolved from a small extra mapping
# so clause text can interpolate computed values too.
AGREEMENT_EXTRA_PLACEHOLDERS = ('BUSINESS_SUFFIX', 'DELAY WINDOW')

AGREEMENT_DEFAULTS = {
    'DELAY WINDOW': '14 days',
}


def render_agreement_clauses(values=None):
    """Render every clause with placeholders filled.

    ``values`` maps placeholder names (without brackets) to project-specific
    values; defaults from ``AGREEMENT_DEFAULTS`` are applied first. Returns a
    list of ``(number, heading, text, missing)`` tuples and the union of all
    missing placeholder names.
    """
    merged = dict(AGREEMENT_DEFAULTS)
    if values:
        merged.update(values)
    rendered = []
    missing_all = set()
    for index, (heading, body) in enumerate(AGREEMENT_CLAUSES, start=1):
        text, missing = fill_placeholders(body, merged)
        missing_all.update(missing)
        rendered.append((index, heading, text, missing))
    return rendered, sorted(missing_all)


# ===== HANDOVER CHECKLIST =====

HANDOVER_CHECKLIST = [
    ('Project completion', [
        ('final_review', 'Final review completed'),
        ('client_approval', 'Client approval received'),
        ('final_payment', 'Final payment confirmed'),
        ('deployment', 'Production deployment completed'),
        ('domain', 'Domain connected'),
        ('ssl', 'SSL confirmed'),
        ('forms', 'Forms tested'),
        ('links', 'Links tested'),
        ('responsive', 'Responsive testing completed'),
        ('browsers', 'Major browser testing completed'),
        ('analytics', 'Analytics configured (if included)'),
        ('seo', 'SEO basics configured (if included)'),
    ]),
    ('Handover', [
        ('credentials', 'Admin credentials transferred securely'),
        ('documentation', 'Relevant documentation delivered'),
        ('code_ownership', 'Source / code ownership handled according to agreement'),
        ('assets', 'Assets delivered'),
        ('domain_hosting', 'Domain / hosting information documented'),
        ('third_party_accounts', 'Third-party account ownership clarified'),
        ('backup', 'Backup created where applicable'),
    ]),
    ('Support', [
        ('support_period', 'Support period documented'),
        ('maintenance_terms', 'Maintenance terms explained'),
        ('future_work', 'Future work process explained'),
    ]),
]

HANDOVER_ITEM_IDS = {
    item_id for _, items in HANDOVER_CHECKLIST for item_id, _ in items
}

HANDOVER_ITEM_LABELS = {
    item_id: label for _, items in HANDOVER_CHECKLIST for item_id, label in items
}

# ===== PROPOSAL =====

# Pricing guidance shown on the proposal form and printed on proposal
# documents. Pricing always depends on confirmed scope; nothing here assigns a
# price automatically.
PROPOSAL_PRICING_NOTE = (
    'Indicative RETEC ranges: Basic Website KSh 15,000-25,000; Standard / '
    'Business Website KSh 25,000-40,000; web applications and custom software '
    'are quoted based on scope. Final pricing depends on the confirmed scope '
    'of work stated in this proposal.'
)

# Wording pre-filled when a new proposal is created. Every value is editable
# per project -- these are defaults, not fixed terms.
PROPOSAL_DEFAULTS = {
    'revisions': (
        'Two rounds of revisions are included at each review stage. Further '
        'revision rounds, or changes to work already approved, are quoted '
        'separately before they are started.'
    ),
    'change_process': (
        'Change requests can be sent at any time, in writing (email is fine). '
        'RETEC will describe the effect on price and timeline before any '
        'change work begins. Small clarifications that stay inside the agreed '
        'scope are absorbed without a charge.'
    ),
    'support_notes': (
        'Bug-fix support for 30 days after handover is included. Ongoing '
        'maintenance, updates and new features are optional and quoted '
        'separately.'
    ),
    'validity_days': 14,
    'assumptions': (
        'The Client supplies content, images, credentials and approvals by '
        'the dates agreed.\n'
        'One decision-maker approves designs, content and final delivery.\n'
        'Pricing assumes the scope described in this proposal and no material '
        'change to it.\n'
        'Work starts once the deposit has been received.'
    ),
    'exclusions': (
        'Hosting, domain registration and renewal fees.\n'
        'Third-party licences, stock assets and service subscriptions.\n'
        'Content writing, photography and brand design unless listed as a '
        'deliverable.\n'
        'Ongoing maintenance beyond the support period stated below.\n'
        'Work not described in the scope of this proposal.'
    ),
    'acceptance_note': (
        'To accept this proposal, reply by email confirming that you would '
        'like to proceed and which scope and price you are accepting. RETEC '
        'will then send the client services agreement and deposit details. '
        'The proposal is valid for the period stated above.'
    ),
}

# Text printed under the investment section of a proposal document.
PROPOSAL_INVESTMENT_NOTE = PROPOSAL_PRICING_NOTE

"""Content for the public legal pages: /privacy, /terms, /security.

Kept out of app.py and out of the templates for the same reason journal.py is:
the wording is long, the structure is uniform, and none of it is Python logic.
app.py imports the three page descriptors and renders them; templates/_legal.html
owns the markup. Editing a clause never means touching a view or a route.

Block grammar (what a section's ``blocks`` list may contain)
------------------------------------------------------------
    ('p',    'text')              a paragraph. '**bold**' and '*italic*' are honoured.
    ('h3',   'text')              a sub-heading inside the section
    ('ul',   ['item', ...])       unordered list
    ('ol',   ['item', ...])       ordered list
    ('dl',   [('term', 'text')])  a definition list — used for field-by-field tables
    ('note', 'text')              a quiet aside. Placeholders and caveats live here.
    ('mail', 'label', 'key')      a visible contact block. `key` names a value from
                                  the route's `legal_emails` dict, so the address is
                                  configuration rather than copy.

Every factual claim below is drawn from the running application. Where a detail
is genuinely unknown to the code — a retention period, a jurisdiction, a
security mailbox — it is written as an explicit placeholder rather than invented.
"""

# Shown on all three pages. Bump when the wording changes; it is the only thing
# that tells a reader whether what they are reading is current.
LAST_UPDATED = '2 February 2026'

# Placeholder markers. Deliberately loud: a legal page that ships with these
# visible is telling the truth about itself. Clear them once real values exist.
TODO = '[TODO: ...]'


def _page(slug, eyebrow, title, lede, intro, sections):
    return {
        'slug': slug,
        'eyebrow': eyebrow,
        'title': title,
        'lede': lede,
        'intro': intro,
        'sections': sections,
    }


def _s(num, slug, title, blocks):
    """One numbered section. `slug` is the anchor id and the TOC target."""
    return {'num': num, 'slug': slug, 'title': title, 'blocks': blocks}


# =============================================================================
# PRIVACY POLICY
# =============================================================================

PRIVACY = _page(
    'privacy',
    'Legal / RETEC',
    'Privacy Policy',
    'How RETEC collects, uses, protects and manages information when you use our '
    'website and services.',
    [
        'This policy describes what this website does with information about you. '
        'It is written to be read. Where the law requires a specific phrase, we use '
        'one; everywhere else we try to say what actually happens.',

        'It applies to the public pages of this website and to information you send '
        'us through them. It does not describe how we handle confidential material '
        'you hand over inside a paid engagement — that is governed by the contract '
        'or statement of work for the project, which may set different rules.',
    ],
    [
        _s('01', 'overview', 'Overview', [
            ('p', 'RETEC is a small digital studio. We build websites, web '
                  'applications and custom software. This website exists to show '
                  'that work and to let people start a conversation with us.'),
            ('p', 'We are a studio, not a platform. There is no account to create, '
                  'nothing to download behind a paywall, and no marketplace. If you '
                  'only read this site, you do not give us an account, a password or '
                  'a profile.'),
            ('p', 'We do not sell personal information, and we do not share it for '
                  'advertising. There is no advertising network on this site.'),
        ]),

        _s('02', 'information-you-provide', 'Information You Provide', [
            ('p', 'You give us information in two ways: by submitting a form, or by '
                  'sending us an email or message. What each one collects is listed '
                  'below, because the difference matters.'),

            ('h3', 'Project inquiry form'),
            ('p', 'The "Start a Project" form asks for:'),
            ('dl', [
                ('Name', 'Your name. Required.'),
                ('Email address', 'So we can reply to you. Required.'),
                ('Business / Organization', 'Optional. Leave it blank if you are '
                                            'enquiring as an individual.'),
                ('Project type', 'Optional. Selected from a fixed list.'),
                ('Budget range', 'Optional. Selected from a fixed list.'),
                ('Project details', 'Your message. Required. Please do not include '
                                    'credentials, identity documents or anything else '
                                    'you would not want forwarded by email.'),
            ]),
            ('p', 'Your inquiry is emailed to the studio. The email record includes '
                  'your name, email address, the fields above and the network address '
                  'the request came from, so that replies can be traced if something '
                  'goes wrong.'),
            ('p', 'Your name and email address are also saved to our mailing list, so '
                  'we can contact you about the enquiry and send occasional studio '
                  'updates. You can ask us to remove that record at any time.'),

            ('h3', 'Become a Partner application form'),
            ('p', 'The partner application asks for your name, email address, '
                  'company or studio, your role or specialty, a link to your '
                  'portfolio, the kind of collaboration you are proposing, your areas '
                  'of expertise, and a longer message. All of it is stored, because an '
                  'application is something we need to be able to refer back to.'),
            ('p', 'This is the only form on the site where your submitted message is '
                  'held as a record in our database rather than existing mainly as an '
                  'email.'),

            ('h3', 'Newsletter signup'),
            ('p', 'The signup form asks for an email address and, optionally, a name. '
                  'The email address is checked against a verification service before '
                  'it is accepted, to reduce the number of bounced and abandoned '
                  'addresses we hold.'),
        ]),

        _s('03', 'collected-automatically', 'Information Collected Automatically', [
            ('p', 'The website keeps a small first-party record of visits. It exists '
                  'so we can tell which parts of the site are useful and which are '
                  'ignored. It is not an advertising profile and it is not linked to '
                  'an identity.'),

            ('h3', 'Page views'),
            ('dl', [
                ('Page', 'The path you requested.'),
                ('Network address', 'The IP address the request came from.'),
                ('Browser', 'The browser and operating system string your browser '
                            'sends with the request.'),
                ('Time', 'When the request arrived.'),
            ]),

            ('h3', 'Section interest'),
            ('p', 'When you scroll a section into view, or click a link that leaves '
                  'the site, we record which section you were in and that you did so. '
                  'Again: the section, the action, your IP address and the time.'),

            ('h3', 'Approximate location'),
            ('p', 'The IP address above is looked up against a public geolocation '
                  'database to derive a country and city. We store that derivation, '
                  'not the address that feeds it. It is coarse — typically city level — '
                  'and it exists so the studio can see roughly where its audience is.'),

            ('h3', 'Server logs'),
            ('p', 'Our host records standard request logs, as any web host must. '
                  'These are operational and are governed by the retention described '
                  'in section 09.'),
        ]),

        _s('04', 'how-we-use-information', 'How We Use Information', [
            ('ul', [
                'To reply to your enquiry, and to keep a record of what was agreed.',
                'To assess and respond to partner applications.',
                'To send the studio newsletter and, where you have asked for it, '
                'occasional updates about work and thinking.',
                'To understand which pages and sections are read, so the site can be '
                'improved.',
                'To keep the site running, secure and available.',
                'To meet legal obligations that apply to us.',
            ]),
            ('p', 'We do not use information from this website to build advertising '
                  'segments, and we do not sell or rent it.'),
            ('note', 'RETEC is a small studio and we do not have a separate data '
                     'protection officer. Privacy enquiries go to the same mailbox as '
                     'everything else.'),
        ]),

        _s('05', 'cookies', 'Cookies and Similar Technologies', [
            ('p', 'This site sets no advertising cookies, no analytics cookies from '
                  'third parties, and no cross-site trackers. There is no cookie '
                  'banner here because there is nothing to consent to.'),

            ('h3', 'The one cookie that exists'),
            ('p', 'Signing in to the private admin area sets a single session cookie. '
                  'It contains a signed identifier that lets the server recognise an '
                  'authenticated administrator. It carries no personal information, it '
                  'is not readable by other sites, and it is destroyed when the '
                  'browser closes. Visitors to the public site never receive it.'),

            ('h3', 'Local storage and similar'),
            ('p', 'We do not use local storage, IndexedDB or device fingerprinting to '
                  'identify returning visitors.'),
        ]),

        _s('06', 'analytics-and-third-parties', 'Analytics and Third-Party Services', [
            ('p', 'Analytics on this site are first-party: the numbers are recorded '
                  'by our own server from our own pages. No third-party analytics '
                  'script runs here.'),

            ('h3', 'Services that receive your information'),
            ('p', 'We use a small number of providers. Each one is listed with what '
                  'it actually receives:'),

            ('dl', [
                ('Transactional email provider',
                 'Brevo delivers the email this site sends — enquiry notifications, '
                 'application notifications and the newsletter. It receives the '
                 'recipient address and the message body of each send.'),
                ('Transactional SMS provider',
                 'The same provider can text the studio when a new enquiry arrives. '
                 'The message contains the contact details from your enquiry. This '
                 'is a notification to us, not to you.'),
                ('Email verification provider',
                 'ZeroBounce checks that a newsletter address is deliverable before '
                 'we store it. It receives the address being checked.'),
                ('IP geolocation provider',
                 'ip-api.com resolves an IP address to a country and city. It '
                 'receives the address, and returns only the country and city.'),
                ('Mailing list hosting',
                 'Newsletter contacts are held in the email provider\'s contact list '
                 'so that broadcasts can be sent.'),
            ]),

            ('h3', 'Assets loaded from other companies'),
            ('p', 'The page you are reading loads a small number of files from CDNs '
                  'rather than from our own server. As with any request to another '
                  'company, those CDNs see the request that reaches them, which '
                  'includes your IP address and browser string:'),
            ('ul', [
                'A font and icon stylesheet, from a public CDN.',
                'The animation libraries that drive the page, from a public CDN.',
                'One small portrait image in the navigation bar, hosted on an image '
                'hosting service rather than ours.',
                'A fallback background photograph, from a stock image service, used '
                'only if no background of our own is configured.',
            ]),
            ('p', 'Our own brand typeface is served from our own server, not from a '
                  'third party.'),
        ]),

        _s('07', 'sharing', 'How We Share Information', [
            ('p', 'We share information only where a service cannot work without it, '
                  'or where the law requires it:'),
            ('ul', [
                'With the email, SMS, verification and geolocation providers listed in '
                'section 06, to the extent needed to perform the service they perform '
                'for us.',
                'With our hosting and database providers, which store the site and its '
                'data.',
                'With professional advisers or authorities where we are legally '
                'required to do so.',
            ]),
            ('p', 'We do not sell personal information. We have never sold it and '
                  'this policy does not create a way to.'),
            ('p', 'None of these recipients are allowed to use your information for '
                  'their own purposes. That is a contractual obligation we place on '
                  'them, not a claim about how they are built.'),
        ]),

        _s('08', 'hosting', 'Hosting and Where Data Lives', [
            ('p', 'The application is served from a managed web host behind a CDN and '
                  'proxy, and its data is held in a managed PostgreSQL database. '
                  'Records about you therefore leave the browser and are processed on '
                  'infrastructure operated by other companies.'),
            ('p', 'Those providers act as processors on our instructions. They are not '
                  'independent controllers for your information, and they do not use '
                  'it to build their own profiles.'),
        ]),

        _s('09', 'retention', 'Data Retention', [
            ('p', 'We keep information only as long as it is doing a job.'),
            ('dl', [
                ('Enquiry and application records',
                 'Kept for as long as the conversation or collaboration lasts, and '
                 'then deleted. ' + TODO + ': state a specific period, for example '
                 '"24 months after the last exchange", and apply it to the stored '
                 'rows.'),
                ('Newsletter records',
                 'Kept until you unsubscribe, then marked inactive and retained '
                 'briefly before removal. ' + TODO + ': confirm the deletion interval.'),
                ('Analytics records',
                 'Page views, section interest and location records are kept '
                 'indefinitely at present. ' + TODO + ': decide on a rolling window '
                 '— 12 months is typical — and delete beyond it.'),
                ('Server logs',
                 'Set by our hosting provider. ' + TODO + ': confirm the provider\'s '
                 'retention window.'),
                ('Backups',
                 'Database backups are kept in rotating fashion by an operator-run '
                 'script. ' + TODO + ': confirm how long the host keeps a backup '
                 'before overwriting it.'),
            ]),
            ('p', 'When we delete a record, it stops being available in the '
                  'application. It may persist briefly inside a backup until that '
                  'backup is rotated out — an ordinary property of backup systems, '
                  'not a hidden second copy.'),
        ]),

        _s('10', 'security', 'Data Security', [
            ('p', 'RETEC is a small studio, so the honest framing is: we take this '
                  'seriously, we do a specific set of things well, and we do not '
                  'claim certifications we do not hold.'),
            ('ul', [
                'All pages and form submissions are served over HTTPS. Credentials '
                'and form data are encrypted in transit.',
                'The single administrator account stores a hashed password. The '
                'plaintext password is never written to the database.',
                'Administrative pages are protected by an authentication check '
                'performed on the server for every request. Hiding a link is not how '
                'that protection works.',
                'Public forms are rate limited, and each carries a hidden field that '
                'quietly rejects automated submissions.',
                'Forms are validated and constrained on the server. Submitted values '
                'are checked against an allowlist where they select from a list.',
                'Content published to the Journal is filtered to a fixed set of '
                'permitted tags and attributes before it is stored.',
                'Sensitive configuration — database credentials, API keys, the '
                'session key — is held in environment variables on the server and is '
                'never committed to source control.',
                'Uploads are restricted to an allowlist of image and video file '
                'extensions, given a generated filename, and size-capped.',
                'The database is written to through an application account, and the '
                'application refuses to run destructive operations against a remote '
                'database unless explicitly unlocked.',
                'Dynamic pages are served with caching disabled, so a page about you '
                'is not held in a shared cache.',
            ]),
            ('p', 'The full picture, including the practices behind these controls, '
                  'is set out on our Security page.'),
            ('p', 'No system is perfectly secure. If a breach affecting your '
                  'information occurs, we will investigate, and we will tell you '
                  'what we find and what we have done about it.'),
        ]),

        _s('11', 'your-rights', 'Your Rights and Choices', [
            ('p', 'Depending on where you live, you may have rights over personal '
                  'information relating to you — to ask what we hold, to correct it, '
                  'to have it deleted, to object to certain processing, or to '
                  'complain to a regulator.'),
            ('p', 'In practice, for this website, the whole list reduces to four '
                  'emails:'),
            ('ul', [
                'Ask what information we hold about you, and get a copy.',
                'Ask us to correct something that is wrong.',
                'Ask us to delete your enquiry, application or newsletter record.',
                'Ask us to stop emailing you. Every newsletter carries an unsubscribe '
                'link, and it works immediately.',
            ]),
            ('p', 'We will act on a request from the address we hold for you, so that '
                  'we can be sure we are not deleting a stranger\'s data on request. '
                  'We will tell you if we cannot act on something, and why.'),
            ('p', 'If you are in the EEA or the UK you also have the right to '
                  'complain to your data protection authority. Elsewhere, your local '
                  'regulator is the equivalent route.'),
        ]),

        _s('12', 'children', "Children's Privacy", [
            ('p', 'This website is a portfolio and a contact point for a business. It '
                  'is not directed at children, and we do not knowingly collect '
                  'personal information from anyone under 16.'),
            ('p', 'If you believe a child has submitted information through one of our '
                  'forms, tell us and we will delete it.'),
        ]),

        _s('13', 'international-transfers', 'International Data Transfers', [
            ('p', 'RETEC operates from Kenya. The hosting, database and email '
                  'providers listed above are not all located in Kenya, so '
                  'information you submit is processed on servers and systems in '
                  'other countries.'),
            ('p', 'Those transfers happen under the safeguards those providers '
                  'publish for the arrangements they operate. We do not separately '
                  'negotiate bespoke transfer terms for a studio of this size.'),
        ]),

        _s('14', 'changes', 'Changes to This Policy', [
            ('p', 'This policy changes when the website changes. The date at the top '
                  'of this page is the real signal — it is updated whenever the text '
                  'is.'),
            ('p', 'If a change materially affects what we do with information you '
                  'have already given us, we will tell you by email before it takes '
                  'effect.'),
            ('note', TODO + ': the section above describes the intended behaviour. '
                     'Wire it to a real notification if and when that process exists.'),
        ]),

        _s('15', 'contact', 'Contact', [
            ('p', 'Privacy questions, access requests and deletion requests all go '
                  'to one address. Read it first, because it is where we can actually '
                  'check who you are against what we hold.'),
            ('mail', 'Privacy enquiries', 'contact_email'),
            ('p', 'There is also a contact form on the homepage. Use the address for '
                  'anything about your data — a form message is easier to lose than '
                  'an email thread.'),
        ]),
    ],
)


# =============================================================================
# TERMS OF USE
# =============================================================================

TERMS = _page(
    'terms',
    'Legal / RETEC',
    'Terms of Use',
    'The rules for using this website. They are deliberately few, and they are '
    'also clearly not the rules for a project.',
    [
        "These terms cover browsing RETEC's public website. They are written to be "
        'short and plain.',

        'They are worth reading precisely because they are narrow. Nothing here '
        'describes how a client engagement works — that is set out in the proposal, '
        'statement of work or contract for the individual project, and those '
        'documents win where the two disagree.',
    ],
    [
        _s('01', 'introduction', 'Introduction', [
            ('p', 'RETEC builds websites, web applications and custom software. This '
                  'website describes that work and lets you start a conversation '
                  'about more of it.'),
            ('p', 'By using this website you accept these terms. If you do not accept '
                  'them, the practical remedy is to close the tab — nothing here '
                  'obliges you to do anything.'),
            ('p', 'These terms are written for RETEC\'s site as it is today. It is a '
                  'portfolio and an enquiry point, not a service that people sign up '
                  'for.'),
        ]),

        _s('02', 'using-the-website', 'Using the Website', [
            ('h3', 'What you may do'),
            ('ul', [
                'Read the site.',
                'Submit the enquiry, partner and newsletter forms.',
                'Quote and link to the site, including the written content and '
                'case-study material, with attribution.',
            ]),

            ('h3', 'What you may not do'),
            ('ul', [
                'Attempt to gain unauthorised access to the site, the admin area or '
                'anything behind them.',
                'Probe, scan, load-test or otherwise interfere with the site\'s '
                'operation.',
                'Scrape the site at a rate that degrades it for other visitors, or '
                'republish large portions of it as your own.',
                'Use the forms to send unsolicited bulk commercial messages.',
            ]),
            ('p', 'The forms are rate limited. Repeated automated submissions are '
                  'rejected automatically, which is a security measure rather than a '
                  'judgement about you.'),
        ]),

        _s('03', 'no-client-relationship', 'No Client Relationship', [
            ('p', 'Reading this website, sending an enquiry, or applying to '
                  'collaborate does not create a client relationship, an agency '
                  'relationship, a partnership, or any other kind of legal '
                  'relationship with RETEC.'),
            ('p', 'A client relationship begins only when RETEC and the other party '
                  'have both signed a written agreement. Until then, neither side is '
                  'bound to work together, and nothing on this website should be read '
                  'as an offer capable of acceptance.'),
            ('p', 'The same applies in reverse: content on this website is general '
                  'information, not advice. Do not build decisions on it without '
                  'talking to us.'),
        ]),

        _s('04', 'our-services', 'Our Services', [
            ('p', 'RETEC offers design, web development, custom software, API '
                  'development and related digital consulting. Those services are '
                  'delivered under individual agreements.'),
            ('p', 'This website is not a catalogue of products with prices and '
                  'checkout. Nothing on it can be purchased.'),
            ('p', 'Where a service description on this site and an agreement differ, '
                  'the agreement is the accurate one.'),
        ]),

        _s('05', 'project-engagements', 'Project Engagements', [
            ('p', 'Every project is different, so there is no single set of project '
                  'terms here. What applies to a given project is set out in the '
                  'proposal, statement of work or contract signed for it.'),
            ('p', 'Those documents typically cover scope, deliverables, schedule, '
                  'fees, payment, revision limits, ownership and confidentiality.'),
            ('note', TODO + ': if RETEC wants a consistent baseline across projects, '
                     'that baseline belongs in a standard terms document referenced '
                     'here — not written into page copy.'),
            ('p', 'Where this website and a signed agreement conflict on anything '
                  'material, the signed agreement governs.'),
        ]),

        _s('06', 'client-responsibilities', 'Client Responsibilities', [
            ('p', 'Client obligations are agreed per project rather than stated here. '
                  'In practice they are the obvious ones: providing the content, '
                  'access, approvals and decisions the work needs, by the dates '
                  'agreed.'),
            ('p', 'Schedules move when inputs arrive late. That is not a penalty, '
                  'just arithmetic, and it is why delivery dates in project documents '
                  'are stated as dependencies rather than promises.'),
        ]),

        _s('07', 'intellectual-property', 'Intellectual Property', [
            ('p', 'RETEC owns this website and everything published on it: the copy, '
                  'the design, the layout, the typography, the code and the visual '
                  'identity. The MADE Mirage typeface is used under the terms of its '
                  'own licence.'),
            ('p', 'You may read it, link to it and quote it with attribution. You may '
                  'not republish it as your own, remove attribution from it, or use '
                  'RETEC\'s name, marks or identity in a way that suggests we are '
                  'endorsing something.'),
            ('p', 'Ownership of work delivered to a client is a project matter and is '
                  'set out in that project\'s agreement. Nothing on this website '
                  'changes the default in any agreement.'),
        ]),

        _s('08', 'client-content', 'Client Content', [
            ('p', 'If you send us your own material — a brief, images, documents, '
                  'repositories — you keep your rights in it, and you grant us only '
                  'the permission needed to use it to respond to you and to deliver '
                  'the work.'),
            ('p', 'That permission is limited to the purpose you sent it for. It does '
                  'not become a licence to reuse your material elsewhere, to show it '
                  'off, or to include it in our portfolio without asking.'),
            ('p', 'Where we display client work on this site, that is a separate '
                  'agreement, and clients who do not want their work shown are not '
                  'shown.'),
        ]),

        _s('09', 'third-party-services', 'Third-Party Services', [
            ('p', 'The site depends on infrastructure and services run by other '
                  'companies: web hosting, a database provider, a CDN, an email '
                  'delivery provider, and the CDNs that serve fonts, icons and the '
                  'animation libraries.'),
            ('p', 'Those services are provided under their own terms, and we do not '
                  'control them. Their availability, security and behaviour are their '
                  'responsibility, not ours.'),
            ('p', 'Links to other sites are provided for reference. RETEC does not '
                  'endorse them and is not responsible for what is on them.'),
        ]),

        _s('10', 'payments-and-fees', 'Payments and Fees', [
            ('p', 'There are no prices on this website and no way to pay through it. '
                  'This site does not process payments, store card details, or '
                  'handle any financial transaction.'),
            ('p', 'Fees, invoicing, schedules and any late-payment terms are agreed '
                  'in writing per project. Nothing here creates an invoice, a quote '
                  'or a price.'),
            ('note', TODO + ': insert the studio\'s actual invoicing and payment '
                     'terms here once they are settled. Do not paraphrase them from '
                     'memory — copy them from the agreement template.'),
        ]),

        _s('11', 'changes-and-revisions', 'Changes and Revisions', [
            ('p', 'Digital work is iterative, and the number of revision rounds '
                  'included in a project is set out in that project\'s agreement.'),
            ('p', 'Work outside the agreed scope — a new feature, a change of '
                  'direction after sign-off — is a change request, and is quoted and '
                  'approved separately before it is started.'),
            ('p', 'These terms do not set a revision allowance, because that number '
                  'means nothing without the scope it applies to.'),
        ]),

        _s('12', 'no-warranties', 'No Warranties', [
            ('p', 'This website and everything on it are provided as they are. To the '
                  'fullest extent the law allows, RETEC disclaims all warranties, '
                  'express or implied, including merchantability, fitness for a '
                  'particular purpose and non-infringement.'),
            ('p', 'Case studies, results and client outcomes described here describe '
                  'particular projects under particular conditions. They are not '
                  'predictions, and they are not a promise that similar results will '
                  'follow from similar work.'),
            ('p', 'Content is provided for general information. It is not legal, '
                  'financial, security or compliance advice, and it should not be '
                  'relied on as such.'),
        ]),

        _s('13', 'liability', 'Limitation of Liability', [
            ('p', 'To the fullest extent permitted by law, RETEC is not liable for '
                  'any indirect, incidental, special or consequential loss, or for '
                  'loss of profits, revenue, data or goodwill, arising from use of '
                  'this website.'),
            ('p', 'Nothing here excludes or limits liability that cannot lawfully be '
                  'excluded — for instance for fraud, or for anything a statute says '
                  'cannot be contracted out of.'),
            ('p', 'These terms apply to your use of this website only. They do not '
                  'limit liability under any signed client agreement, which is '
                  'governed on its own terms.'),
            ('note', TODO + ': this is a general website-terms statement. It is not '
                     'reviewed for any specific governing law, and the enforceability '
                     'of any limitation depends on where the claim is brought. Have '
                     'a lawyer confirm the wording against the studio\'s jurisdiction '
                     'before relying on it in a dispute.'),
        ]),

        _s('14', 'availability', 'Website Availability', [
            ('p', 'We publish and maintain this site in good faith, but we do not '
                  'promise that it will always be available, always be complete, or '
                  'always be free of errors.'),
            ('p', 'There is no uptime guarantee on this site, and no service level '
                  'attached to it. The same goes for third-party services the site '
                  'depends on — see section 09.'),
            ('p', 'We may change, suspend or withdraw any part of the site at any '
                  'time, with or without notice.'),
        ]),

        _s('15', 'termination', 'Termination', [
            ('p', 'You may stop using this website whenever you like. There is no '
                  'account to close.'),
            ('p', 'We may block access, temporarily or permanently, where a request '
                  'appears automated, where it is interfering with the site, or where '
                  'it is unlawful.'),
            ('p', 'Blocking access does not create a refund, a credit or any other '
                  'obligation — nothing on this site is paid for.'),
            ('p', 'Termination of a client engagement is governed by that '
                  'engagement\'s agreement, not by this page.'),
        ]),

        _s('16', 'governing-law', 'Governing Law', [
            ('p', 'These terms are governed by the laws of Kenya, which is where '
                  'RETEC operates. The courts of Kenya have jurisdiction over any '
                  'dispute arising from them.'),
            ('note', TODO + ': confirm the jurisdiction and whether RETEC trades '
                     'through a registered entity elsewhere. If it does, the law '
                     'that governs consumer-facing terms may need to change.'),
            ('p', 'If any provision of these terms is found unenforceable, the rest '
                  'of them continue to apply.'),
        ]),

        _s('17', 'changes', 'Changes to These Terms', [
            ('p', 'We may update these terms. The date at the top of the page shows '
                  'when they last changed, and that date is authoritative.'),
            ('p', 'Continuing to use the website after a change means accepting it. '
                  'Because nothing on this site is a paid service or a commitment, '
                  'we do not run a consent flow for legal-page updates.'),
        ]),

        _s('18', 'contact', 'Contact', [
            ('p', 'Questions about these terms go to the studio by email, or through '
                  'the enquiry form on the homepage.'),
            ('mail', 'Terms enquiries', 'contact_email'),
        ]),
    ],
)


# =============================================================================
# SECURITY
# =============================================================================

SECURITY = _page(
    'security',
    'Legal / RETEC',
    'Security',
    'What is actually implemented on this site, and what is not. Written for '
    'readers who would rather have the short honest list than the long impressive '
    'one.',
    [
        'RETEC is a small studio. This page describes the security of our website and '
        'the applications we build — honestly, and without the vocabulary of a '
        'compliance programme we do not run.',

        'The rule we have applied while writing it: if a control exists in the code '
        'or the infrastructure, it is described. If it does not, it is not mentioned. '
        'Where a practice depends on configuration, it says so.',
    ],
    [
        _s('01', 'security-at-retec', 'Security at RETEC', [
            ('p', 'There is no dedicated security team, because there is no security '
                  'team to have. Security here is the responsibility of the person who '
                  'builds and runs the systems, alongside the rest of the work.'),
            ('p', 'That shape has an obvious consequence worth stating plainly: there '
                  'is no 24/7 operations centre watching anything. Systems are '
                  'monitored in the ordinary way — by the infrastructure they run on '
                  'and by application logging — not by a team on a rota.'),
            ('p', 'RETEC holds no formal security certification. We do not hold SOC 2, '
                  'ISO 27001 or PCI DSS, we have not commissioned a penetration test, '
                  'and we do not describe anything here as certified, audited or '
                  'compliant with a framework. If you need a vendor with those, this '
                  'is not that.'),
            ('p', 'What we do have is a small set of controls we actually keep, and '
                  'this page describes them accurately.'),
        ]),

        _s('02', 'application-security', 'Application Security', [
            ('h3', 'Transport'),
            ('p', 'The site is served over HTTPS, and form submissions are encrypted '
                  'in transit. The application is deployed behind a proxy and is '
                  'configured to trust exactly one proxy hop for the forwarded '
                  'protocol and client address, so a client cannot spoof either by '
                  'sending the relevant headers directly.'),

            ('h3', 'Authentication'),
            ('p', 'Administrative access is restricted to a single account. The '
                  'password is stored as a bcrypt hash; the plaintext password is '
                  'never written to the database, and cannot be recovered from it. '
                  'Login attempts are rate limited per source address, with a tighter '
                  'allowance than general site traffic.'),

            ('h3', 'Session handling'),
            ('p', 'Authentication state is held in a signed, server-validated session '
                  'cookie. It is not a bearer token containing readable claims, and '
                  'the signing key is a secret held in environment configuration.'),

            ('h3', 'Authorization'),
            ('p', 'Every administrative route is guarded by an authentication check '
                  'performed on the server for each individual request. Hiding a link '
                  'in the interface is not part of that, and removing the guard from '
                  'one route is not a supported configuration.'),

            ('h3', 'Request forgery'),
            ('p', 'Form submissions that carry visitor input are protected with '
                  'cross-site request forgery tokens. A small number of endpoints are '
                  'deliberately exempt — the newsletter signup, the analytics '
                  'receivers and the admin image upload — because they are either '
                  'unauthenticated by design or unreachable without an authenticated '
                  'session.'),
        ]),

        _s('03', 'input-validation', 'Input Validation', [
            ('p', 'All public input is validated on the server, never only in the '
                  'browser. Validation is allowlist-based wherever a value comes from '
                  'a fixed set of choices, so an unexpected value is rejected rather '
                  'than coerced.'),
            ('ul', [
                'Fields are length-bounded, so an oversized submission cannot be '
                'stored or forwarded.',
                'Email addresses are format-checked, and newsletter addresses are '
                'additionally verified against a deliverability service before they '
                'are stored.',
                'URL fields accept only http and https, reject non-web schemes such as '
                'javascript: and data:, reject embedded credentials, and reject hosts '
                'containing a wildcard, port or path.',
                'Uploads are restricted to an allowlist of image and video extensions, '
                'renamed to a generated filename, and capped at 16 MB per request.',
                'Request bodies are size-capped at the web server and application '
                'layer.',
            ]),
            ('p', 'Content published to the Journal is parsed and re-emitted from a '
                  'fixed allowlist of tags and attributes, and broken or unbalanced '
                  'markup is discarded. Published content is not a free path for '
                  'script injection.'),
        ]),

        _s('04', 'infrastructure', 'Infrastructure and Hosting', [
            ('p', 'The application runs on a managed web host behind a CDN, with a '
                  'managed PostgreSQL database. The CDN terminates client connections '
                  'and the host runs the application under a WSGI server.'),
            ('ul', [
                'A web application firewall sits in front of the application and '
                'filters the common classes of malicious request before they reach '
                'the code.',
                'TLS is used for all connections, including to the database. The '
                'application refuses to connect to a remote database without TLS '
                'enabled.',
                'Responses are served with caching disabled so that personalised or '
                'administrative pages are never stored in a shared cache.',
                'Static assets are public and cache-busted by a version query string.',
            ]),
            ('note', 'Hosting headers such as HSTS and the CDN\'s own protections are '
                     'configured at the provider rather than in the application '
                     'source, so they can change without a code change. This page '
                     'describes them as configured, not as guaranteed.'),
        ]),

        _s('05', 'data-protection', 'Data Protection', [
            ('ul', [
                'Passwords are bcrypt-hashed and never stored or logged in plaintext.',
                'Database credentials, third-party API keys and the session signing key '
                'are held in environment variables on the server. None of them are '
                'committed to source control; the files that hold them are excluded '
                'from the repository.',
                'Uploaded filenames are generated rather than taken from the client.',
                'Administrative and diagnostic output goes to server logs rather than '
                'into responses.',
                'SMTP and third-party API traffic is made over TLS.',
            ]),
            ('p', 'Where practical, secrets have been removed from source control '
                  'entirely. Where a credential was ever committed, it should be '
                  'treated as compromised and rotated rather than relied upon — '
                  'rotation is a matter of record-keeping, not of code.'),
        ]),

        _s('06', 'access-control', 'Access Control', [
            ('p', 'The administrative area is a single-account model. That is the '
                  'whole design, and it has an obvious property: there is exactly one '
                  'identity to grant, revoke and audit.'),
            ('ul', [
                'Access is granted by possession of the credentials, and the account '
                'is not shared. If someone else needs access, they need their own.',
                'A password change requires proving the current password first, and '
                'the confirmation step expires after a short window.',
                'There is no separate read-only, editor or viewer role, and no '
                'per-object permission model.',
            ]),
            ('p', 'The principle applied throughout is least privilege: the application '
                  'holds the database credentials it needs and no more, and a '
                  'compromise of the web tier does not by itself grant access to '
                  'anything beyond it.'),
            ('note', 'Two independent safeguards guard destructive database '
                     'operations. The application refuses to boot against a remote '
                     'database unless explicitly allowed, and refuses to drop tables '
                     'unless two separate confirming environment variables are both '
                     'set. A single leaked environment variable is therefore not '
                     'sufficient to destroy the database.'),
        ]),

        _s('07', 'backups', 'Backups', [
            ('p', 'The database is backed up by an operator-run script that produces '
                  'a timestamped, compressed SQL dump and stores it outside the '
                  'database provider. Older dumps are pruned on a rolling basis.'),
            ('p', 'This exists because a managed database plan without a point-in-time '
                  'restore is not a backup strategy. It has already been learned the '
                  'expensive way.'),
            ('ul', [
                'The dump script is read-only: it never writes to the database it is '
                'backing up.',
                'Backups are stored outside the database provider, so a provider-side '
                'failure does not take them with it.',
                'There are tools to list, verify and restore a dump.',
            ]),
            ('note', TODO + ': confirm how often the backup job actually runs. The '
                     'script exists and is tested; a backup that nobody schedules is '
                     'not a backup, and this page should not imply otherwise.'),
        ]),

        _s('08', 'logging-and-monitoring', 'Logging and Monitoring', [
            ('p', 'There is no dedicated monitoring service and no alerting pipeline '
                  'of our own. What exists is standard:'),
            ('ul', [
                'Application logging records failures — email delivery errors, '
                'third-party API errors, upload failures, scheduler errors — with '
                'enough context to diagnose them.',
                'The hosting platform logs requests and serves the site.',
                'First-party analytics record page views, section interest and coarse '
                'location, which is how unusual traffic would first become visible.',
            ]),
            ('p', 'None of this constitutes 24/7 monitoring, and nobody is paged. If '
                  'you are assessing RETEC for a role that requires a documented '
                  'incident response capability with guaranteed response times, this '
                  'is not a match.'),
        ]),

        _s('09', 'third-party-services', 'Third-Party Services', [
            ('p', 'RETEC depends on other companies. Each one is a place where our '
                  'security is somebody else\'s security, so they are named here '
                  'rather than left implicit.'),
            ('dl', [
                ('Managed web host and CDN',
                 'Runs and fronts the application. Secures client connections.'),
                ('Managed PostgreSQL provider',
                 'Stores the application data, including the personal information '
                 'described in the Privacy Policy.'),
                ('Transactional email and SMS provider',
                 'Holds a contact list and delivers messages. It has seen every '
                 'inquiry email address and message body.'),
                ('Email deliverability provider',
                 'Receives addresses submitted for verification.'),
                ('IP geolocation provider',
                 'Receives IP addresses and returns a country and city. Note that this '
                 'lookup is made over plain HTTP; the response is not confidential '
                 'information, but the request is visible in transit.'),
                ('Public CDNs',
                 'Serve fonts, icons and animation libraries. They see the requests '
                 'that reach them, which include IP address and browser string.'),
                ('Cloudinary (optional)',
                 'Stores uploaded media when configured. With no configuration the '
                 'application stores uploads locally instead.'),
                ('AI language-model API (optional)',
                 'Used to draft summaries of public news articles for the Journal. It '
                 'operates on retrieved public content and does not receive visitor '
                 'personal data.'),
            ]),
            ('p', 'Each of these has its own security posture and its own terms. We '
                  'rely on their controls; we do not audit them, and we have not '
                  'verified their compliance status on your behalf.'),
        ]),

        _s('10', 'secure-development', 'Secure Development', [
            ('ul', [
                'Dependencies are pinned to specific versions, so a build is '
                'reproducible and an upgrade is a deliberate act rather than an '
                'accident.',
                'Framework, driver and library versions are kept current, and '
                'security-relevant updates are applied deliberately.',
                'Secrets are configured through the environment, which keeps them out '
                'of the source tree and out of the templates.',
                'Templates escape output by default; raw HTML is only used where '
                'content has been through the sanitiser.',
                'Destructive database operations are guarded by a module that requires '
                'two independent confirmations, so a development convenience cannot '
                'reach production data.',
                'Form handling is rate limited, and forms carry a hidden field that '
                'rejects automated submissions before any mail is sent.',
                'New routes that read or write protected data are expected to carry '
                'the authentication decorator; this is checked in review.',
            ]),
            ('p', 'RETEC is a small team, so the honest statement about process is '
                  'this: these practices are followed deliberately, and they are not '
                  'audited by anyone outside the studio.'),
        ]),

        _s('11', 'incident-response', 'Incident Response', [
            ('p', 'There is no formal, documented incident response plan with defined '
                  'severity levels and response times. What happens in practice is '
                  'that the person who built the system is the person who responds '
                  'to it.'),
            ('p', 'The order of operations, when something is wrong:'),
            ('ol', [
                'Establish what actually happened and what is affected. Log records '
                'and application errors are the starting point.',
                'Contain it — revoke credentials, remove access, disable the affected '
                'route — before investigating further.',
                'Rotate anything that may have been exposed: application keys, '
                'database credentials, third-party API keys, the session key. Rotation '
                'is assumed, never assumed to be unnecessary.',
                'Assess who was affected and what of theirs was involved.',
                'Tell those affected, plainly and without overstating confidence, and '
                'say what was done.',
            ]),
            ('p', 'If you are assessing us as a vendor, this section is the one to '
                  'weigh most carefully. It is small, and it is written to be '
                  'readable by a person rather than to satisfy a checklist.'),
        ]),

        _s('12', 'responsible-disclosure', 'Responsible Disclosure', [
            ('p', 'If you find a vulnerability in this website or in something we have '
                  'built, we would rather hear about it quietly than read about it '
                  'publicly.'),
            ('p', 'Please report it privately, and please give us a reasonable '
                  'opportunity to assess and fix it before disclosing details.'),

            ('h3', 'What to include'),
            ('ul', [
                'What the issue is, and how to reproduce it.',
                'Which page, endpoint or project it affects.',
                'What an attacker could do with it.',
                'Any proof-of-concept you are willing to share privately.',
                'How to reach you, and how long you are willing to wait.',
            ]),

            ('h3', 'What to expect'),
            ('ul', [
                'An acknowledgement that the report arrived.',
                'An honest assessment — including being told that something is not '
                'in fact a vulnerability, or that we are not going to fix it.',
                'No public attribution unless you ask for it.',
            ]),
            ('p', 'There is no bug bounty programme and no financial reward attached '
                  'to a report. We are a small studio and cannot offer one honestly. '
                  'The incentive here is the same as it would be anywhere else: a '
                  'working system.'),
            ('p', 'Please do not access data that is not yours, do not degrade the '
                  'service for others, and do not use automated scanning. We will not '
                  'pursue action against good-faith research that stays inside these '
                  'lines, but we will not tolerate destructive testing.'),
        ]),

        _s('13', 'contact', 'Contact', [
            ('p', 'Security reports and privacy enquiries go to the same mailbox as '
                  'all other correspondence. That address is configured, so a report '
                  'reaches a person rather than an unattended form.'),
            ('mail', 'Security disclosures', 'security_email'),
            ('note', TODO + ': set SECURITY_CONTACT_EMAIL if reports should be routed '
                     'to a dedicated mailbox. Until it is set, they arrive in the '
                     'studio inbox alongside project enquiries, which is honest but '
                     'not ideal.'),
            ('p', 'If a report turns out to be urgent — active exploitation, '
                  'exposed credentials — say so in the subject line so it is not '
                  'buried among enquiries.'),
        ]),
    ],
)


PAGES = {
    'privacy': PRIVACY,
    'terms': TERMS,
    'security': SECURITY,
}

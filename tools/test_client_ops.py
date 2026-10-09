"""Tests for the client operations feature (discovery -> handover).

Run against an isolated database only — never the configured production one:

    DATABASE_URL="sqlite:////tmp/opencode/retec-clientops.db" .venv/bin/python tools/test_client_ops.py

or with the same DATABASE_URL under a unittest/pytest runner.

The guard below refuses to import app.py unless DATABASE_URL is already a
sqlite URL, because importing app connects to whatever .env points at and
these tests write rows.
"""

import json
import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

os.environ.setdefault('SECRET_KEY', 'test-secret-key-not-for-production')

if not os.environ.get('DATABASE_URL', '').startswith('sqlite:'):
    raise SystemExit(
        'Set DATABASE_URL to a sqlite file first, e.g.\n'
        '  DATABASE_URL="sqlite:////tmp/opencode/retec-clientops.db" '
        '.venv/bin/python tools/test_client_ops.py'
    )

import app as retec  # noqa: E402
from app import (  # noqa: E402
    app, db, Client, ClientQuestionnaire, ClientProposal, ClientAgreement,
    ClientPayment, ClientNote, ClientHandover, Enquiry,
    build_client_from_questionnaire, clean_client_status, clean_date_value,
    clean_money, schedule_rows_from_form, agreement_placeholder_values,
)

application = app

# The context processor hits the GitHub API on every page render; a test suite
# that shells out to the network is slow and flaky, so the calls are stubbed.
retec.get_github_stats = lambda *args, **kwargs: None
retec.get_github_projects = lambda *args, **kwargs: []

# Emails are fail-soft in production, but tests must not send anything even if
# a real Brevo key happens to be present in the environment.
retec.send_questionnaire_notification = lambda *args, **kwargs: True
retec.send_questionnaire_confirmation = lambda *args, **kwargs: True


def questionnaire_payload(**extra):
    """A minimal valid submission: the four required answers."""
    data = {
        'full_name': 'Ada Lovelace',
        'email': 'ada@example.com',
        'looking_to_build': 'A booking system for my clinic.',
        'project_success': 'Patients can book online without calling.',
    }
    data.update(extra)
    return data


class HelperTests(unittest.TestCase):
    """Pure functions and document builders."""

    def test_client_status_whitelist(self):
        self.assertEqual(clean_client_status(' signed '), 'signed')
        self.assertIsNone(clean_client_status('made-up-stage'))
        self.assertIsNone(clean_client_status(None))
        self.assertIsNone(clean_client_status(''))

    def test_clean_money_parsing(self):
        self.assertEqual(clean_money('15,000'), 15000.0)
        self.assertEqual(clean_money('KSh 25000.50'), 25000.5)
        self.assertIsNone(clean_money('abc'))
        self.assertIsNone(clean_money('-5'))
        self.assertIsNone(clean_money(''))

    def test_clean_date_value_parsing(self):
        from datetime import date
        self.assertEqual(clean_date_value('2026-03-04'), date(2026, 3, 4))
        self.assertIsNone(clean_date_value('not a date'))
        self.assertIsNone(clean_date_value(''))

    def test_schedule_rows_require_label_and_amount(self):
        rows = schedule_rows_from_form({
            'sched_label_1': 'Deposit', 'sched_amount_1': '10,000',
            'sched_timing_1': 'on signing',
            'sched_label_2': 'No amount', 'sched_amount_2': '',
            'sched_label_3': '', 'sched_amount_3': '5000',
            'sched_label_4': 'Final', 'sched_amount_4': '15000',
        })
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]['label'], 'Deposit')
        self.assertEqual(rows[0]['amount'], 10000.0)
        self.assertEqual(rows[1]['label'], 'Final')

    def test_agreement_clauses_flag_missing_placeholders(self):
        clauses, missing = retec.client_documents.render_agreement_clauses({})
        self.assertGreaterEqual(len(clauses), 30)
        self.assertIn('CLIENT NAME', missing)
        self.assertIn('PROJECT FEE', missing)
        # A known value disappears from the missing set for that clause.
        clauses, missing = retec.client_documents.render_agreement_clauses(
            {'CLIENT NAME': 'Acme Ltd'})
        self.assertNotIn('CLIENT NAME', missing)

    def test_fill_placeholders_keeps_unknown_tokens_visible(self):
        text, missing = retec.client_documents.fill_placeholders(
            'Between [CLIENT NAME] and [MYSTERY].', {})
        self.assertEqual(text, 'Between [CLIENT NAME] and [MYSTERY].')
        self.assertEqual(missing, ['CLIENT NAME', 'MYSTERY'])

    def test_build_client_from_questionnaire_maps_record_fields(self):
        with application.app_context():
            client = build_client_from_questionnaire({
                'full_name': '  Ada Lovelace ',
                'business_name': 'Clinic Co',
                'email': 'ADA@Example.com',
                'phone': '0712 345 678',
                'looking_to_build': 'A booking system',
                'problem_solving': 'Phone bookings waste time',
                'budget_range': '25000_40000',
                'contact_method': 'whatsapp',
            })
        self.assertEqual(client.name, 'Ada Lovelace')
        self.assertEqual(client.email, 'ada@example.com')
        self.assertEqual(client.status, 'discovery')
        self.assertEqual(client.source, 'questionnaire')
        self.assertEqual(client.budget_range, '25000_40000')
        self.assertEqual(client.contact_method, 'whatsapp')
        self.assertEqual(client.project_title, 'A booking system')

    def test_build_client_rejects_unknown_budget_and_contact(self):
        with application.app_context():
            client = build_client_from_questionnaire({
                'full_name': 'X', 'email': 'x@example.com',
                'budget_range': 'unlimited', 'contact_method': 'pigeon',
            })
        self.assertEqual(client.budget_range, '')
        self.assertEqual(client.contact_method, '')

    def test_agreement_values_prefer_explicit_payment_terms(self):
        with application.app_context():
            client = Client(name='Ada', email='ada@example.com',
                            project_title='Booking system', fee=25000)
            agreement = ClientAgreement(client=client,
                                        payment_terms='50% up front.')
            values = agreement_placeholder_values(agreement)
            self.assertEqual(values['PAYMENT TERMS'], '50% up front.')
            agreement.payment_terms = ''
            values = agreement_placeholder_values(agreement)
            # No payments and no proposal schedule -> derived terms stay empty.
            self.assertIsNone(values['PAYMENT TERMS'])


class ModelTests(unittest.TestCase):
    """Property behaviour on the new models."""

    def setUp(self):
        application.config.update(TESTING=True, WTF_CSRF_ENABLED=False,
                                  RATELIMIT_ENABLED=False)
        self.ctx = application.app_context()
        self.ctx.push()

    def tearDown(self):
        retec.db.session.rollback()
        retec.db.session.remove()
        self.ctx.pop()

    def _client(self, **kwargs):
        kwargs.setdefault('name', 'Model Test')
        client = Client(**kwargs)
        retec.db.session.add(client)
        retec.db.session.flush()
        return client

    def test_fee_paid_only_counts_fee_kinds_marked_paid(self):
        client = self._client(fee=20000)
        retec.db.session.add_all([
            ClientPayment(client=client, label='Deposit', kind='deposit',
                          amount=5000, status='paid'),
            ClientPayment(client=client, label='Milestone', kind='milestone',
                          amount=10000, status='pending'),
            ClientPayment(client=client, label='Domain', kind='hosting',
                          amount=1000, status='paid'),
            ClientPayment(client=client, label='Waived bit', kind='deposit',
                          amount=500, status='waived'),
        ])
        retec.db.session.flush()
        self.assertEqual(client.fee_paid, 5000)
        self.assertEqual(client.fee_outstanding, 15000)
        self.assertEqual(client.other_costs_paid, 1000)
        self.assertEqual(client.pending_amount, 10000)

    def test_fee_outstanding_is_none_without_a_fee(self):
        client = self._client()
        self.assertIsNone(client.fee_outstanding)
        self.assertEqual(client.fee_paid, 0)

    def test_proposal_missing_fields_and_validity(self):
        from datetime import datetime, timedelta
        proposal = ClientProposal(client=Client(name='X'))
        retec.db.session.add(proposal)
        retec.db.session.flush()
        self.assertIn('Project title', proposal.missing_fields)
        self.assertIn('Investment / project price', proposal.missing_fields)
        self.assertFalse(proposal.is_final)
        self.assertIsNone(proposal.valid_until)

        proposal.title = 'Site'
        proposal.summary = 'Summary'
        proposal.fee = 15000
        proposal.payment_schedule = json.dumps(
            [{'label': 'Deposit', 'amount': 7500, 'timing': 'on signing'}])
        proposal.timeline = '4 weeks'
        proposal.scope = 'Build'
        proposal.deliverables = 'Site'
        proposal.status = 'sent'
        proposal.sent_at = datetime(2026, 10, 1, 12, 0)
        proposal.validity_days = 14
        retec.db.session.flush()
        self.assertEqual(proposal.missing_fields, [])
        self.assertTrue(proposal.is_final)
        from datetime import date
        self.assertEqual(proposal.valid_until, date(2026, 10, 15))

    def test_handover_counts_and_completion(self):
        client = self._client()
        handover = ClientHandover(client=client)
        retec.db.session.add(handover)
        retec.db.session.flush()
        self.assertEqual(handover.total_count,
                         len(retec.client_documents.HANDOVER_ITEM_IDS))
        self.assertEqual(handover.checked_count, 0)
        self.assertFalse(handover.is_complete)

        handover.checklist = json.dumps({
            item_id: True for item_id in retec.client_documents.HANDOVER_ITEM_IDS
        })
        handover.signoff_name = 'Ada'
        retec.db.session.flush()
        self.assertTrue(handover.is_complete)

    def test_requirements_list_survives_bad_json(self):
        client = self._client(requirements='{broken')
        self.assertEqual(client.requirements_list, [])
        client.requirements = json.dumps(['cms', 'blog'])
        self.assertEqual(client.requirements_list, ['cms', 'blog'])


class PublicQuestionnaireTests(unittest.TestCase):
    """The /start-a-project page and submission."""

    def setUp(self):
        application.config.update(TESTING=True, WTF_CSRF_ENABLED=False,
                                  RATELIMIT_ENABLED=False)
        self.ctx = application.app_context()
        self.ctx.push()
        self.client = application.test_client()
        self._baseline = Client.query.count()

    def tearDown(self):
        retec.db.session.rollback()
        ClientQuestionnaire.query.delete()
        Client.query.filter(Client.name.in_(
            ['Ada Lovelace', 'X'])).delete(synchronize_session=False)
        retec.db.session.commit()
        retec.db.session.remove()
        self.ctx.pop()

    def test_get_renders_all_sections(self):
        response = self.client.get('/start-a-project')
        self.assertEqual(response.status_code, 200)
        body = response.get_data(as_text=True)
        self.assertIn('qs-form', body)
        self.assertIn('Client Information', body)
        self.assertIn('Functional Requirements', body)
        self.assertIn('name="website"', body)  # honeypot

    def test_valid_submission_creates_client_and_questionnaire(self):
        response = self.client.post('/start-a-project', data=questionnaire_payload(
            budget_range='25000_40000',
            contact_method='email',
            requirements__cms='1',
            requirements__booking_system='1',
            desired_launch='2026-12-01',
        ), follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn('is in.', response.get_data(as_text=True))

        client = Client.query.filter_by(email='ada@example.com').first()
        self.assertIsNotNone(client)
        self.assertEqual(client.status, 'discovery')
        self.assertEqual(client.source, 'questionnaire')
        self.assertEqual(client.budget_range, '25000_40000')
        self.assertEqual(client.requirements_list, ['booking_system', 'cms'])
        from datetime import date
        self.assertEqual(client.desired_launch, date(2026, 12, 1))

        questionnaire = ClientQuestionnaire.query.filter_by(
            client_id=client.id).first()
        self.assertIsNotNone(questionnaire)
        responses = questionnaire.parsed()
        self.assertEqual(responses['full_name'], 'Ada Lovelace')
        self.assertEqual(responses['requirements'], ['booking_system', 'cms'])
        self.assertEqual(responses['project_success'],
                         'Patients can book online without calling.')

    def test_missing_required_answers_are_rejected(self):
        response = self.client.post('/start-a-project', data={
            'full_name': 'Nobody', 'email': 'not-an-email',
        })
        self.assertEqual(response.status_code, 200)
        body = response.get_data(as_text=True)
        self.assertIn('Please check the following', body)
        self.assertEqual(Client.query.count(), self._baseline)

    def test_honeypot_submission_is_dropped(self):
        data = questionnaire_payload()
        data['website'] = 'https://spam.example'
        self.client.post('/start-a-project', data=data)
        self.assertEqual(Client.query.count(), self._baseline)

    def test_confirmation_page_renders(self):
        response = self.client.get('/start-a-project/complete')
        self.assertEqual(response.status_code, 200)
        self.assertIn('questionnaire', response.get_data(as_text=True).lower())


class AdminClientTests(unittest.TestCase):
    """Admin screens and the lifecycle POSTs."""

    def setUp(self):
        application.config.update(TESTING=True, WTF_CSRF_ENABLED=False,
                                  RATELIMIT_ENABLED=False)
        self.ctx = application.app_context()
        self.ctx.push()
        self.client = application.test_client()
        user = retec.User.query.filter_by(username='client-ops-test-admin').first()
        if user is None:
            user = retec.User(
                username='client-ops-test-admin',
                password_hash=retec.bcrypt.generate_password_hash(
                    'client-ops-test-password').decode('utf-8'))
            retec.db.session.add(user)
            retec.db.session.commit()
        with self.client.session_transaction() as session:
            session['admin_id'] = user.id
            session['admin_username'] = user.username

    def tearDown(self):
        retec.db.session.rollback()
        retec.db.session.remove()
        self.ctx.pop()

    def _new_client(self, **kwargs):
        kwargs.setdefault('name', 'Test Client')
        kwargs.setdefault('email', 'client@example.com')
        kwargs.setdefault('status', 'discovery')
        kwargs.setdefault('project_title', 'Booking system')
        kwargs.setdefault('fee', 40000)
        client = Client(**kwargs)
        retec.db.session.add(client)
        retec.db.session.commit()
        return client

    def _cleanup(self, *clients):
        for client in clients:
            retec.db.session.delete(client)
        retec.db.session.commit()

    # -- List, export, add --

    def test_clients_list_and_export_render(self):
        client = self._new_client(name='Export Me')
        try:
            response = self.client.get('/admin/clients')
            self.assertEqual(response.status_code, 200)
            self.assertIn('Export Me', response.get_data(as_text=True))

            filtered = self.client.get('/admin/clients?status=discovery&q=Export')
            self.assertEqual(filtered.status_code, 200)
            self.assertIn('Export Me', filtered.get_data(as_text=True))

            csv_response = self.client.get('/admin/clients/export.csv')
            self.assertEqual(csv_response.status_code, 200)
            self.assertIn('Export Me', csv_response.get_data(as_text=True))
        finally:
            self._cleanup(client)

    def test_add_client_validates_status_and_name(self):
        before = Client.query.count()
        rejected = self.client.post('/admin/clients/add', data={
            'name': '', 'status': 'not-a-status', 'source': 'manual',
        })
        self.assertEqual(rejected.status_code, 200)
        self.assertEqual(Client.query.count(), before)

        accepted = self.client.post('/admin/clients/add', data={
            'name': 'Added Via Form', 'status': 'lead', 'source': 'referral',
            'email': 'added@example.com', 'fee': '25,000',
        }, follow_redirects=True)
        self.assertEqual(accepted.status_code, 200)
        created = Client.query.filter_by(name='Added Via Form').first()
        self.assertIsNotNone(created)
        self.assertEqual(created.status, 'lead')
        self.assertEqual(created.source, 'referral')
        self.assertEqual(float(created.fee), 25000.0)
        self.assertTrue(
            ClientNote.query.filter_by(client_id=created.id).count() >= 1)
        self._cleanup(created)

    def test_detail_renders_every_tab(self):
        client = self._new_client()
        questionnaire = ClientQuestionnaire(
            client=client, responses=json.dumps({
                'full_name': 'Test Client', 'email': 'client@example.com',
                'looking_to_build': 'A system', 'requirements': ['cms'],
            }))
        retec.db.session.add(questionnaire)
        retec.db.session.commit()
        try:
            for tab in ('overview', 'questionnaire', 'documents',
                        'payments', 'activity', 'handover'):
                response = self.client.get(
                    '/admin/clients/%d?tab=%s' % (client.id, tab))
                self.assertEqual(response.status_code, 200, tab)
            # Unknown tabs fall back instead of 404 or crashing the include.
            response = self.client.get('/admin/clients/%d?tab=bogus' % client.id)
            self.assertEqual(response.status_code, 200)
        finally:
            self._cleanup(client)

    def test_status_change_validated_and_logged(self):
        client = self._new_client(status='discovery')
        try:
            rejected = self.client.post(
                '/admin/clients/status/%d' % client.id,
                data={'status': 'made-up'}, follow_redirects=True)
            self.assertEqual(rejected.status_code, 200)
            self.assertEqual(client.status, 'discovery')

            accepted = self.client.post(
                '/admin/clients/status/%d' % client.id,
                data={'status': 'qualified', 'tab': 'overview'},
                follow_redirects=True)
            self.assertEqual(accepted.status_code, 200)
            self.assertEqual(client.status, 'qualified')
            statuses = [n for n in client.notes if n.kind == 'status']
            self.assertTrue(any('Qualified' in n.body for n in statuses))
        finally:
            self._cleanup(client)

    # -- Proposals --

    def test_proposal_lifecycle(self):
        client = self._new_client(status='qualified')
        try:
            created = self.client.post(
                '/admin/clients/%d/proposal/add' % client.id, data={
                    'title': 'Clinic booking site',
                    'summary': 'A booking site for the clinic.',
                    'scope': 'Design and build\nDeploy',
                    'deliverables': 'Website',
                    'timeline': '4 weeks from deposit',
                    'fee': '40,000',
                    'sched_label_1': 'Deposit', 'sched_amount_1': '20000',
                    'sched_timing_1': 'on signing',
                    'sched_label_2': 'Final', 'sched_amount_2': '20000',
                    'sched_timing_2': 'on delivery',
                    'validity_days': '14',
                }, follow_redirects=True)
            self.assertEqual(created.status_code, 200)
            proposal = ClientProposal.query.filter_by(
                client_id=client.id).first()
            self.assertIsNotNone(proposal)
            self.assertTrue(proposal.reference.startswith('RETEC-P-'))
            self.assertEqual(float(proposal.fee), 40000.0)
            self.assertEqual(len(proposal.schedule_rows), 2)
            self.assertEqual(proposal.missing_fields, [])

            view = self.client.get(
                '/admin/clients/%d/proposal/%d' % (client.id, proposal.id))
            self.assertEqual(view.status_code, 200)
            body = view.get_data(as_text=True)
            self.assertIn('Clinic booking site', body)
            self.assertIn('40,000', body)

            # Sending then accepting advances the client record.
            client.status = 'proposal_sent'
            retec.db.session.commit()
            self.client.post(
                '/admin/clients/%d/proposal/%d/status' % (client.id, proposal.id),
                data={'status': 'accepted'}, follow_redirects=True)
            self.assertEqual(proposal.status, 'accepted')
            self.assertEqual(client.status, 'approved')
            self.assertIsNotNone(proposal.responded_at)

            deleted = self.client.post(
                '/admin/clients/%d/proposal/%d/delete' % (client.id, proposal.id),
                follow_redirects=True)
            self.assertEqual(deleted.status_code, 200)
            self.assertIsNone(ClientProposal.query.filter_by(
                id=proposal.id).first())
        finally:
            self._cleanup(client)

    def test_proposal_requires_summary_and_fee(self):
        client = self._new_client()
        try:
            before = ClientProposal.query.count()
            rejected = self.client.post(
                '/admin/clients/%d/proposal/add' % client.id, data={
                    'title': 'No summary', 'fee': 'not a number',
                })
            self.assertEqual(rejected.status_code, 200)
            self.assertEqual(ClientProposal.query.count(), before)
        finally:
            self._cleanup(client)

    # -- Agreements --

    def test_agreement_lifecycle_and_signed_transition(self):
        client = self._new_client(status='approved', business='Clinic Co')
        try:
            created = self.client.post(
                '/admin/clients/%d/agreement/add' % client.id, data={
                    'project_fee': '40000', 'deposit_percent': '50',
                    'support_period': '30 days after handover',
                    'start_date': '2026-11-01',
                    'expected_delivery': '2026-12-01',
                }, follow_redirects=True)
            self.assertEqual(created.status_code, 200)
            agreement = ClientAgreement.query.filter_by(
                client_id=client.id).first()
            self.assertIsNotNone(agreement)
            self.assertTrue(agreement.reference.startswith('RETEC-A-'))
            self.assertEqual(float(agreement.deposit_percent), 50)
            self.assertEqual(agreement.deposit_amount, 20000.0)

            view = self.client.get(
                '/admin/clients/%d/agreement/%d' % (client.id, agreement.id))
            self.assertEqual(view.status_code, 200)
            body = view.get_data(as_text=True)
            self.assertIn('Client Services Agreement', body)
            self.assertIn('Kenya', body)
            self.assertIn('Review with a qualified Kenyan legal professional',
                          body)
            # Filled values, no raw placeholder for the client name.
            self.assertIn('Test Client', body)
            self.assertNotIn('[CLIENT NAME]', body)

            # Signing from an approved record advances the pipeline.
            self.client.post(
                '/admin/clients/%d/agreement/%d/status' % (client.id, agreement.id),
                data={'status': 'signed', 'signed_by': 'Ada Lovelace'},
                follow_redirects=True)
            self.assertEqual(agreement.status, 'signed')
            self.assertEqual(agreement.signed_by, 'Ada Lovelace')
            self.assertIsNotNone(agreement.signed_at)
            self.assertEqual(client.status, 'signed')
        finally:
            self._cleanup(client)

    # -- Payments, notes, handover --

    def test_payment_record_toggle_and_delete(self):
        client = self._new_client(fee=40000)
        try:
            self.client.post(
                '/admin/clients/%d/payments/add' % client.id, data={
                    'label': 'Deposit', 'kind': 'deposit', 'amount': '20,000',
                    'status': 'pending', 'tab': 'payments',
                }, follow_redirects=True)
            payment = ClientPayment.query.filter_by(client_id=client.id).first()
            self.assertIsNotNone(payment)
            self.assertEqual(client.fee_paid, 0)

            self.client.post(
                '/admin/clients/%d/payments/%d/toggle' % (client.id, payment.id),
                data={'tab': 'payments'}, follow_redirects=True)
            self.assertEqual(payment.status, 'paid')
            self.assertIsNotNone(payment.paid_date)
            self.assertEqual(client.fee_paid, 20000)
            self.assertEqual(client.fee_outstanding, 20000)

            self.client.post(
                '/admin/clients/%d/payments/%d/delete' % (client.id, payment.id),
                data={'tab': 'payments'}, follow_redirects=True)
            self.assertIsNone(ClientPayment.query.filter_by(
                id=payment.id).first())
        finally:
            self._cleanup(client)

    def test_payment_rejects_unknown_kind_and_bad_amount(self):
        client = self._new_client()
        try:
            before = ClientPayment.query.count()
            self.client.post('/admin/clients/%d/payments/add' % client.id, data={
                'label': 'Weird', 'kind': 'bribe', 'amount': '100',
            }, follow_redirects=True)
            self.client.post('/admin/clients/%d/payments/add' % client.id, data={
                'label': 'Weird', 'kind': 'deposit', 'amount': 'lots',
            }, follow_redirects=True)
            self.assertEqual(ClientPayment.query.count(), before)
        finally:
            self._cleanup(client)

    def test_notes_and_task_toggle(self):
        client = self._new_client()
        try:
            self.client.post('/admin/clients/%d/notes/add' % client.id, data={
                'kind': 'call', 'body': 'Spoke about scope.', 'tab': 'activity',
            }, follow_redirects=True)
            note = ClientNote.query.filter_by(
                client_id=client.id, kind='call').first()
            self.assertIsNotNone(note)
            self.assertEqual(note.author, 'client-ops-test-admin')

            self.client.post('/admin/clients/%d/notes/add' % client.id, data={
                'kind': 'task', 'body': 'Send proposal', 'tab': 'activity',
            }, follow_redirects=True)
            task = ClientNote.query.filter_by(
                client_id=client.id, kind='task').first()
            self.assertFalse(task.done)
            self.client.post(
                '/admin/clients/%d/notes/%d/toggle' % (client.id, task.id),
                data={'tab': 'activity'}, follow_redirects=True)
            self.assertTrue(task.done)
            self.assertEqual(client.open_tasks, [])

            self.client.post(
                '/admin/clients/%d/notes/%d/delete' % (client.id, note.id),
                data={'tab': 'activity'}, follow_redirects=True)
            self.assertIsNone(ClientNote.query.filter_by(id=note.id).first())
        finally:
            self._cleanup(client)

    def test_handover_checklist_saves_and_completes(self):
        client = self._new_client()
        try:
            data = {'notes': 'Credentials handed over.'}
            for item_id in retec.client_documents.HANDOVER_ITEM_IDS:
                data['item_%s' % item_id] = '1'
            data['signoff_name'] = 'Ada Lovelace'
            data['signoff_date'] = '2026-10-08'
            data['signoff_method'] = 'email confirmation'
            self.client.post(
                '/admin/clients/%d/handover' % client.id, data=data,
                follow_redirects=True)
            handover = client.handover
            self.assertIsNotNone(handover)
            self.assertTrue(handover.is_complete)
            self.assertIsNotNone(handover.completed_at)
        finally:
            self._cleanup(client)

    # -- Enquiry conversion and access control --

    def test_enquiry_converts_once(self):
        enquiry = Enquiry(name='Curious', email='curious@example.com',
                          business='Curious Co', project_type='Web app',
                          budget='25000_40000', message='We need a system.',
                          ip_address='127.0.0.1')
        retec.db.session.add(enquiry)
        retec.db.session.commit()
        try:
            first = self.client.post(
                '/admin/enquiries/convert/%d' % enquiry.id,
                follow_redirects=True)
            self.assertEqual(first.status_code, 200)
            client = Client.query.filter_by(enquiry_id=enquiry.id).first()
            self.assertIsNotNone(client)
            self.assertEqual(client.status, 'lead')
            self.assertEqual(client.source, 'enquiry')
            self.assertEqual(client.project_title, 'Web app')
            self.assertEqual(client.budget_range, '25000_40000')

            second = self.client.post(
                '/admin/enquiries/convert/%d' % enquiry.id)
            self.assertEqual(second.status_code, 302)
            self.assertIn('/admin/clients/%d' % client.id,
                          second.headers['Location'])
            self.assertEqual(
                Client.query.filter_by(enquiry_id=enquiry.id).count(), 1)
            self._cleanup(client)
        finally:
            retec.db.session.delete(enquiry)
            retec.db.session.commit()

    def test_admin_pages_require_login(self):
        anon = application.test_client()
        for path in ('/admin/clients', '/admin/clients/export.csv',
                     '/admin/clients/add'):
            response = anon.get(path)
            self.assertEqual(response.status_code, 302, path)
            self.assertIn('/admin/login', response.headers['Location'])


if __name__ == '__main__':
    unittest.main(verbosity=2)

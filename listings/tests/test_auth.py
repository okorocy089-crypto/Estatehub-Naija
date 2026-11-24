import json
import re
import shutil
from contextlib import redirect_stdout
from decimal import Decimal
from io import BytesIO, StringIO
from smtplib import SMTPException
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import check_password
from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from django.utils import timezone
from PIL import Image

from listings.forms import AgentDetailsForm, InquiryForm, PropertyForm
from listings.models import Agent, AgentRegistrationDraft, PasswordResetCode, Property, PropertyImage, PropertyView


@override_settings(
    EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
    MEDIA_ROOT='listing-test-media',
)
class BuyerAuthenticationTests(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.addClassCleanup(shutil.rmtree, 'listing-test-media', ignore_errors=True)

    def post_json(self, path, payload, client=None, **extra):
        return (client or self.client).post(
            path,
            data=json.dumps(payload),
            content_type='application/json',
            **extra,
        )

    def test_registration_creates_and_signs_in_buyer(self):
        response = self.post_json('/api/auth/register/', {
            'fullName': 'Ada Buyer',
            'email': 'ada@example.com',
            'password': 'A-strong-password-892!',
        })

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()['user']['fullName'], 'Ada Buyer')
        user = get_user_model().objects.get(email='ada@example.com')
        self.assertTrue(user.check_password('A-strong-password-892!'))
        self.assertEqual(int(self.client.session['_auth_user_id']), user.pk)

    def test_registration_rejects_duplicate_email(self):
        User = get_user_model()
        User.objects.create_user(
            username='ada@example.com',
            email='ada@example.com',
            password='A-strong-password-892!',
        )

        response = self.post_json('/api/auth/register/', {
            'fullName': 'Ada Buyer',
            'email': 'ADA@example.com',
            'password': 'A-strong-password-892!',
        })

        self.assertEqual(response.status_code, 409)

    def test_login_with_email_and_logout(self):
        get_user_model().objects.create_user(
            username='ada@example.com',
            email='ada@example.com',
            first_name='Ada Buyer',
            password='A-strong-password-892!',
        )

        response = self.post_json('/api/auth/login/', {
            'email': 'ada@example.com',
            'password': 'A-strong-password-892!',
        })

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['user']['email'], 'ada@example.com')

        logout_response = self.post_json('/api/auth/logout/', {})
        self.assertEqual(logout_response.status_code, 200)
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_registration_requires_csrf_token(self):
        client = Client(enforce_csrf_checks=True)
        client.get('/api/auth/me/')
        token = client.cookies['csrftoken'].value
        payload = {
            'fullName': 'Ada Buyer',
            'email': 'ada@example.com',
            'password': 'A-strong-password-892!',
        }

        rejected = self.post_json('/api/auth/register/', payload, client=client)
        accepted = self.post_json(
            '/api/auth/register/',
            payload,
            client=client,
            HTTP_X_CSRFTOKEN=token,
            HTTP_ORIGIN='http://localhost:3000',
        )

        self.assertEqual(rejected.status_code, 403)
        self.assertEqual(accepted.status_code, 201)

    @override_settings(GOOGLE_CLIENT_ID='')
    def test_google_sign_in_reports_missing_configuration(self):
        response = self.post_json('/api/auth/google/', {'credential': 'token'})

        self.assertEqual(response.status_code, 503)
        self.assertIn('not configured', response.json()['error'])

    def test_registration_page_creates_account_with_separate_names(self):
        response = self.client.post('/register/', {
            'first_name': 'Ada',
            'last_name': 'Buyer',
            'email': 'ada@example.com',
            'password': 'A-strong-password-892!',
        })

        self.assertRedirects(response, '/')
        user = get_user_model().objects.get(email='ada@example.com')
        self.assertEqual(user.first_name, 'Ada')
        self.assertEqual(user.last_name, 'Buyer')
        self.assertTrue(user.check_password('A-strong-password-892!'))
        self.assertEqual(int(self.client.session['_auth_user_id']), user.pk)

    @override_settings(GOOGLE_CLIENT_ID='')
    def test_registration_page_shows_login_and_google_options(self):
        response = self.client.get('/register/')

        self.assertContains(response, 'First Name')
        self.assertContains(response, 'Last Name')
        self.assertContains(response, 'Email address')
        self.assertContains(response, 'Already have an account?')
        self.assertContains(response, 'Log in now')
        self.assertContains(response, 'Google sign-in is not configured yet.')

    def test_guest_navbar_shows_register_button_without_profile_icon(self):
        response = self.client.get('/')

        self.assertContains(response, 'Register Now')
        self.assertNotContains(response, 'Become an Agent')
        self.assertNotContains(response, 'Agent Dashboard')
        self.assertNotContains(response, 'nav-profile-toggle')

    def test_authenticated_non_agent_sees_become_agent_button(self):
        user = get_user_model().objects.create_user(
            username='buyer@example.com',
            email='buyer@example.com',
            password='A-strong-password-892!',
        )
        self.client.force_login(user)

        response = self.client.get('/')

        self.assertContains(response, 'Become an Agent')
        self.assertContains(response, '/agents/register/')
        self.assertNotContains(response, 'Agent Dashboard')

    def test_authenticated_navbar_shows_profile_menu_instead_of_register_button(self):
        get_user_model().objects.create_user(
            username='ada@example.com',
            email='ada@example.com',
            first_name='Ada',
            last_name='Buyer',
            password='A-strong-password-892!',
        )
        self.client.login(username='ada@example.com', password='A-strong-password-892!')

        response = self.client.get('/')

        self.assertContains(response, 'nav-profile-toggle')
        self.assertContains(response, 'Hi, Ada')
        self.assertContains(response, 'Logout')
        self.assertNotContains(response, 'Register Now')

    def test_logout_redirects_to_login_page(self):
        user = get_user_model().objects.create_user(
            username='ada@example.com',
            email='ada@example.com',
            first_name='Ada',
            password='A-strong-password-892!',
        )
        self.client.force_login(user)

        response = self.client.post('/logout/')

        self.assertRedirects(response, '/login/', fetch_redirect_response=False)
        login_response = self.client.get('/login/')
        self.assertContains(login_response, 'data-toast')
        self.assertContains(login_response, 'You have been logged out.')
        self.assertContains(login_response, 'role="status"')
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_guest_become_agent_flow_starts_with_registration(self):
        response = self.client.get('/agents/register/')

        self.assertRedirects(response, '/register/?next=/agents/register/')

    def test_agent_details_city_is_limited_to_configured_regions(self):
        form = AgentDetailsForm(data={
            'agency': 'Ada Homes',
            'bio': 'Residential property specialist.',
            'specialties': ['Residential'],
            'city': 'Owerri',
        })

        self.assertFalse(form.is_valid())
        self.assertIn('city', form.errors)
        self.assertEqual(
            list(form.fields['city'].choices),
            [
                ('Imo', 'Imo'),
                ('Lagos', 'Lagos'),
                ('Abuja', 'Abuja'),
                ('Port Harcourt', 'Port Harcourt'),
            ],
        )

    def test_agent_dashboard_tabs_show_owned_active_history_and_profile(self):
        user = get_user_model().objects.create_user(
            username='dashboard-agent@example.com',
            email='dashboard-agent@example.com',
            password='A-strong-password-892!',
        )
        agent = Agent.objects.create(
            user=user,
            name='Ada Agent',
            agency='Ada Homes',
            phone='+2348031234567',
            whatsapp='+2348031234567',
            bio='Residential property specialist.',
            specialties='Residential, Land',
            city='Lagos',
        )
        Property.objects.create(
            title='Active Lagos Home',
            description='An active listing.',
            price=50000000,
            address='Victoria Island',
            city='Lagos',
            agent=agent,
            status='available',
            views_count=12,
        )
        Property.objects.create(
            title='Sold Lagos Home',
            description='A completed sale.',
            price=60000000,
            address='Lekki',
            city='Lagos',
            agent=agent,
            status='sold',
        )
        Property.objects.create(
            title='Rented Lagos Flat',
            description='A completed rental.',
            price=3000000,
            listing_type='rent',
            address='Ikeja',
            city='Lagos',
            agent=agent,
            status='rented',
        )
        self.client.force_login(user)

        active_response = self.client.get('/dashboard/')
        self.assertContains(active_response, 'Active Lagos Home')
        self.assertNotContains(active_response, 'Sold Lagos Home')
        self.assertContains(active_response, 'Browse All')
        self.assertContains(active_response, 'New listing')
        self.assertContains(active_response, '12 views')
        self.assertContains(active_response, 'agent-dashboard-mobile-nav')
        self.assertContains(active_response, 'aria-label="New listing"')
        self.assertContains(active_response, 'class="bi bi-plus-circle"')
        self.assertContains(active_response, 'class="bi bi-check2-circle"')
        self.assertContains(active_response, 'class="bi bi-person-circle"')
        self.assertContains(active_response, 'class="agent-dashboard-page"')
        self.assertContains(active_response, 'agent-dashboard-mobile-active is-active')
        self.assertContains(active_response, 'href="/property/add/"')

        history_response = self.client.get('/dashboard/?tab=history')
        self.assertContains(history_response, 'Sold Lagos Home')
        self.assertContains(history_response, 'Rented Lagos Flat')
        self.assertNotContains(history_response, 'Active Lagos Home')
        self.assertContains(history_response, 'agent-dashboard-mobile-icon is-active')
        self.assertContains(history_response, 'aria-current="page"')

        profile_response = self.client.get('/dashboard/?tab=profile')
        self.assertContains(profile_response, 'Ada Agent')
        self.assertContains(profile_response, 'Ada Homes')
        self.assertContains(profile_response, 'Residential, Land')
        self.assertContains(profile_response, 'Primary city / region')
        self.assertContains(profile_response, 'aria-label="Agent profile"')

    def create_agent_with_property(self, username='listing-agent@example.com', status='available'):
        user = get_user_model().objects.create_user(
            username=username,
            email=username,
            password='A-strong-password-892!',
        )
        agent = Agent.objects.create(
            user=user,
            name='Ada Agent',
            agency='Ada Homes',
            phone='+2348031234567',
            whatsapp='+2348031234567',
            city='Lagos',
        )
        property_obj = Property.objects.create(
            title='Lagos Family Home',
            description='A well-maintained property.',
            price=50000000,
            address='Victoria Island',
            city='Lagos',
            state='Lagos State',
            agent=agent,
            status=status,
        )
        return user, agent, property_obj

    def property_form_data(self, **overrides):
        data = {
            'title': 'New Lagos Family Home',
            'description': (
                'A well-maintained family home with bright rooms, modern finishes, '
                'and convenient access to nearby shops.'
            ),
            'price': '50000000',
            'listing_type': 'sale',
            'property_type': 'residential',
            'bedrooms': '4',
            'bathrooms': '3',
            'floor_area_sqm': '350',
            'plot_area_sqm': '500',
            'area': 'Works Layout',
            'address': 'Victoria Island',
            'city': 'Lagos',
            'state': 'Lagos State',
            'title_deed': 'coo',
            'furnished': 'Unfurnished',
            'amenities': ['24/7 Security', 'Borehole'],
            'other_amenities': '',
        }
        data.update(overrides)
        return data

    def property_form_files(self, count=6):
        uploads = []
        colors = ('red', 'green', 'blue', 'orange', 'purple', 'yellow', 'black', 'white', 'gray', 'pink')
        for index in range(count):
            image = BytesIO()
            Image.new('RGB', (12, 12), color=colors[index % len(colors)]).save(
                image,
                format='PNG',
            )
            uploads.append(SimpleUploadedFile(
                f'property-{index}.png',
                image.getvalue(),
                content_type='image/png',
            ))
        return {
            'images': uploads,
            'title_deed_document': SimpleUploadedFile(
                'title-deed.pdf',
                b'%PDF-1.4\nEstateHub test document\n%%EOF',
                content_type='application/pdf',
            ),
        }

    def test_price_forms_accept_comma_formatted_values(self):
        property_form = PropertyForm(
            data=self.property_form_data(price='50,000,000'),
            files=self.property_form_files(),
        )
        self.assertTrue(property_form.is_valid(), property_form.errors)
        self.assertEqual(property_form.cleaned_data['price'], Decimal('50000000'))

        inquiry_form = InquiryForm(data={
            'name': 'Buyer',
            'email': 'buyer@example.com',
            'phone': '08031234567',
            'inquiry_type': 'price_offer',
            'offer_amount': '12,345,678.90',
            'message': 'I would like to make an offer.',
        })
        self.assertTrue(inquiry_form.is_valid(), inquiry_form.errors)
        self.assertEqual(inquiry_form.cleaned_data['offer_amount'], Decimal('12345678.90'))

    def test_listing_form_rent_period_land_fields_and_amenities(self):
        land_form = PropertyForm(data=self.property_form_data(
            property_type='land',
            bedrooms='999',
            bathrooms='not a number',
            furnished='Unfurnished',
            amenities=['Borehole', 'Parking'],
            other_amenities='Gate, Landscaped garden',
        ), files=self.property_form_files())
        self.assertTrue(land_form.is_valid(), land_form.errors)
        self.assertIsNone(land_form.cleaned_data['bedrooms'])
        self.assertIsNone(land_form.cleaned_data['bathrooms'])
        self.assertEqual(land_form.cleaned_data['furnished'], '')
        self.assertEqual(
            land_form.cleaned_data['amenities'],
            'Borehole, Parking, Gate, Landscaped garden',
        )
        self.assertNotIn('status', land_form.fields)

        rental_form = PropertyForm(data=self.property_form_data(
            listing_type='rent',
            property_type='rentals',
        ), files=self.property_form_files())
        self.assertFalse(rental_form.is_valid())
        self.assertIn('rent_period', rental_form.errors)
        rental_form = PropertyForm(data=self.property_form_data(
            listing_type='rent',
            property_type='rentals',
            rent_period='month',
        ), files=self.property_form_files())
        self.assertTrue(rental_form.is_valid(), rental_form.errors)

    def test_listing_form_requires_six_to_ten_photos(self):
        too_few = PropertyForm(
            data=self.property_form_data(),
            files=self.property_form_files(count=5),
        )
        self.assertFalse(too_few.is_valid())
        self.assertIn('Upload at least 1 more', str(too_few.errors['images']))

        too_many = PropertyForm(
            data=self.property_form_data(),
            files=self.property_form_files(count=11),
        )
        self.assertFalse(too_many.is_valid())
        self.assertIn('maximum upload limit (10)', str(too_many.errors['images']))

    def test_listing_form_rejects_gibberish_and_out_of_range_values(self):
        form = PropertyForm(
            data=self.property_form_data(
                title='!!!!!!!!!!!!',
                description='asdf qwer zxcv hjkl asdf qwer zxcv hjkl.',
                price='999999999999999999',
                bedrooms='100',
                city='Lagos123',
            ),
            files=self.property_form_files(),
        )

        self.assertFalse(form.is_valid())
        for field in ('title', 'description', 'price', 'bedrooms', 'city'):
            self.assertIn(field, form.errors)

    def test_listing_form_requires_valid_title_deed_document(self):
        no_document = self.property_form_files()
        no_document.pop('title_deed_document')
        form = PropertyForm(data=self.property_form_data(), files=no_document)

        self.assertFalse(form.is_valid())
        self.assertIn('title_deed_document', form.errors)

        invalid_document = self.property_form_files()
        invalid_document['title_deed_document'] = SimpleUploadedFile(
            'title-deed.exe',
            b'not an accepted document',
            content_type='application/octet-stream',
        )
        form = PropertyForm(
            data=self.property_form_data(),
            files=invalid_document,
        )
        self.assertFalse(form.is_valid())
        self.assertIn('title_deed_document', form.errors)

    @override_settings(MEDIA_ROOT='property-test-media')
    def test_agent_can_upload_multiple_photos_to_listing(self):
        self.addCleanup(shutil.rmtree, 'property-test-media', ignore_errors=True)
        user, agent, _property_obj = self.create_agent_with_property()
        self.client.force_login(user)

        uploads = []
        for color in ('red', 'green', 'blue', 'orange', 'purple', 'yellow'):
            image = BytesIO()
            Image.new('RGB', (12, 12), color=color).save(image, format='PNG')
            uploads.append(SimpleUploadedFile(
                f'{color}.png',
                image.getvalue(),
                content_type='image/png',
            ))

        response = self.client.post('/property/add/', {
            **self.property_form_data(),
            **self.property_form_files(),
            'images': uploads,
        })

        self.assertRedirects(response, '/dashboard/')
        created = Property.objects.get(title='New Lagos Family Home')
        self.assertTrue(created.title_deed_document.name.endswith('.pdf'))
        self.assertEqual(created.images.count(), 6)
        self.assertEqual(PropertyImage.objects.filter(property=created).count(), 6)
        detail_response = self.client.get(f'/property/{created.slug}/')
        self.assertContains(detail_response, 'View title deed document')

    def test_area_filter_matches_neighborhood(self):
        _user, _agent, property_obj = self.create_agent_with_property()
        property_obj.area = 'Works Layout'
        property_obj.save(update_fields=['area'])
        other = Property.objects.create(
            title='Different Neighborhood Home',
            description='Another listing.',
            price=50000000,
            area='New Owerri',
            city='Lagos',
            agent=property_obj.agent,
        )

        response = self.client.get('/?area=Works')

        self.assertContains(response, property_obj.title)
        self.assertNotContains(response, other.title)

    def test_agent_can_create_and_update_listing_without_status_field(self):
        user, agent, property_obj = self.create_agent_with_property()
        self.client.force_login(user)

        response = self.client.post('/property/add/', {
            **self.property_form_data(),
            **self.property_form_files(),
        })

        self.assertRedirects(response, '/dashboard/')
        created = Property.objects.get(title='New Lagos Family Home')
        self.assertEqual(created.agent, agent)
        self.assertEqual(created.status, 'available')
        create_form_response = self.client.get('/property/add/')
        self.assertContains(create_form_response, 'Title')
        self.assertContains(create_form_response, 'Select file')
        self.assertContains(create_form_response, 'disabled')
        self.assertNotContains(create_form_response, 'name="status"')
        self.assertNotContains(create_form_response, 'Choose the property location on the map')
        self.assertNotContains(create_form_response, 'data-location-picker')
        self.assertNotContains(create_form_response, 'name="latitude"')
        self.assertNotContains(create_form_response, 'name="longitude"')
        saved_document = created.title_deed_document.name

        response = self.client.post(
            f'/property/{created.slug}/edit/',
            self.property_form_data(status='sold', title='Updated Family Home'),
        )

        self.assertRedirects(response, '/dashboard/')
        created.refresh_from_db()
        self.assertEqual(created.title, 'Updated Family Home')
        self.assertEqual(created.status, 'available')
        self.assertEqual(created.images.count(), 6)
        self.assertEqual(created.title_deed_document.name, saved_document)

    def test_agent_can_complete_listing_once_and_sold_listing_is_immutable(self):
        user, agent, property_obj = self.create_agent_with_property()
        self.client.force_login(user)

        response = self.client.get(f'/property/{property_obj.slug}/mark-complete/')
        self.assertEqual(response.status_code, 405)

        response = self.client.post(f'/property/{property_obj.slug}/mark-complete/')

        self.assertRedirects(response, '/dashboard/?tab=history')
        property_obj.refresh_from_db()
        self.assertEqual(property_obj.status, 'sold')
        self.assertContains(self.client.get('/dashboard/?tab=history'), property_obj.title)
        self.assertNotContains(self.client.get('/'), property_obj.title)
        self.assertEqual(
            self.client.get('/property/{}/edit/'.format(property_obj.slug)).status_code,
            404,
        )
        self.assertEqual(
            self.client.get('/property/{}/delete/'.format(property_obj.slug)).status_code,
            404,
        )

        response = self.client.post(f'/property/{property_obj.slug}/mark-complete/')
        self.assertRedirects(response, '/dashboard/?tab=history')
        property_obj.refresh_from_db()
        self.assertEqual(property_obj.status, 'sold')

    def test_rental_completion_moves_listing_to_history_as_rented(self):
        user, agent, property_obj = self.create_agent_with_property(
            username='rental-agent@example.com',
        )
        property_obj.listing_type = 'rent'
        property_obj.save(update_fields=['listing_type'])
        self.client.force_login(user)

        response = self.client.post(f'/property/{property_obj.slug}/mark-complete/')

        self.assertRedirects(response, '/dashboard/?tab=history')
        property_obj.refresh_from_db()
        self.assertEqual(property_obj.status, 'rented')
        self.assertContains(self.client.get('/dashboard/?tab=history'), 'Lagos Family Home')

    def test_delisting_requires_confirmation_then_deletes_listing(self):
        user, agent, property_obj = self.create_agent_with_property(
            username='delist-agent@example.com',
        )
        self.client.force_login(user)

        response = self.client.get(f'/property/{property_obj.slug}/delete/')

        self.assertContains(response, 'will be permanently deleted')
        self.assertTrue(Property.objects.filter(pk=property_obj.pk).exists())

        response = self.client.post(f'/property/{property_obj.slug}/delete/')

        self.assertRedirects(response, '/dashboard/')
        self.assertFalse(Property.objects.filter(pk=property_obj.pk).exists())

    def test_property_detail_get_increments_views_count_without_post_increment(self):
        user, agent, property_obj = self.create_agent_with_property(
            username='views-agent@example.com',
        )
        for index, color in enumerate(('red', 'blue')):
            image = BytesIO()
            Image.new('RGB', (12, 12), color=color).save(image, format='PNG')
            property_obj.images.create(
                image=SimpleUploadedFile(
                    f'gallery-{index}.png',
                    image.getvalue(),
                    content_type='image/png',
                ),
            )

        response = self.client.get(f'/property/{property_obj.slug}/')

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Show previous image')
        self.assertContains(response, 'Show next image')
        self.assertContains(response, 'data-gallery-thumbnail')
        self.assertContains(response, 'detail-price-actions')
        self.assertContains(response, 'detail-contact-row has-agent')
        rendered_detail = response.content.decode()
        self.assertLess(
            rendered_detail.index('class="detail-sidebar"'),
            rendered_detail.index('class="property-content-card"'),
        )
        property_obj.refresh_from_db()
        self.assertEqual(property_obj.views_count, 1)

        response = self.client.get(f'/property/{property_obj.slug}/')
        self.assertEqual(response.status_code, 200)
        property_obj.refresh_from_db()
        self.assertEqual(property_obj.views_count, 1)

        response = self.client.post(f'/property/{property_obj.slug}/', {})

        self.assertEqual(response.status_code, 200)
        property_obj.refresh_from_db()
        self.assertEqual(property_obj.views_count, 1)

    def test_property_views_are_counted_once_per_authenticated_account(self):
        first_user, _agent, property_obj = self.create_agent_with_property(
            username='first-viewer@example.com',
        )
        second_user = get_user_model().objects.create_user(
            username='second-viewer@example.com',
            email='second-viewer@example.com',
            password='A-strong-password-892!',
        )
        url = f'/property/{property_obj.slug}/'

        self.client.force_login(first_user)
        self.client.get(url)
        self.client.get(url)
        property_obj.refresh_from_db()
        self.assertEqual(property_obj.views_count, 1)

        self.client.force_login(second_user)
        self.client.get(url)
        property_obj.refresh_from_db()
        self.assertEqual(property_obj.views_count, 2)

    def test_anonymous_property_views_are_counted_once_per_persistent_visitor_cookie(self):
        _user, _agent, property_obj = self.create_agent_with_property(
            username='anonymous-view-agent@example.com',
        )
        url = f'/property/{property_obj.slug}/'

        first_response = self.client.get(url)
        visitor_cookie = first_response.cookies['visitor_id']
        self.assertEqual(visitor_cookie['max-age'], 60 * 60 * 24 * 365 * 5)
        self.assertTrue(visitor_cookie['httponly'])
        self.assertEqual(visitor_cookie['samesite'], 'Lax')

        self.client.get(url)
        property_obj.refresh_from_db()
        self.assertEqual(property_obj.views_count, 1)

        another_session = Client()
        another_session.cookies['visitor_id'] = visitor_cookie.value
        another_session.get(url)
        property_obj.refresh_from_db()
        self.assertEqual(property_obj.views_count, 1)

        another_visitor = Client()
        another_visitor.get(url)
        property_obj.refresh_from_db()
        self.assertEqual(property_obj.views_count, 2)
        self.assertEqual(property_obj.visitor_views.count(), 2)

    def test_invalid_visitor_cookie_is_replaced_with_a_valid_uuid(self):
        _user, _agent, property_obj = self.create_agent_with_property(
            username='invalid-cookie-view-agent@example.com',
        )
        self.client.cookies['visitor_id'] = 'not-a-uuid'

        response = self.client.get(f'/property/{property_obj.slug}/')

        visitor_id = response.cookies['visitor_id'].value
        self.assertEqual(str(PropertyView.objects.get(property=property_obj).visitor_id), visitor_id)
        self.assertNotEqual(visitor_id, 'not-a-uuid')

    def test_existing_anonymous_session_view_is_reused_when_visitor_cookie_is_set(self):
        _user, _agent, property_obj = self.create_agent_with_property(
            username='legacy-view-agent@example.com',
        )
        session = self.client.session
        session['existing_session'] = True
        session.save()
        PropertyView.objects.create(
            property=property_obj,
            user=None,
            session_key=session.session_key,
        )
        property_obj.views_count = 1
        property_obj.save(update_fields=['views_count'])

        response = self.client.get(f'/property/{property_obj.slug}/')

        self.assertEqual(PropertyView.objects.filter(property=property_obj).count(), 1)
        property_obj.refresh_from_db()
        self.assertEqual(property_obj.views_count, 1)
        self.assertEqual(
            str(PropertyView.objects.get(property=property_obj).visitor_id),
            response.cookies['visitor_id'].value,
        )

    @override_settings(MEDIA_ROOT='agent-test-media')
    def test_agent_registration_verifies_email_then_creates_profile(self):
        self.addCleanup(shutil.rmtree, 'agent-test-media', ignore_errors=True)
        user = get_user_model().objects.create_user(
            username='agent@example.com',
            email='agent@example.com',
            password='A-strong-password-892!',
        )
        self.client.force_login(user)

        image = BytesIO()
        Image.new('RGB', (8, 8), color='blue').save(image, format='PNG')
        response = self.client.post('/agents/register/', {
            'name': 'Ada Agent',
            'phone': '0803 123 4567',
            'photo': SimpleUploadedFile(
                'agent.png',
                image.getvalue(),
                content_type='image/png',
            ),
        })

        self.assertRedirects(response, '/agents/verify-email/')
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ['agent@example.com'])
        code = re.search(r'\b(\d{6})\b', mail.outbox[0].body).group(1)
        draft = AgentRegistrationDraft.objects.get(user=user)
        self.assertEqual(draft.phone, '+2348031234567')
        self.assertFalse(draft.email_verified)
        self.assertTrue(check_password(code, draft.code_hash))

        invalid_code = '000000' if code != '000000' else '000001'
        response = self.client.post('/agents/verify-email/', {'code': invalid_code})
        self.assertEqual(response.status_code, 200)
        draft.refresh_from_db()
        self.assertEqual(draft.attempts, 1)
        self.assertContains(response, 'incorrect')

        response = self.client.post('/agents/verify-email/', {'code': code})
        self.assertRedirects(response, '/agents/details/')
        draft.refresh_from_db()
        self.assertTrue(draft.email_verified)
        self.assertEqual(draft.code_hash, '')

        response = self.client.get('/agents/details/')
        self.assertContains(response, '<select name="city"')
        for region in ('Imo', 'Lagos', 'Abuja', 'Port Harcourt'):
            self.assertContains(response, f'<option value="{region}">{region}</option>')

        response = self.client.post('/agents/details/', {
            'agency': 'Ada Homes',
            'bio': 'Residential property specialist.',
            'specialties': ['Residential', 'Land'],
            'city': 'Lagos',
        })

        self.assertRedirects(response, '/dashboard/')
        agent = Agent.objects.get(user=user)
        self.assertEqual(agent.name, 'Ada Agent')
        self.assertEqual(agent.agency, 'Ada Homes')
        self.assertEqual(agent.phone, '+2348031234567')
        self.assertEqual(agent.whatsapp, '+2348031234567')
        self.assertEqual(agent.specialties, 'Residential, Land')
        self.assertTrue(agent.verified)
        self.assertTrue(agent.photo)
        self.assertFalse(AgentRegistrationDraft.objects.filter(user=user).exists())

        response = self.client.get('/')
        self.assertContains(response, 'Agent Dashboard')
        self.assertContains(response, 'nav-agent-photo')

    @override_settings(GOOGLE_CLIENT_ID='test-google-client-id')
    @patch('google.oauth2.id_token.verify_oauth2_token')
    def test_google_login_redirects_to_profile_completion_when_names_missing(self, mock_verify):
        mock_verify.return_value = {
            'email': 'ada@example.com',
            'email_verified': True,
            'name': 'Ada Brown',
            'given_name': 'Ada',
            'family_name': '',
        }

        response = self.client.post(
            '/api/auth/google/',
            data=json.dumps({'credential': 'sample-google-token'}),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['redirect_to'], '/google/profile/')
        self.assertTrue(self.client.session.get('_auth_user_id'))

    @override_settings(GOOGLE_CLIENT_ID='test-google-client-id')
    def test_google_sign_in_button_is_configured_on_auth_pages(self):
        response = self.client.get('/login/')

        self.assertEqual(
            response.headers.get('Cross-Origin-Opener-Policy'),
            'same-origin-allow-popups',
        )
        self.assertContains(response, 'client_id: "test\\u002Dgoogle\\u002Dclient\\u002Did"')
        self.assertContains(response, '/api/auth/google/')
        self.assertContains(response, 'Loading Google sign-in')
        self.assertContains(response, 'Google sign-in could not load.')
        self.assertNotContains(response, 'Google sign-in is not configured yet.')

    def test_login_page_authenticates_with_email(self):
        get_user_model().objects.create_user(
            username='ada@example.com',
            email='ada@example.com',
            first_name='Ada',
            password='A-strong-password-892!',
        )

        response = self.client.post('/login/', {
            'username': 'ada@example.com',
            'password': 'A-strong-password-892!',
        })

        self.assertRedirects(response, '/')
        self.assertTrue(response.wsgi_request.user.is_authenticated)

    def test_auth_pages_reject_external_next_redirects(self):
        get_user_model().objects.create_user(
            username='ada@example.com',
            email='ada@example.com',
            password='A-strong-password-892!',
        )
        response = self.client.post('/login/?next=https://example.com', {
            'username': 'ada@example.com',
            'password': 'A-strong-password-892!',
            'next': 'https://example.com',
        })

        self.assertRedirects(response, '/')

    def test_password_reset_sends_code_verifies_and_resets_password(self):
        user = get_user_model().objects.create_user(
            username='ada@example.com',
            email='ada@example.com',
            first_name='Ada',
            password='A-strong-password-892!',
        )

        response = self.client.post('/password-reset/', {'email': 'ada@example.com'})
        self.assertRedirects(response, '/password-reset/verify/')
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ['ada@example.com'])

        code = re.search(r'\b(\d{6})\b', mail.outbox[0].body).group(1)
        response = self.client.post('/password-reset/verify/', {'code': code})
        self.assertRedirects(response, '/password-reset/new/')

        response = self.client.post('/password-reset/new/', {
            'new_password1': 'A-new-strong-password-345!',
            'new_password2': 'A-new-strong-password-345!',
        })
        self.assertRedirects(response, '/login/')
        user.refresh_from_db()
        self.assertTrue(user.check_password('A-new-strong-password-345!'))
        self.assertFalse(user.check_password('A-strong-password-892!'))
        self.assertNotIn('password_reset_verified_user_id', self.client.session)

        response = self.client.post('/login/', {
            'username': 'ada@example.com',
            'password': 'A-new-strong-password-345!',
        })
        self.assertRedirects(response, '/')
        self.assertTrue(response.wsgi_request.user.is_authenticated)

    def test_password_reset_request_does_not_disclose_unknown_email(self):
        response = self.client.post('/password-reset/', {'email': 'unknown@example.com'})

        self.assertRedirects(response, '/password-reset/verify/')
        self.assertEqual(len(mail.outbox), 0)
        response = self.client.get('/password-reset/verify/')
        self.assertContains(response, 'If an account exists')

    @override_settings(EMAIL_BACKEND='django.core.mail.backends.console.EmailBackend')
    def test_password_reset_explains_console_delivery_in_development(self):
        get_user_model().objects.create_user(
            username='ada@example.com',
            email='ada@example.com',
            password='A-strong-password-892!',
        )

        console_output = StringIO()
        with redirect_stdout(console_output):
            self.client.post('/password-reset/', {'email': 'ada@example.com'})

        self.assertIn('Your EstateHub password reset code', console_output.getvalue())
        self.assertRegex(console_output.getvalue(), r'\b\d{6}\b')

        response = self.client.get('/password-reset/verify/')

        self.assertContains(response, 'Email delivery is not configured')
        self.assertContains(response, 'application server console')

    @patch('listings.auth_views.send_mail', side_effect=SMTPException('SMTP unavailable'))
    def test_password_reset_send_failure_invalidates_code(self, send_mail_mock):
        get_user_model().objects.create_user(
            username='ada@example.com',
            email='ada@example.com',
            password='A-strong-password-892!',
        )

        with self.assertLogs('listings.auth_views', level='ERROR') as log_output:
            response = self.client.post('/password-reset/', {'email': 'ada@example.com'})

        self.assertRedirects(response, '/password-reset/')
        self.assertFalse(PasswordResetCode.objects.filter(user__email='ada@example.com').exists())
        self.assertTrue(send_mail_mock.called)
        self.assertIn('Could not send password reset email', log_output.output[0])

    def test_password_reset_rejects_invalid_codes_and_limits_attempts(self):
        get_user_model().objects.create_user(
            username='ada@example.com',
            email='ada@example.com',
            password='A-strong-password-892!',
        )
        self.client.post('/password-reset/', {'email': 'ada@example.com'})
        sent_code = re.search(r'\b(\d{6})\b', mail.outbox[0].body).group(1)
        invalid_code = '000000' if sent_code != '000000' else '000001'

        for _ in range(5):
            response = self.client.post('/password-reset/verify/', {'code': invalid_code})
            self.assertEqual(response.status_code, 200)
        self.assertFalse(
            PasswordResetCode.objects.filter(user__email='ada@example.com').exists()
        )

    def test_password_reset_code_expires(self):
        get_user_model().objects.create_user(
            username='ada@example.com',
            email='ada@example.com',
            password='A-strong-password-892!',
        )
        self.client.post('/password-reset/', {'email': 'ada@example.com'})
        code = re.search(r'\b(\d{6})\b', mail.outbox[0].body).group(1)
        reset_code = PasswordResetCode.objects.get(user__email='ada@example.com')
        reset_code.expires_at = timezone.now()
        reset_code.save(update_fields=['expires_at'])

        response = self.client.post('/password-reset/verify/', {'code': code})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'invalid or expired')

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import RequestFactory, TestCase, override_settings

from listings.models import Agent, Favorite, Property, SavedSearch
from listings.views import _send_saved_search_alerts


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class BuyerFeatureTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.agent_user = user_model.objects.create_user(
            username="agent@example.com",
            email="agent@example.com",
            password="A-strong-password-892!",
        )
        self.agent = Agent.objects.create(
            user=self.agent_user,
            name="Ada Agent",
            agency="Ada Homes",
            phone="+2348031234567",
            whatsapp="2348031234567",
            city="Owerri",
        )
        self.property = Property.objects.create(
            title="Owerri Family Home",
            description="A family home in a quiet and convenient neighborhood.",
            price=50000000,
            city="Owerri",
            area="Works Layout",
            latitude=5.4833,
            longitude=7.0333,
            agent=self.agent,
        )
        self.buyer = user_model.objects.create_user(
            username="buyer@example.com",
            email="buyer@example.com",
            password="A-strong-password-892!",
        )

    def test_footer_links_to_browse_agent_help_and_legal_pages(self):
        response = self.client.get("/")

        self.assertContains(response, "Homes for sale")
        self.assertNotContains(response, "Map search")
        self.assertNotContains(response, "View properties on map")
        self.assertContains(response, "Become an agent")
        self.assertContains(response, "Listing verification")
        self.assertContains(response, "Privacy notice")

    def test_information_pages_render(self):
        for slug in ("about", "verification", "safety", "contact", "privacy", "terms"):
            with self.subTest(page=slug):
                response = self.client.get(f"/info/{slug}/")
                self.assertEqual(response.status_code, 200)

    def test_listing_report_feature_is_not_available(self):
        response = self.client.get(f"/property/{self.property.slug}/")

        self.assertNotContains(response, "Report this listing")
        self.assertEqual(
            self.client.post(f"/property/{self.property.slug}/report/").status_code,
            404,
        )

    def test_map_routes_are_removed(self):
        self.assertEqual(self.client.get("/property-map/").status_code, 404)
        self.assertEqual(self.client.get("/property-map/data/").status_code, 404)

    def test_user_can_save_and_remove_a_property(self):
        self.client.force_login(self.buyer)
        catalog = self.client.get("/")
        self.assertContains(catalog, 'class="bi bi-bookmark"')
        self.assertNotContains(catalog, ">Save</span>")

        response = self.client.post(f"/property/{self.property.slug}/save/", {
            "next": "/",
        }, HTTP_X_REQUESTED_WITH="XMLHttpRequest")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {
            "saved": True,
            "property_id": self.property.pk,
        })
        self.assertFalse(response.has_header("Location"))
        self.assertTrue(Favorite.objects.filter(
            user=self.buyer,
            property=self.property,
        ).exists())
        saved_page = self.client.get("/saved-properties/")
        self.assertContains(saved_page, self.property.title)
        self.assertContains(saved_page, 'class="bi bi-bookmark-fill"')
        self.assertContains(saved_page, 'class="favorite-label" data-favorite-label')
        self.assertContains(saved_page, '>Saved</span>')

        response = self.client.post(
            f"/property/{self.property.slug}/save/",
            {"next": "/"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(response.json()["saved"], False)
        self.assertFalse(Favorite.objects.filter(
            user=self.buyer,
            property=self.property,
        ).exists())

    def test_saved_search_can_be_created_renamed_paused_and_deleted(self):
        self.client.force_login(self.buyer)
        response = self.client.post("/saved-searches/save/", {
            "name": "Homes in Owerri",
            "city": "Owerri",
            "email_alerts": "on",
        })
        self.assertRedirects(response, "/saved-searches/")
        search = SavedSearch.objects.get(user=self.buyer)
        self.assertEqual(search.criteria, {"city": "Owerri"})

        response = self.client.post(
            f"/saved-searches/{search.pk}/rename/",
            {"name": "Owerri family homes"},
        )
        self.assertRedirects(response, "/saved-searches/")
        search.refresh_from_db()
        self.assertEqual(search.name, "Owerri family homes")

        self.client.post(f"/saved-searches/{search.pk}/toggle-alerts/")
        search.refresh_from_db()
        self.assertFalse(search.email_alerts)

        self.client.post(f"/saved-searches/{search.pk}/delete/")
        self.assertFalse(SavedSearch.objects.filter(pk=search.pk).exists())

    def test_saved_search_actions_cannot_modify_another_users_search(self):
        search = SavedSearch.objects.create(
            user=self.buyer,
            name="Private search",
            criteria={"city": "Owerri"},
            filter_hash="a" * 64,
        )
        another_buyer = get_user_model().objects.create_user(
            username="other@example.com",
            email="other@example.com",
            password="A-strong-password-892!",
        )
        self.client.force_login(another_buyer)

        response = self.client.post(f"/saved-searches/{search.pk}/delete/")

        self.assertEqual(response.status_code, 404)
        self.assertTrue(SavedSearch.objects.filter(pk=search.pk).exists())

    def test_saved_search_alert_emails_matching_buyer_but_not_listing_agent(self):
        buyer_search = SavedSearch.objects.create(
            user=self.buyer,
            name="Owerri properties",
            criteria={"city": "Owerri"},
            filter_hash="b" * 64,
        )
        SavedSearch.objects.create(
            user=self.agent_user,
            name="Agent's own search",
            criteria={"city": "Owerri"},
            filter_hash="c" * 64,
        )
        request = RequestFactory().get("/")

        _send_saved_search_alerts(request, self.property)

        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [self.buyer.email])
        self.assertIn(f"/property/{self.property.slug}/", mail.outbox[0].body)
        self.assertTrue(SavedSearch.objects.filter(pk=buyer_search.pk).exists())

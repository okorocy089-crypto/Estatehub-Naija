import hashlib
import json
import logging
import uuid
from decimal import Decimal, InvalidOperation
from smtplib import SMTPException

from django.conf import settings
from django.http import HttpResponseRedirect, JsonResponse
from django.shortcuts import render, get_object_or_404, redirect
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.mail import send_mail
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import F, Q
from django.urls import reverse_lazy, reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST
from urllib.parse import urlencode

from .models import (
    Agent,
    Favorite,
    Inquiry,
    Property,
    PropertyImage,
    PropertyView,
    SavedSearch,
)
from .forms import InquiryForm, PropertyForm, SavedSearchForm

logger = logging.getLogger(__name__)


def _public_property_queryset():
    return Property.objects.filter(
        is_approved=True,
        status__in=["available", "under_offer"],
    )


def _apply_listing_filters(queryset, filters):
    query = str(filters.get("q", "")).strip()[:100]
    if query:
        queryset = queryset.filter(
            Q(title__icontains=query)
            | Q(description__icontains=query)
            | Q(address__icontains=query)
            | Q(area__icontains=query)
            | Q(city__icontains=query)
        )

    city = str(filters.get("city", "")).strip()[:100]
    if city:
        queryset = queryset.filter(city__iexact=city)
    area = str(filters.get("area", "")).strip()[:150]
    if area:
        queryset = queryset.filter(area__icontains=area)

    listing_type = filters.get("listing_type")
    if listing_type in dict(Property.LISTING_TYPES):
        queryset = queryset.filter(listing_type=listing_type)

    property_type = filters.get("property_type")
    if property_type in dict(Property.PROPERTY_TYPES):
        queryset = queryset.filter(property_type=property_type)

    bedrooms = str(filters.get("bedrooms", "")).strip()
    if bedrooms.isdigit() and 1 <= int(bedrooms) <= 50:
        queryset = queryset.filter(bedrooms__gte=int(bedrooms))

    for key, lookup in (("min_price", "price__gte"), ("max_price", "price__lte")):
        raw_value = str(filters.get(key, "")).replace(",", "").strip()
        if raw_value:
            try:
                amount = Decimal(raw_value)
            except InvalidOperation:
                continue
            if amount.is_finite() and amount >= 0:
                queryset = queryset.filter(**{lookup: amount})
    return queryset

def property_list_view(request):
    """
    Main catalog view narrowing the query step-by-step from URL parameters:
    ?city=Owerri&min_price=20000000&max_price=80000000&bedrooms=3&listing_type=sale&property_type=duplex
    """
    queryset = _apply_listing_filters(_public_property_queryset(), request.GET)
    q = request.GET.get("q", "").strip()
    city = request.GET.get("city", "").strip()
    area = request.GET.get("area", "").strip()
    listing_type = request.GET.get("listing_type", "").strip()
    property_type = request.GET.get("property_type", "").strip()
    bedrooms = request.GET.get("bedrooms", "").strip()
    min_price = request.GET.get("min_price", "").strip()
    max_price = request.GET.get("max_price", "").strip()

    # Title deed filter
    title_deed = request.GET.get('title_deed', '').strip()
    if title_deed:
        queryset = queryset.filter(title_deed__icontains=title_deed)

    # 9. Sorting
    sort_by = request.GET.get('sort_by', 'newest')
    if sort_by == 'price_asc':
        queryset = queryset.order_by('price')
    elif sort_by == 'price_desc':
        queryset = queryset.order_by('-price')
    elif sort_by == 'popular':
        queryset = queryset.order_by('-views_count')
    else:
        queryset = queryset.order_by('-created_at')

    # Featured properties for homepage
    featured_properties = Property.objects.filter(
        is_approved=True,
        featured=True,
        status__in=['available', 'under_offer'],
    )[:3]

    # Pagination: 9 per page
    paginator = Paginator(queryset, 9)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    filter_values = {
        key: request.GET.get(key, "")
        for key in (
            "q",
            "city",
            "area",
            "listing_type",
            "property_type",
            "bedrooms",
            "min_price",
            "max_price",
        )
    }
    search_form = SavedSearchForm(initial={
        **filter_values,
        "name": _saved_search_name(filter_values),
        "email_alerts": True,
    })
    favorite_property_ids = set()
    if request.user.is_authenticated:
        visible_ids = list(page_obj.object_list.values_list("pk", flat=True))
        if featured_properties:
            visible_ids.extend(featured_properties.values_list("pk", flat=True))
        favorite_property_ids = set(
            Favorite.objects.filter(
                user=request.user,
                property_id__in=visible_ids,
            ).values_list("property_id", flat=True)
        )

    context = {
        'page_obj': page_obj,
        'featured_properties': featured_properties,
        'total_count': queryset.count(),
        'selected_city': city,
        'selected_area': area,
        'selected_type': listing_type,
        'selected_property_type': property_type,
        'selected_bedrooms': bedrooms,
        'selected_min_price': min_price,
        'selected_max_price': max_price,
        'selected_sort': sort_by,
        'search_query': q,
        "saved_search_form": search_form,
        "favorite_property_ids": favorite_property_ids,
        "filter_values": filter_values,
        "has_active_filters": any(filter_values.values()),
    }
    return render(request, 'listings/property_list.html', context)


def _saved_search_name(criteria):
    location = criteria.get("area") or criteria.get("city")
    if location:
        return f"Properties in {location}"[:100]
    listing_type = criteria.get("listing_type")
    if listing_type:
        return f"{dict(Property.LISTING_TYPES).get(listing_type, 'Property')} search"
    return "My property search"


@login_required
@require_POST
def toggle_favorite(request, slug):
    property_obj = get_object_or_404(
        _public_property_queryset(),
        slug=slug,
    )
    favorite, created = Favorite.objects.get_or_create(
        user=request.user,
        property=property_obj,
    )
    if not created:
        favorite.delete()
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return JsonResponse({
            "saved": created,
            "property_id": property_obj.pk,
        })

    if created:
        messages.success(request, "Property saved to your list.")
    else:
        messages.success(request, "Property removed from your saved list.")

    next_url = request.POST.get("next", "")
    if next_url and url_has_allowed_host_and_scheme(
        next_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return redirect(next_url)
    return redirect("listings:saved_properties")


@login_required
def saved_properties(request):
    favorites = Favorite.objects.filter(
        user=request.user,
        property__is_approved=True,
    ).select_related("property").prefetch_related("property__images")
    return render(request, "listings/saved_properties.html", {
        "favorites": favorites,
    })


@login_required
@require_POST
def save_search(request):
    form = SavedSearchForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Please provide a valid filtered search to save.")
        return redirect("listings:property_list")

    criteria = form.get_criteria()
    filter_hash = hashlib.sha256(
        json.dumps(criteria, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    search, created = SavedSearch.objects.get_or_create(
        user=request.user,
        filter_hash=filter_hash,
        defaults={
            "name": form.cleaned_data["name"].strip(),
            "criteria": criteria,
            "email_alerts": form.cleaned_data["email_alerts"],
        },
    )
    if created:
        messages.success(request, "Search saved. You can manage it from Saved searches.")
    else:
        search.name = form.cleaned_data["name"].strip()
        search.criteria = criteria
        search.email_alerts = form.cleaned_data["email_alerts"]
        search.save(update_fields=["name", "criteria", "email_alerts"])
        messages.info(request, "Your saved search has been updated.")
    return redirect("listings:saved_searches")


@login_required
def saved_searches(request):
    searches = SavedSearch.objects.filter(user=request.user)
    for search in searches:
        search.query_string = urlencode(search.criteria)
    return render(request, "listings/saved_searches.html", {
        "saved_searches": searches,
    })


@login_required
@require_POST
def saved_search_action(request, search_id, action):
    saved_search = get_object_or_404(SavedSearch, pk=search_id, user=request.user)
    if action == "delete":
        saved_search.delete()
        messages.success(request, "Saved search deleted.")
    elif action == "toggle-alerts":
        saved_search.email_alerts = not saved_search.email_alerts
        saved_search.save(update_fields=["email_alerts"])
        messages.success(
            request,
            "Email alerts enabled." if saved_search.email_alerts else "Email alerts paused.",
        )
    elif action == "rename":
        name = request.POST.get("name", "").strip()
        if not name or len(name) > 100:
            messages.error(request, "Enter a search name between 1 and 100 characters.")
        else:
            saved_search.name = name
            saved_search.save(update_fields=["name"])
            messages.success(request, "Saved search renamed.")
    else:
        return redirect("listings:saved_searches")
    return redirect("listings:saved_searches")


def _send_saved_search_alerts(request, property_obj):
    if not property_obj.is_approved or property_obj.status not in {"available", "under_offer"}:
        return
    searches = SavedSearch.objects.filter(
        email_alerts=True,
        user__is_active=True,
    ).exclude(user__email="")
    property_url = request.build_absolute_uri(
        reverse("listings:property_detail", kwargs={"slug": property_obj.slug})
    )
    for saved_search in searches.iterator():
        if property_obj.agent_id and property_obj.agent.user_id == saved_search.user_id:
            continue
        matches = _apply_listing_filters(
            Property.objects.filter(pk=property_obj.pk),
            saved_search.criteria,
        ).exists()
        if not matches:
            continue
        try:
            sent_count = send_mail(
                subject=f"New property matching {saved_search.name}",
                message=(
                    f"A new property matches your saved search, {saved_search.name}:\n\n"
                    f"{property_obj.title}\n"
                    f"{property_obj.city}{f', {property_obj.area}' if property_obj.area else ''}\n"
                    f"Price: ₦{property_obj.price:,.0f}\n\n"
                    f"View listing: {property_url}\n\n"
                    "Manage your saved searches and email alerts from your EstateHub account."
                ),
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[saved_search.user.email],
                fail_silently=False,
            )
            if sent_count != 1:
                logger.error(
                    "Saved-search alert was not accepted for search %s",
                    saved_search.pk,
                )
        except (SMTPException, OSError):
            logger.exception(
                "Could not send alert for saved search %s",
                saved_search.pk,
            )


def property_detail_view(request, slug):
    """
    Detail view using friendly slugs: /properties/4-bedroom-terrace-duplex-works-layout-owerri/
    Counts one view per account or persistent anonymous visitor and renders the listing.
    """
    property_obj = get_object_or_404(Property, slug=slug, is_approved=True)

    visitor_id = None
    if request.method == 'GET':
        if request.user.is_authenticated:
            _view, created = PropertyView.objects.get_or_create(
                property=property_obj,
                user=request.user,
            )
        else:
            cookie_value = request.COOKIES.get("visitor_id")
            try:
                visitor_id = uuid.UUID(cookie_value) if cookie_value else uuid.uuid4()
            except (ValueError, TypeError, AttributeError):
                visitor_id = uuid.uuid4()

            visitor_view = PropertyView.objects.filter(
                property=property_obj,
                visitor_id=visitor_id,
            ).first()
            if visitor_view:
                created = False
            else:
                legacy_view = None
                session_key = request.session.session_key
                if session_key:
                    legacy_view = PropertyView.objects.filter(
                        property=property_obj,
                        user__isnull=True,
                        session_key=session_key,
                        visitor_id__isnull=True,
                    ).first()
                if legacy_view:
                    legacy_view.visitor_id = visitor_id
                    legacy_view.save(update_fields=["visitor_id"])
                    created = False
                else:
                    _view, created = PropertyView.objects.get_or_create(
                        property=property_obj,
                        visitor_id=visitor_id,
                        defaults={"user": None},
                    )

        if created:
            Property.objects.filter(pk=property_obj.pk).update(
                views_count=F('views_count') + 1
            )
            property_obj.refresh_from_db(fields=['views_count'])

    inquiry_form = InquiryForm()
    if request.method == 'POST':
        inquiry_form = InquiryForm(request.POST)
        if inquiry_form.is_valid():
            inquiry = inquiry_form.save(commit=False)
            inquiry.property = property_obj
            inquiry.save()
            messages.success(request, f"Your inquiry for {property_obj.title} was submitted! The agent has been notified.")
            return redirect('listings:property_detail', slug=property_obj.slug)

    # Similar properties in the same city or category
    similar_properties = Property.objects.filter(
        is_approved=True,
        status__in=['available', 'under_offer'],
        city=property_obj.city
    ).exclude(pk=property_obj.pk)[:3]

    context = {
        'property': property_obj,
        'inquiry_form': inquiry_form,
        "is_favorite": (
            request.user.is_authenticated
            and Favorite.objects.filter(user=request.user, property=property_obj).exists()
        ),
        'similar_properties': similar_properties,
        'whatsapp_url': property_obj.get_whatsapp_url(),
    }
    response = render(request, 'listings/property_detail.html', context)
    if visitor_id is not None:
        response.set_cookie(
            "visitor_id",
            str(visitor_id),
            max_age=60 * 60 * 24 * 365 * 5,
            httponly=True,
            samesite="Lax",
            secure=request.is_secure(),
        )
    return response


SITE_INFO_PAGES = {
    "about": {
        "title": "About EstateHub Naija",
        "intro": "A place to discover property listings and connect with agents in Nigeria.",
        "sections": [
            ("Browse with clearer details", "Search listings by city, neighborhood, property type, and sale or rental status. Listing details show the information supplied by the agent."),
            ("Connect directly", "Contact an agent about a property or arrange a viewing using the contact options shown on each listing."),
        ],
    },
    "verification": {
        "title": "Listing verification",
        "intro": "Understand what verification on EstateHub means before making a property decision.",
        "sections": [
            ("What the badge means", "A verified agent account confirms that an agent completed the platform's email-based onboarding. It is not a guarantee of ownership, title validity, property condition, or transaction outcome."),
            ("Do your own checks", "Independently verify the seller or agent, inspect the property, and have a qualified Nigerian property professional review title documents before paying or signing."),
        ],
    },
    "safety": {
        "title": "Property viewing and transaction safety",
        "intro": "Use these basic precautions when contacting agents or viewing a property.",
        "sections": [
            ("Before a viewing", "Arrange visits directly with the agent, tell someone where you are going, and avoid sending deposits before you have independently verified the property and the recipient."),
            ("Before paying", "Inspect the property and original title documents. Seek independent legal advice and confirm payment details in person through trusted channels."),
            ("Flag a concern", "Contact support if you notice a listing that appears inaccurate, duplicated, or unavailable."),
        ],
    },
    "contact": {
        "title": "Contact support",
        "intro": "Need help with EstateHub or want to flag a platform issue?",
        "sections": [
            ("WhatsApp help desk", "Message our help desk and include the listing link or a short description of the issue. Never send passwords, verification codes, or payment card details."),
        ],
    },
    "privacy": {
        "title": "Privacy notice",
        "intro": "This page summarizes how EstateHub features use the information you provide. Have this notice reviewed for your operating jurisdiction before production use.",
        "sections": [
            ("Account and listing information", "Account details support registration, login, and saved features. Listing and contact details are displayed to help visitors inquire about properties."),
            ("Saved searches", "Saved-search criteria are stored with your account and may be used to email matching listing alerts when you enable alerts."),
            ("Your choices", "You can remove saved properties, delete saved searches, pause their email alerts, or contact support about your account."),
        ],
    },
    "terms": {
        "title": "Terms of use",
        "intro": "These plain-language platform guidelines are not a substitute for reviewed legal terms.",
        "sections": [
            ("Use of listings", "Listing information is supplied by agents and may change. Confirm availability, price, location, and documents directly before relying on a listing."),
            ("No transaction guarantee", "EstateHub helps visitors discover listings and connect with agents; it does not guarantee property ownership, title, condition, agent conduct, or a successful transaction."),
            ("Responsible use", "Do not post misleading or unlawful content, misuse another person's information, or use the platform to facilitate fraud or harassment."),
        ],
    },
}


def site_info_page(request, slug):
    page = SITE_INFO_PAGES.get(slug)
    if page is None:
        from django.http import Http404
        raise Http404
    return render(request, "listings/site_info.html", {
        **page,
        "page_slug": slug,
    })


class AgentDashboardView(LoginRequiredMixin, ListView):
    """
    Dashboard for agents to view and manage their own listings and inquiries.
    """
    model = Property
    template_name = 'listings/agent_dashboard.html'
    context_object_name = 'agent_properties'

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated and not Agent.objects.filter(user=request.user).exists():
            return redirect('listings:agent_registration')
        return super().dispatch(request, *args, **kwargs)

    def get_agent(self):
        return Agent.objects.get(user=self.request.user)

    def get_tab(self):
        tab = self.request.GET.get('tab', 'active')
        return tab if tab in {'active', 'history', 'profile'} else 'active'

    def get_queryset(self):
        queryset = Property.objects.filter(agent=self.get_agent()).prefetch_related('images')
        if self.get_tab() == 'active':
            queryset = queryset.filter(status__in=['available', 'under_offer'])
        elif self.get_tab() == 'history':
            queryset = queryset.filter(status__in=['sold', 'rented'])
        else:
            return Property.objects.none()
        return queryset.order_by('-created_at')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        agent = self.get_agent()
        context['agent'] = agent
        context['selected_tab'] = self.get_tab()
        context['active_count'] = Property.objects.filter(
            agent=agent,
            status__in=['available', 'under_offer'],
        ).count()
        context['history_count'] = Property.objects.filter(
            agent=agent,
            status__in=['sold', 'rented'],
        ).count()
        return context


class PropertyCreateView(LoginRequiredMixin, CreateView):
    model = Property
    form_class = PropertyForm
    template_name = 'listings/property_form.html'
    success_url = reverse_lazy('listings:agent_dashboard')

    def form_valid(self, form):
        agent = get_object_or_404(Agent, user=self.request.user)
        form.instance.agent = agent
        with transaction.atomic():
            self.object = form.save()
            self._save_uploaded_images(form)
        _send_saved_search_alerts(self.request, self.object)
        messages.success(self.request, "Property listing added successfully!")
        return HttpResponseRedirect(self.get_success_url())

    def _save_uploaded_images(self, form):
        for image in form.cleaned_data.get('images', []):
            PropertyImage.objects.create(property=self.object, image=image)


class PropertyUpdateView(LoginRequiredMixin, UserPassesTestMixin, UpdateView):
    """
    Ownership check: An agent should never be able to edit another agent's listing.
    """
    model = Property
    form_class = PropertyForm
    template_name = 'listings/property_form.html'
    success_url = reverse_lazy('listings:agent_dashboard')

    def get_queryset(self):
        queryset = super().get_queryset()
        if self.request.user.is_superuser:
            return queryset
        return queryset.filter(
            agent__user=self.request.user,
            status__in=['available', 'under_offer'],
        )

    def test_func(self):
        prop = self.get_object()
        return self.request.user.is_superuser or (prop.agent and prop.agent.user == self.request.user)

    def form_valid(self, form):
        with transaction.atomic():
            self.object = form.save()
            for image in form.cleaned_data.get('images', []):
                PropertyImage.objects.create(property=self.object, image=image)
        messages.success(self.request, "Property listing updated successfully!")
        return HttpResponseRedirect(self.get_success_url())


class PropertyDeleteView(LoginRequiredMixin, UserPassesTestMixin, DeleteView):
    """
    Ownership check: Only the owning agent or admin can delete.
    """
    model = Property
    template_name = 'listings/property_confirm_delete.html'
    success_url = reverse_lazy('listings:agent_dashboard')

    def get_queryset(self):
        queryset = super().get_queryset()
        if self.request.user.is_superuser:
            return queryset
        return queryset.filter(
            agent__user=self.request.user,
            status__in=['available', 'under_offer'],
        )

    def test_func(self):
        prop = self.get_object()
        return self.request.user.is_superuser or (prop.agent and prop.agent.user == self.request.user)


@login_required
@require_POST
def property_mark_complete(request, slug):
    agent = get_object_or_404(Agent, user=request.user)
    property_obj = get_object_or_404(Property, slug=slug, agent=agent)
    completed_status = 'sold' if property_obj.listing_type == 'sale' else 'rented'
    updated = Property.objects.filter(
        pk=property_obj.pk,
        status__in=['available', 'under_offer'],
    ).update(status=completed_status, updated_at=timezone.now())

    if updated:
        messages.success(
            request,
            'Listing marked as sold.' if completed_status == 'sold' else 'Listing marked as rented.',
        )
    else:
        messages.error(request, 'This listing has already been completed and cannot be changed.')

    return redirect(f"{reverse('listings:agent_dashboard')}?tab=history")

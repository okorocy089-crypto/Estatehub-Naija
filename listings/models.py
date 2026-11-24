import builtins
import uuid
from django.core.validators import FileExtensionValidator
from django.db import models
from django.db.models import Q
from django.conf import settings
from django.contrib.auth.models import User
from django.utils.text import slugify
from urllib.parse import quote_plus

class Agent(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='agent_profile', null=True, blank=True)
    name = models.CharField(max_length=150)
    agency = models.CharField(max_length=150, default='Independent Realtor')
    phone = models.CharField(max_length=20)
    whatsapp = models.CharField(max_length=20, help_text="WhatsApp digits with country code (e.g. 2348030000000)")
    photo = models.ImageField(upload_to='agents/', blank=True, null=True)
    bio = models.TextField(blank=True)
    specialties = models.CharField(max_length=255, blank=True)
    verified = models.BooleanField(default=True)
    city = models.CharField(max_length=100, default='Owerri')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name} - {self.agency} ({self.city})"

    @property
    def clean_whatsapp(self):
        return "".join(filter(str.isdigit, self.whatsapp))


class Property(models.Model):
    LISTING_TYPES = [
        ("sale", "For Sale"),
        ("rent", "For Rent"),
    ]

    PROPERTY_TYPES = [
        ("residential", "Residential"),
        ("commercial", "Commercial"),
        ("luxury", "Luxury Homes"),
        ("land", "Land & Plots"),
        ("rentals", "Rentals"),
    ]

    RENT_PERIOD_CHOICES = [
        ("year", "Per year"),
        ("month", "Per month"),
        ("one_time", "One-time"),
    ]

    TITLE_DEED_CHOICES = [
        ("coo", "C of O"),
        ("governors_consent", "Governor's Consent"),
        ("deed_of_assignment", "Deed of Assignment"),
        ("gazette", "Gazette"),
        ("other", "Other"),
    ]

    STATUS_CHOICES = [
        ("available", "Available"),
        ("under_offer", "Under Offer"),
        ("sold", "Sold"),
        ("rented", "Rented"),
    ]

    FURNISHED_CHOICES = [
        ("Furnished", "Fully Furnished"),
        ("Semi-Furnished", "Semi-Furnished"),
        ("Unfurnished", "Unfurnished"),
    ]

    title = models.CharField(max_length=200)
    slug = models.SlugField(max_length=250, unique=True, blank=True)
    description = models.TextField()
    price = models.DecimalField(max_digits=14, decimal_places=2, help_text="Price in Nigerian Naira (₦)")
    listing_type = models.CharField(max_length=10, choices=LISTING_TYPES, default="sale")
    rent_period = models.CharField(max_length=10, choices=RENT_PERIOD_CHOICES, blank=True)
    price_negotiable = models.BooleanField(default=False)
    property_type = models.CharField(max_length=20, choices=PROPERTY_TYPES, default="residential")
    area = models.CharField(max_length=150, blank=True)
    bedrooms = models.PositiveIntegerField(null=True, blank=True, default=None)
    bathrooms = models.PositiveIntegerField(null=True, blank=True, default=None)
    floor_area_sqm = models.PositiveIntegerField(null=True, blank=True)
    plot_area_sqm = models.PositiveIntegerField(null=True, blank=True)
    address = models.CharField(max_length=255, blank=True)
    city = models.CharField(max_length=100, help_text="e.g. Owerri, Lagos, Abuja, Port Harcourt")
    state = models.CharField(max_length=100, default="Imo State")
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    title_deed = models.CharField(max_length=30, choices=TITLE_DEED_CHOICES, default="coo")
    title_deed_document = models.FileField(
        upload_to="property_documents/",
        blank=True,
        null=True,
        validators=[FileExtensionValidator(
            allowed_extensions=["pdf", "jpg", "jpeg", "png", "webp", "doc", "docx"]
        )],
    )
    furnished = models.CharField(max_length=20, choices=FURNISHED_CHOICES, blank=True, default="")
    amenities = models.TextField(blank=True, help_text="Comma-separated list of amenities")
    
    agent = models.ForeignKey(Agent, on_delete=models.SET_NULL, null=True, related_name="properties")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="available")
    featured = models.BooleanField(default=False, help_text="Display prominently in the homepage featured reel")
    is_approved = models.BooleanField(default=True, help_text="Admin approval verification check")
    views_count = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "Properties"
        ordering = ["-created_at"]

    def save(self, *args, **kwargs):
        if not self.slug:
            base_slug = slugify(self.title)
            slug = base_slug
            counter = 1
            while Property.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug = f"{base_slug}-{counter}"
                counter += 1
            self.slug = slug
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.title} - ₦{self.price:,.0f} ({self.city})"

    @property
    def amenities_list(self):
        if not self.amenities:
            return []
        return [item.strip() for item in self.amenities.split(",") if item.strip()]

    def get_whatsapp_url(self):
        if not self.agent or not self.agent.whatsapp:
            return "#"
        clean_number = "".join(filter(str.isdigit, self.agent.whatsapp))
        msg = f"Hello! I am interested in \"{self.title}\" in {self.city} listed for ₦{self.price:,.0f} on EstateHub and would like to arrange a viewing."
        return f"https://wa.me/{clean_number}?text={quote_plus(msg)}"


class PropertyImage(models.Model):
    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name="images")
    image = models.ImageField(upload_to="properties/")
    image_url = models.URLField(max_length=500, blank=True, help_text="External URL or CDN asset fallback")
    caption = models.CharField(max_length=150, blank=True)
    is_primary = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Image for {self.property.title}"

    @builtins.property
    def url(self):
        if self.image:
            return self.image.url
        return self.image_url


class PropertyView(models.Model):
    property = models.ForeignKey(
        Property,
        on_delete=models.CASCADE,
        related_name="visitor_views",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="property_views",
        null=True,
        blank=True,
    )
    session_key = models.CharField(max_length=40, blank=True, default="")
    visitor_id = models.UUIDField(null=True, blank=True, default=None)
    viewed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["property", "user"],
                condition=Q(user__isnull=False),
                name="unique_property_view_per_user",
            ),
            models.UniqueConstraint(
                fields=["property", "visitor_id"],
                condition=Q(visitor_id__isnull=False),
                name="unique_property_visitor",
            ),
        ]

    def __str__(self):
        viewer = self.user if self.user_id else self.visitor_id or self.session_key
        return f"View of {self.property} by {viewer}"


class Inquiry(models.Model):
    INQUIRY_TYPES = [
        ("general", "General Question"),
        ("viewing", "Schedule Site Viewing"),
        ("price_offer", "Make Price Offer"),
    ]

    STATUS_CHOICES = [
        ("new", "New Unhandled"),
        ("contacted", "Agent Contacted"),
        ("viewing_scheduled", "Inspection Scheduled"),
        ("closed", "Closed / Deal Finalized"),
    ]

    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name="inquiries")
    name = models.CharField(max_length=150)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=25)
    inquiry_type = models.CharField(max_length=20, choices=INQUIRY_TYPES, default="viewing")
    offer_amount = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    preferred_viewing_date = models.DateTimeField(null=True, blank=True)
    message = models.TextField()
    status = models.CharField(max_length=25, choices=STATUS_CHOICES, default="new")
    agent_notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name_plural = "Inquiries"
        ordering = ["-created_at"]

    def __str__(self):
        return f"Inquiry by {self.name} on {self.property.title}"


class Favorite(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="favorites")
    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name="favorited_by")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("user", "property")

    def __str__(self):
        return f"{self.user.username} saved {self.property.title}"


class SavedSearch(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="saved_property_searches",
    )
    name = models.CharField(max_length=100)
    criteria = models.JSONField(default=dict)
    filter_hash = models.CharField(max_length=64)
    email_alerts = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "filter_hash"],
                name="unique_saved_search_per_user",
            ),
        ]

    def __str__(self):
        return f"{self.name} ({self.user})"


class PasswordResetCode(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='password_reset_code',
    )
    code_hash = models.CharField(max_length=128)
    created_at = models.DateTimeField()
    expires_at = models.DateTimeField()
    attempts = models.PositiveSmallIntegerField(default=0)

    def __str__(self):
        return f"Password reset code for {self.user.email}"


class AgentRegistrationDraft(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='agent_registration_draft',
    )
    name = models.CharField(max_length=150)
    phone = models.CharField(max_length=20)
    photo = models.ImageField(upload_to='agents/pending/', blank=True, null=True)
    agency = models.CharField(max_length=150, blank=True)
    bio = models.TextField(blank=True)
    specialties = models.CharField(max_length=255, blank=True)
    city = models.CharField(max_length=100, blank=True)
    code_hash = models.CharField(max_length=128, blank=True)
    code_sent_at = models.DateTimeField(null=True, blank=True)
    code_expires_at = models.DateTimeField(null=True, blank=True)
    attempts = models.PositiveSmallIntegerField(default=0)
    resend_count = models.PositiveSmallIntegerField(default=0)
    email_verified = models.BooleanField(default=False)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Pending agent registration for {self.user}"

from django.contrib import admin
from .models import (
    Agent,
    Favorite,
    Inquiry,
    Property,
    PropertyImage,
    SavedSearch,
)

class PropertyImageInline(admin.TabularInline):
    model = PropertyImage
    extra = 2

@admin.register(Property)
class PropertyAdmin(admin.ModelAdmin):
    list_display = (
        'title',
        'city',
        'area',
        'formatted_price',
        'listing_type',
        'rent_period',
        'property_type',
        'price_negotiable',
        'status',
        'featured',
        'is_approved',
        'agent',
        'views_count',
        'created_at'
    )
    list_filter = (
        'city',
        'area',
        'listing_type',
        'rent_period',
        'property_type',
        'price_negotiable',
        'status',
        'featured',
        'is_approved',
        'created_at'
    )
    search_fields = ('title', 'address', 'area', 'city', 'description')
    prepopulated_fields = {'slug': ('title',)}
    list_editable = ('status', 'featured', 'is_approved')
    inlines = [PropertyImageInline]
    actions = ['mark_featured', 'unmark_featured', 'approve_listings']

    def formatted_price(self, obj):
        return f"₦{obj.price:,.0f}"
    formatted_price.short_description = "Price (₦)"

    def mark_featured(self, request, queryset):
        queryset.update(featured=True)
    mark_featured.short_description = "Feature selected properties on homepage"

    def unmark_featured(self, request, queryset):
        queryset.update(featured=False)
    unmark_featured.short_description = "Remove from featured"

    def approve_listings(self, request, queryset):
        queryset.update(is_approved=True)
    approve_listings.short_description = "Approve verified listings"


@admin.register(Agent)
class AgentAdmin(admin.ModelAdmin):
    list_display = ('name', 'agency', 'phone', 'whatsapp', 'city', 'verified')
    list_filter = ('city', 'verified')
    search_fields = ('name', 'agency', 'phone', 'whatsapp')


@admin.register(Inquiry)
class InquiryAdmin(admin.ModelAdmin):
    list_display = (
        'name',
        'phone',
        'property',
        'inquiry_type',
        'status',
        'preferred_viewing_date',
        'created_at'
    )
    list_filter = ('status', 'inquiry_type', 'created_at')
    search_fields = ('name', 'phone', 'email', 'property__title')
    list_editable = ('status',)


@admin.register(Favorite)
class FavoriteAdmin(admin.ModelAdmin):
    list_display = ('user', 'property', 'created_at')
    search_fields = ('user__username', 'property__title')


@admin.register(SavedSearch)
class SavedSearchAdmin(admin.ModelAdmin):
    list_display = ('name', 'user', 'email_alerts', 'created_at')
    list_filter = ('email_alerts', 'created_at')
    search_fields = ('name', 'user__email')
    readonly_fields = ('filter_hash', 'created_at')

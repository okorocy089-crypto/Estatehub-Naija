import re

from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import AuthenticationForm, SetPasswordForm
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import UploadedFile
from django.forms.widgets import ClearableFileInput

from .models import Agent, Inquiry, Property


AGENT_CITY_REGION_CHOICES = (
    ('Imo', 'Imo'),
    ('Lagos', 'Lagos'),
    ('Abuja', 'Abuja'),
    ('Port Harcourt', 'Port Harcourt'),
)

AMENITY_CHOICES = (
    ('Generator', 'Generator'),
    ('Borehole', 'Borehole'),
    ('24/7 Security', '24/7 Security'),
    ('Swimming Pool', 'Swimming Pool'),
    ('Parking', 'Parking'),
    ('Air Conditioning', 'Air Conditioning'),
    ('Elevator', 'Elevator'),
    ('En-suite Bedrooms', 'En-suite Bedrooms'),
    ('Fitted Kitchen', 'Fitted Kitchen'),
    ('Internet', 'Internet'),
    ('CCTV', 'CCTV'),
    ('Solar Power', 'Solar Power'),
)


class CommaSeparatedDecimalField(forms.DecimalField):
    def to_python(self, value):
        if isinstance(value, str):
            value = value.replace(',', '').strip()
        return super().to_python(value)


class MultipleImageInput(ClearableFileInput):
    allow_multiple_selected = True


class MultipleImageField(forms.ImageField):
    widget = MultipleImageInput

    def clean(self, data, initial=None):
        if data in self.empty_values:
            return []
        if not isinstance(data, (list, tuple)):
            data = [data]
        return [super().clean(image, None) for image in data]


class BuyerRegistrationForm(forms.Form):
    first_name = forms.CharField(
        label='First Name',
        max_length=150,
        widget=forms.TextInput(attrs={
            'class': 'form-input',
            'autocomplete': 'given-name',
        }),
    )
    last_name = forms.CharField(
        label='Last Name',
        max_length=150,
        widget=forms.TextInput(attrs={
            'class': 'form-input',
            'autocomplete': 'family-name',
        }),
    )
    email = forms.EmailField(
        label='Email address',
        max_length=150,
        widget=forms.EmailInput(attrs={
            'class': 'form-input',
            'autocomplete': 'email',
        }),
    )
    password = forms.CharField(
        label='Password',
        widget=forms.PasswordInput(attrs={
            'class': 'form-input',
            'autocomplete': 'new-password',
        }),
    )

    def clean_email(self):
        email = self.cleaned_data['email'].strip().lower()
        User = get_user_model()
        username_lookup = {f'{User.USERNAME_FIELD}__iexact': email}
        if User.objects.filter(email__iexact=email).exists() or User.objects.filter(
            **username_lookup
        ).exists():
            raise ValidationError(
                'An account with this email already exists. Please log in.'
            )
        return email

    def clean_password(self):
        password = self.cleaned_data['password']
        User = get_user_model()
        user = User(
            email=self.cleaned_data.get('email', ''),
            first_name=self.cleaned_data.get('first_name', ''),
            last_name=self.cleaned_data.get('last_name', ''),
        )
        validate_password(password, user=user)
        return password


class EmailAuthenticationForm(AuthenticationForm):
    username = forms.EmailField(
        label='Email',
        max_length=320,
        widget=forms.EmailInput(attrs={
            'class': 'form-input',
            'autofocus': True,
            'autocomplete': 'email',
        }),
    )
    password = forms.CharField(
        label='Password',
        strip=False,
        widget=forms.PasswordInput(attrs={
            'class': 'form-input',
            'autocomplete': 'current-password',
        }),
    )

    def clean_username(self):
        return self.cleaned_data['username'].strip().lower()


class PasswordResetRequestForm(forms.Form):
    email = forms.EmailField(
        label='Email address',
        max_length=150,
        widget=forms.EmailInput(attrs={
            'class': 'form-input',
            'autocomplete': 'email',
            'autofocus': True,
        }),
    )

    def clean_email(self):
        return self.cleaned_data['email'].strip().lower()


class PasswordResetCodeForm(forms.Form):
    code = forms.RegexField(
        regex=r'^[0-9]{6}$',
        label='Verification code',
        widget=forms.TextInput(attrs={
            'class': 'form-input',
            'autocomplete': 'one-time-code',
            'inputmode': 'numeric',
            'pattern': '[0-9]{6}',
            'maxlength': '6',
            'autofocus': True,
        }),
    )


class BuyerSetPasswordForm(SetPasswordForm):
    new_password1 = forms.CharField(
        label='New password',
        widget=forms.PasswordInput(attrs={
            'class': 'form-input',
            'autocomplete': 'new-password',
        }),
    )
    new_password2 = forms.CharField(
        label='Confirm new password',
        widget=forms.PasswordInput(attrs={
            'class': 'form-input',
            'autocomplete': 'new-password',
        }),
    )


class GoogleProfileCompletionForm(forms.Form):
    first_name = forms.CharField(
        label='First Name',
        max_length=150,
        widget=forms.TextInput(attrs={
            'class': 'form-input',
            'autocomplete': 'given-name',
        }),
    )
    last_name = forms.CharField(
        label='Last Name',
        max_length=150,
        widget=forms.TextInput(attrs={
            'class': 'form-input',
            'autocomplete': 'family-name',
        }),
    )


class AgentIdentityForm(forms.Form):
    name = forms.CharField(
        label='Agent name',
        max_length=150,
        widget=forms.TextInput(attrs={
            'class': 'form-input',
            'autocomplete': 'name',
        }),
    )
    phone = forms.CharField(
        label='Nigerian mobile number',
        max_length=24,
        widget=forms.TelInput(attrs={
            'class': 'form-input',
            'autocomplete': 'tel',
            'placeholder': '0803 123 4567',
        }),
    )
    photo = forms.ImageField(
        label='Agent profile photo',
        widget=forms.ClearableFileInput(attrs={
            'class': 'form-input',
            'accept': 'image/*',
        }),
    )

    def clean_phone(self):
        digits = ''.join(
            character
            for character in self.cleaned_data['phone']
            if character.isdigit()
        )
        if digits.startswith('234'):
            digits = digits[3:]
        if not digits.startswith('0'):
            digits = f'0{digits}'
        if not re.fullmatch(r'0(?:70|80|81|90|91)\d{8}', digits):
            raise ValidationError(
                'Enter a valid Nigerian mobile number, such as 0803 123 4567.'
            )

        phone = f'+234{digits[1:]}'
        if Agent.objects.filter(phone=phone).exists():
            raise ValidationError(
                'This phone number is already linked to an agent account!'
            )
        return phone


class AgentEmailVerificationForm(forms.Form):
    code = forms.RegexField(
        regex=r'^[0-9]{6}$',
        label='6-digit verification code',
        widget=forms.TextInput(attrs={
            'class': 'form-input',
            'inputmode': 'numeric',
            'autocomplete': 'one-time-code',
            'pattern': '[0-9]{6}',
            'maxlength': '6',
            'placeholder': '123456',
            'autofocus': True,
        }),
    )


class AgentDetailsForm(forms.Form):
    agency = forms.CharField(
        label='Company / Agency name',
        max_length=150,
        widget=forms.TextInput(attrs={
            'class': 'form-input',
        }),
    )
    bio = forms.CharField(
        label='Agent bio',
        max_length=3000,
        widget=forms.Textarea(attrs={
            'class': 'form-textarea',
            'rows': 5,
        }),
    )
    specialties = forms.MultipleChoiceField(
        choices=(
            ('Residential', 'Residential'),
            ('Commercial', 'Commercial'),
            ('Luxury Homes', 'Luxury Homes'),
            ('Land', 'Land'),
            ('Rentals', 'Rentals'),
        ),
        widget=forms.CheckboxSelectMultiple(attrs={
            'class': 'agent-specialties',
        }),
    )
    city = forms.ChoiceField(
        label='Primary city / region',
        choices=AGENT_CITY_REGION_CHOICES,
        widget=forms.Select(attrs={
            'class': 'form-select',
        }),
    )


class PropertyForm(forms.ModelForm):
    title = forms.CharField(
        min_length=10,
        max_length=200,
        widget=forms.TextInput(attrs={
            'class': 'form-input',
            'placeholder': 'e.g. 4-Bedroom Detached Duplex in Works Layout',
            'data-listing-text': 'title',
        }),
    )
    description = forms.CharField(
        min_length=40,
        max_length=5000,
        widget=forms.Textarea(attrs={
            'class': 'form-textarea property-description-input',
            'rows': 4,
            'data-listing-text': 'description',
        }),
    )
    price = CommaSeparatedDecimalField(
        max_digits=14,
        decimal_places=2,
        min_value=1,
        max_value=999999999999.99,
        widget=forms.TextInput(attrs={
            'class': 'form-input',
            'placeholder': '50,000,000',
            'inputmode': 'decimal',
            'data-price-input': '',
            'min': '1',
            'max': '999999999999.99',
        }),
    )
    images = MultipleImageField(
        required=False,
        label='Property photos',
        widget=MultipleImageInput(attrs={
            'class': 'form-input',
            'accept': 'image/*',
            'data-property-photos': '',
        }),
    )
    title_deed_document = forms.FileField(
        required=False,
        validators=Property._meta.get_field('title_deed_document').validators,
        widget=forms.FileInput(attrs={
            'class': 'deed-document-input',
            'accept': '.pdf,.jpg,.jpeg,.png,.webp,.doc,.docx',
            'data-deed-document': '',
        }),
    )
    bedrooms = forms.IntegerField(
        required=False,
        min_value=1,
        max_value=50,
        widget=forms.NumberInput(attrs={
            'class': 'form-input',
            'min': 1,
            'max': 50,
        }),
    )
    bathrooms = forms.IntegerField(
        required=False,
        min_value=1,
        max_value=50,
        widget=forms.NumberInput(attrs={
            'class': 'form-input',
            'min': 1,
            'max': 50,
        }),
    )
    floor_area_sqm = forms.IntegerField(
        required=False,
        min_value=1,
        max_value=1000000,
        widget=forms.NumberInput(attrs={
            'class': 'form-input',
            'placeholder': 'e.g. 250',
            'min': 1,
            'max': 1000000,
        }),
    )
    plot_area_sqm = forms.IntegerField(
        required=False,
        min_value=1,
        max_value=1000000,
        widget=forms.NumberInput(attrs={
            'class': 'form-input',
            'placeholder': 'e.g. 500',
            'min': 1,
            'max': 1000000,
        }),
    )
    property_type = forms.ChoiceField(
        choices=Property.PROPERTY_TYPES,
        widget=forms.Select(attrs={
            'class': 'form-select',
            'data-property-type': '',
        }),
    )
    title_deed = forms.ChoiceField(
        choices=Property.TITLE_DEED_CHOICES,
        widget=forms.Select(attrs={
            'class': 'form-select',
        }),
    )
    furnished = forms.ChoiceField(
        required=False,
        choices=(('', '- Select an option -'), *Property.FURNISHED_CHOICES),
        label='Furnished',
        widget=forms.Select(attrs={
            'class': 'form-select',
        }),
    )
    amenities = forms.MultipleChoiceField(
        required=False,
        choices=AMENITY_CHOICES,
        widget=forms.CheckboxSelectMultiple(attrs={
            'class': 'property-amenities',
        }),
    )
    rent_period = forms.ChoiceField(
        required=False,
        choices=(('', 'Select rent period'), *Property.RENT_PERIOD_CHOICES),
        widget=forms.Select(attrs={
            'class': 'form-select',
            'data-rent-period': '',
        }),
    )
    price_negotiable = forms.BooleanField(
        required=False,
        label='Price negotiable',
        widget=forms.CheckboxInput(attrs={
            'class': 'form-checkbox',
        }),
    )
    other_amenities = forms.CharField(
        required=False,
        max_length=500,
        label='Other amenities',
        widget=forms.TextInput(attrs={
            'class': 'form-input',
            'placeholder': 'Add another amenity',
        }),
    )

    class Meta:
        model = Property
        fields = [
            'title',
            'description',
            'price',
            'images',
            'listing_type',
            'property_type',
            'bedrooms',
            'bathrooms',
            'floor_area_sqm',
            'plot_area_sqm',
            'area',
            'address',
            'city',
            'state',
            'title_deed',
            'title_deed_document',
            'furnished',
            'amenities',
            'other_amenities',
            'rent_period',
            'price_negotiable',
        ]
        widgets = {
            'listing_type': forms.Select(attrs={
                'class': 'form-select',
            }),
            'area': forms.TextInput(attrs={
                'class': 'form-input',
                'placeholder': 'e.g. Works Layout',
            }),
            'address': forms.TextInput(attrs={
                'class': 'form-input',
                'placeholder': '',
            }),
            'city': forms.TextInput(attrs={
                'class': 'form-input',
                'placeholder': 'Owerri',
            }),
            'state': forms.TextInput(attrs={
                'class': 'form-input',
                'placeholder': 'Imo State',
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            self.initial['amenities'] = self.instance.amenities_list
        for field_name in ('area', 'city', 'state'):
            self.fields[field_name].widget.attrs['data-listing-text'] = 'location'
        self.fields['address'].widget.attrs['data-listing-text'] = 'address'
        self.fields['other_amenities'].widget.attrs['data-listing-text'] = 'amenities'

    @staticmethod
    def _has_meaningful_text(value, min_letters=3, letter_ratio=0.4):
        letters = sum(character.isalpha() for character in value)
        visible_characters = sum(not character.isspace() for character in value)
        return (
            letters >= min_letters
            and visible_characters > 0
            and letters / visible_characters >= letter_ratio
            and not re.search(r'(.)\1{5,}', value, re.IGNORECASE)
        )

    def clean_title(self):
        title = ' '.join(self.cleaned_data['title'].split())
        letter_count = sum(character.isalpha() for character in title)
        vowel_count = sum(character.lower() in 'aeiouy' for character in title)
        if (
            not re.fullmatch(r"[\w\s.,'&()/\-]+", title)
            or not self._has_meaningful_text(title, min_letters=5)
            or vowel_count / max(letter_count, 1) < 0.15
        ):
            raise ValidationError('Enter a meaningful property title.')
        if len(title.split()) < 2:
            raise ValidationError('Include at least two words in the property title.')
        return title

    def clean_description(self):
        description = self.cleaned_data['description'].strip()
        words = re.findall(r'\b[\w\'-]+\b', description)
        if len(words) < 6 or not self._has_meaningful_text(
            description,
            min_letters=25,
            letter_ratio=0.55,
        ) or sum(character.lower() in 'aeiou' for character in description) / max(
            sum(character.isalpha() for character in description),
            1,
        ) < 0.2:
            raise ValidationError(
                'Enter a clear property description with at least six meaningful words.'
            )
        return description

    def clean_area(self):
        return self._clean_location_text('area')

    def clean_city(self):
        return self._clean_location_text('city')

    def clean_state(self):
        return self._clean_location_text('state')

    def _clean_location_text(self, field_name):
        value = ' '.join(self.cleaned_data[field_name].split())
        if not value and not self.fields[field_name].required:
            return value
        if not re.fullmatch(r"[A-Za-zÀ-ÖØ-öø-ÿ\s.'-]+", value):
            raise ValidationError('Use a valid place name with letters only.')
        if not self._has_meaningful_text(value, min_letters=2, letter_ratio=0.5):
            raise ValidationError('Enter a valid place name.')
        return value

    def clean_address(self):
        address = ' '.join(self.cleaned_data.get('address', '').split())
        if address and (
            not re.fullmatch(r"[A-Za-zÀ-ÖØ-öø-ÿ0-9\s,.'/#()-]+", address)
            or not self._has_meaningful_text(address, min_letters=3, letter_ratio=0.2)
        ):
            raise ValidationError('Enter a valid street address.')
        return address

    def clean_other_amenities(self):
        value = self.cleaned_data.get('other_amenities', '')
        items = [item.strip() for item in re.split(r'[,;\n]', value) if item.strip()]
        if any(
            len(item) > 60 or not self._has_meaningful_text(
                item,
                min_letters=2,
                letter_ratio=0.35,
            )
            for item in items
        ):
            raise ValidationError('Enter valid amenity names, separated by commas.')
        return ', '.join(items)

    def clean_title_deed_document(self):
        document = self.cleaned_data.get('title_deed_document')
        if isinstance(document, UploadedFile) and document.size > 10 * 1024 * 1024:
            raise ValidationError('The title deed document must be 10 MB or smaller.')
        return document

    def clean(self):
        cleaned_data = super().clean()
        images = cleaned_data.get('images') or []
        current_image_count = (
            self.instance.images.count()
            if self.instance and self.instance.pk
            else 0
        )
        total_image_count = current_image_count + len(images)
        if total_image_count > 10:
            self.add_error('images', 'You have reached the maximum upload limit (10).')
        elif total_image_count < 6:
            self.add_error(
                'images',
                f'Upload at least {6 - total_image_count} more to continue.',
            )

        listing_type = cleaned_data.get('listing_type')
        if listing_type == 'rent' and not cleaned_data.get('rent_period'):
            self.add_error(
                'rent_period',
                'Select whether rent is per year, per month, or one-time.',
            )
        elif listing_type == 'sale':
            cleaned_data['rent_period'] = ''

        title_deed = cleaned_data.get('title_deed')
        document = cleaned_data.get('title_deed_document')
        has_existing_document = bool(
            self.instance
            and self.instance.pk
            and self.instance.title_deed_document
        )
        deed_changed = bool(
            self.instance
            and self.instance.pk
            and title_deed != self.instance.title_deed
        )
        if not document and (not has_existing_document or deed_changed):
            self.add_error(
                'title_deed_document',
                'Upload the document that matches the selected title deed.',
            )

        if cleaned_data.get('property_type') == 'land':
            for field_name, empty_value in (
                ('bedrooms', None),
                ('bathrooms', None),
                ('furnished', ''),
            ):
                cleaned_data[field_name] = empty_value
                self.errors.pop(field_name, None)

        selected_amenities = cleaned_data.get('amenities') or []
        other_amenities = cleaned_data.get('other_amenities') or ''
        additional_amenities = [
            item.strip()
            for item in re.split(r'[,;\n]', other_amenities)
            if item.strip()
        ]
        cleaned_data['amenities'] = ', '.join(dict.fromkeys(
            [*selected_amenities, *additional_amenities]
        ))
        return cleaned_data


class InquiryForm(forms.ModelForm):
    offer_amount = CommaSeparatedDecimalField(
        required=False,
        max_digits=14,
        decimal_places=2,
        widget=forms.TextInput(attrs={
            'class': 'form-input',
            'placeholder': 'Enter your offer',
            'inputmode': 'decimal',
            'data-price-input': '',
        }),
    )

    class Meta:
        model = Inquiry
        fields = [
            'name',
            'email',
            'phone',
            'inquiry_type',
            'offer_amount',
            'preferred_viewing_date',
            'message',
        ]
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-input',
                'placeholder': 'Your Full Name',
                'required': True,
            }),
            'email': forms.EmailInput(attrs={
                'class': 'form-input',
                'placeholder': 'your.email@example.com',
            }),
            'phone': forms.TextInput(attrs={
                'class': 'form-input',
                'placeholder': '+234 803 000 0000',
                'required': True,
            }),
            'inquiry_type': forms.Select(attrs={
                'class': 'form-select',
            }),
            'preferred_viewing_date': forms.DateTimeInput(
                attrs={
                    'class': 'form-input',
                    'type': 'datetime-local',
                },
                format='%Y-%m-%dT%H:%M',
            ),
            'message': forms.Textarea(attrs={
                'class': 'form-textarea',
                'rows': 4,
            }),
        }


class SavedSearchForm(forms.Form):
    name = forms.CharField(
        max_length=100,
        widget=forms.TextInput(attrs={"class": "form-input", "maxlength": 100}),
    )
    q = forms.CharField(required=False, max_length=100)
    city = forms.CharField(required=False, max_length=100)
    area = forms.CharField(required=False, max_length=150)
    listing_type = forms.ChoiceField(
        required=False,
        choices=(("", "Any"), *Property.LISTING_TYPES),
    )
    property_type = forms.ChoiceField(
        required=False,
        choices=(("", "Any"), *Property.PROPERTY_TYPES),
    )
    bedrooms = forms.IntegerField(required=False, min_value=1, max_value=50)
    min_price = CommaSeparatedDecimalField(
        required=False,
        min_value=0,
        max_digits=14,
        decimal_places=2,
    )
    max_price = CommaSeparatedDecimalField(
        required=False,
        min_value=0,
        max_digits=14,
        decimal_places=2,
    )
    email_alerts = forms.BooleanField(required=False, initial=True)

    def clean(self):
        cleaned_data = super().clean()
        min_price = cleaned_data.get("min_price")
        max_price = cleaned_data.get("max_price")
        if min_price is not None and max_price is not None and min_price > max_price:
            self.add_error("max_price", "Maximum price must be greater than minimum price.")
        filter_names = (
            "q",
            "city",
            "area",
            "listing_type",
            "property_type",
            "bedrooms",
            "min_price",
            "max_price",
        )
        if not any(cleaned_data.get(name) not in (None, "") for name in filter_names):
            raise ValidationError("Add at least one search filter before saving.")
        return cleaned_data

    def get_criteria(self):
        if not self.is_valid():
            raise ValueError("Saved-search criteria are only available for valid input.")
        return {
            key: str(self.cleaned_data[key]) if self.cleaned_data.get(key) is not None else ""
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
            if self.cleaned_data.get(key) not in (None, "")
        }

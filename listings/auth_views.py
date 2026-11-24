import json
import logging
import secrets
from datetime import timedelta
from smtplib import SMTPException

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import authenticate, get_user_model, login, logout
from django.contrib.auth.hashers import check_password, make_password
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.mail import send_mail
from django.core.validators import validate_email
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_POST
from .forms import (
    AgentEmailVerificationForm,
    AgentDetailsForm,
    AgentIdentityForm,
    BuyerRegistrationForm,
    BuyerSetPasswordForm,
    EmailAuthenticationForm,
    GoogleProfileCompletionForm,
    PasswordResetCodeForm,
    PasswordResetRequestForm,
)
from .models import Agent, AgentRegistrationDraft, PasswordResetCode

logger = logging.getLogger(__name__)

PASSWORD_RESET_CODE_TTL = timedelta(minutes=10)
PASSWORD_RESET_RESEND_DELAY = timedelta(minutes=1)
PASSWORD_RESET_SESSION_TTL = 10 * 60
PASSWORD_RESET_MAX_ATTEMPTS = 5
AGENT_CODE_TTL = timedelta(minutes=10)
AGENT_CODE_RESEND_DELAY = timedelta(seconds=60)
AGENT_CODE_MAX_ATTEMPTS = 5
AGENT_CODE_MAX_RESENDS = 3
AGENT_CODE_SEND_DELAY = timedelta(minutes=1)


def _safe_next_url(request, next_url):
    if next_url and url_has_allowed_host_and_scheme(
        next_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return next_url
    return reverse('listings:property_list')


def register_page(request):
    if request.user.is_authenticated:
        return redirect('listings:property_list')

    form = BuyerRegistrationForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        User = get_user_model()
        email = form.cleaned_data['email']
        user = User.objects.create_user(
            username=email,
            email=email,
            first_name=form.cleaned_data['first_name'],
            last_name=form.cleaned_data['last_name'],
            password=form.cleaned_data['password'],
        )
        login(request, user, backend='django.contrib.auth.backends.ModelBackend')
        return redirect(_safe_next_url(request, request.POST.get('next')))

    return render(request, 'listings/auth/register.html', {
        'form': form,
        'next': request.POST.get('next') or request.GET.get('next', ''),
        'google_client_id': settings.GOOGLE_CLIENT_ID,
    })


def login_page(request):
    if request.user.is_authenticated:
        return redirect('listings:property_list')

    form = EmailAuthenticationForm(request, data=request.POST or None)
    if request.method == 'POST' and form.is_valid():
        login(request, form.get_user())
        return redirect(_safe_next_url(request, request.POST.get('next')))

    return render(request, 'listings/auth/login.html', {
        'form': form,
        'next': request.POST.get('next') or request.GET.get('next', ''),
        'google_client_id': settings.GOOGLE_CLIENT_ID,
    })


def _agent_registration_login_redirect():
    register_url = reverse('listings:auth_register')
    agent_url = reverse('listings:agent_registration')
    return f'{register_url}?next={agent_url}'


def _send_agent_verification_email(request, email, code):
    try:
        sent_count = send_mail(
            subject='Verify your EstateHub agent account',
            message=(
                f'Your EstateHub agent verification code is {code}.\n\n'
                'This code expires in 10 minutes. If you did not request this, '
                'you can ignore this email.'
            ),
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[email],
            fail_silently=False,
        )
        if sent_count == 1:
            return True
        logger.error('Agent verification email was not accepted by the email backend')
    except (SMTPException, OSError):
        logger.exception('Could not send agent verification email')

    messages.error(
        request,
        'We could not send your email verification code right now. Please try again later.',
    )
    return False


def _agent_verification_code_sent(request, draft, code, count_resend=False):
    if not _send_agent_verification_email(request, request.user.email, code):
        return False

    now = timezone.now()
    draft.code_hash = make_password(code)
    draft.code_sent_at = now
    draft.code_expires_at = now + AGENT_CODE_TTL
    if count_resend:
        draft.resend_count += 1
    draft.save(update_fields=[
        'code_hash',
        'code_sent_at',
        'code_expires_at',
        'attempts',
        'resend_count',
        'updated_at',
    ])
    return True


def agent_registration(request):
    if not request.user.is_authenticated:
        return redirect(_agent_registration_login_redirect())
    if Agent.objects.filter(user=request.user).exists():
        return redirect('listings:agent_dashboard')

    draft = AgentRegistrationDraft.objects.filter(user=request.user).first()
    form = AgentIdentityForm(
        request.POST or None,
        request.FILES or None,
        initial={
            'name': draft.name if draft else '',
            'phone': draft.phone if draft else '',
        },
    )
    if request.method == 'POST' and form.is_valid():
        phone = form.cleaned_data['phone']
        if Agent.objects.filter(phone=phone).exclude(user=request.user).exists():
            form.add_error('phone', 'This phone number is already linked to an agent account.')
        else:
            now = timezone.now()
            restarting_pending_draft = bool(draft and draft.code_sent_at)
            if restarting_pending_draft and draft.attempts >= AGENT_CODE_MAX_ATTEMPTS:
                form.add_error(None, 'Too many incorrect attempts. Contact support to continue agent registration.')
            elif restarting_pending_draft and draft.resend_count >= AGENT_CODE_MAX_RESENDS:
                form.add_error(None, 'You have requested the maximum number of codes. Contact support to continue.')
            elif restarting_pending_draft and now - draft.code_sent_at < AGENT_CODE_SEND_DELAY:
                form.add_error(None, 'Please wait one minute before requesting another verification code.')
            else:
                draft, _ = AgentRegistrationDraft.objects.get_or_create(
                    user=request.user,
                    defaults={'name': form.cleaned_data['name'], 'phone': phone},
                )
                draft.name = form.cleaned_data['name']
                draft.phone = phone
                if form.cleaned_data['photo']:
                    draft.photo = form.cleaned_data['photo']
                draft.email_verified = False
                draft.code_hash = ''
                draft.code_expires_at = None
                if not restarting_pending_draft:
                    draft.attempts = 0
                    draft.resend_count = 0
                draft.save()

                code = f'{secrets.randbelow(1_000_000):06d}'
                if _agent_verification_code_sent(
                    request,
                    draft,
                    code,
                    restarting_pending_draft,
                ):
                    return redirect('listings:agent_email_verify')

    return render(request, 'listings/agents/registration.html', {'form': form})


def agent_email_verify(request):
    if not request.user.is_authenticated:
        return redirect(_agent_registration_login_redirect())
    if Agent.objects.filter(user=request.user).exists():
        return redirect('listings:agent_dashboard')

    draft = AgentRegistrationDraft.objects.filter(user=request.user).first()
    if not draft:
        messages.info(request, 'Start your agent registration to verify your email address.')
        return redirect('listings:agent_registration')
    if draft.email_verified:
        return redirect('listings:agent_details')
    if not draft.code_hash or not draft.code_sent_at or not draft.code_expires_at:
        messages.info(request, 'Request a verification code to continue.')
        return redirect('listings:agent_registration')

    form = AgentEmailVerificationForm(request.POST or None)
    if request.method == 'POST' and request.POST.get('action') == 'resend':
        if draft.attempts >= AGENT_CODE_MAX_ATTEMPTS:
            messages.error(request, 'Too many incorrect attempts. Restart agent registration to request a new code.')
            return redirect('listings:agent_registration')
        if draft.resend_count >= AGENT_CODE_MAX_RESENDS:
            messages.error(request, 'You have requested the maximum number of codes. Restart agent registration to try again.')
            return redirect('listings:agent_registration')
        now = timezone.now()
        if now - draft.code_sent_at < AGENT_CODE_SEND_DELAY:
            messages.info(request, 'Please wait one minute before requesting another code.')
        else:
            code = f'{secrets.randbelow(1_000_000):06d}'
            if _agent_verification_code_sent(request, draft, code, count_resend=True):
                messages.success(request, 'A new verification code has been sent.')
        return redirect('listings:agent_email_verify')

    if request.method == 'POST' and form.is_valid():
        with transaction.atomic():
            draft = AgentRegistrationDraft.objects.select_for_update().get(pk=draft.pk)
            now = timezone.now()
            if draft.attempts >= AGENT_CODE_MAX_ATTEMPTS:
                form.add_error(None, 'Too many incorrect attempts. Restart agent registration to request a new code.')
            elif not draft.code_expires_at or draft.code_expires_at <= now:
                form.add_error(None, 'That code has expired. Request a new verification code.')
            elif check_password(form.cleaned_data['code'], draft.code_hash):
                draft.email_verified = True
                draft.code_hash = ''
                draft.code_expires_at = None
                draft.save(update_fields=[
                    'email_verified',
                    'code_hash',
                    'code_expires_at',
                    'updated_at',
                ])
                return redirect('listings:agent_details')
            else:
                draft.attempts += 1
                draft.save(update_fields=['attempts', 'updated_at'])
                form.add_error(None, 'That verification code is incorrect.')

    return render(request, 'listings/agents/verify_email.html', {
        'form': form,
        'email': draft.user.email,
        'email_backend_is_console': (
            settings.EMAIL_BACKEND == 'django.core.mail.backends.console.EmailBackend'
        ),
        'resend_available_at': draft.code_sent_at + AGENT_CODE_RESEND_DELAY,
    })


def agent_details(request):
    if not request.user.is_authenticated:
        return redirect(_agent_registration_login_redirect())
    if Agent.objects.filter(user=request.user).exists():
        return redirect('listings:agent_dashboard')

    draft = AgentRegistrationDraft.objects.filter(user=request.user, email_verified=True).first()
    if not draft:
        messages.info(request, 'Verify your email address before completing your agent profile.')
        return redirect('listings:agent_registration')

    form = AgentDetailsForm(
        request.POST or None,
        initial={
            'agency': draft.agency,
            'bio': draft.bio,
            'specialties': draft.specialties.split(',') if draft.specialties else [],
            'city': draft.city,
        },
    )
    if request.method == 'POST' and form.is_valid():
        with transaction.atomic():
            draft = AgentRegistrationDraft.objects.select_for_update().get(pk=draft.pk)
            if not draft.email_verified:
                messages.error(request, 'Verify your email address before completing your agent profile.')
                return redirect('listings:agent_registration')
            Agent.objects.create(
                user=request.user,
                name=draft.name,
                agency=form.cleaned_data['agency'],
                phone=draft.phone,
                whatsapp=draft.phone,
                photo=draft.photo,
                bio=form.cleaned_data['bio'],
                specialties=', '.join(form.cleaned_data['specialties']),
                city=form.cleaned_data['city'],
                verified=True,
            )
            draft.delete()
        messages.success(request, 'Your agent profile is verified and ready.')
        return redirect('listings:agent_dashboard')

    return render(request, 'listings/agents/details.html', {'form': form, 'draft': draft})


def google_profile_completion(request):
    if not request.user.is_authenticated:
        return redirect('listings:auth_login')

    form = GoogleProfileCompletionForm(
        request.POST or None,
        initial={
            'first_name': request.user.first_name or '',
            'last_name': request.user.last_name or '',
        },
    )
    if request.method == 'POST' and form.is_valid():
        request.user.first_name = form.cleaned_data['first_name'].strip()
        request.user.last_name = form.cleaned_data['last_name'].strip()
        request.user.save(update_fields=['first_name', 'last_name'])
        messages.success(request, 'Your profile details have been saved.')
        return redirect('listings:agent_dashboard')

    return render(request, 'listings/auth/google_profile_completion.html', {'form': form})


def password_reset_request(request):
    if request.user.is_authenticated:
        return redirect('listings:property_list')

    form = PasswordResetRequestForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        email = form.cleaned_data['email']
        request.session['password_reset_email'] = email
        request.session.pop('password_reset_verified_user_id', None)
        user = get_user_model().objects.filter(email__iexact=email, is_active=True).first()
        if user:
            now = timezone.now()
            with transaction.atomic():
                reset_code, created = PasswordResetCode.objects.select_for_update().get_or_create(
                    user=user,
                    defaults={
                        'code_hash': '',
                        'created_at': now - PASSWORD_RESET_RESEND_DELAY,
                        'expires_at': now,
                    },
                )
                can_send = created or now - reset_code.created_at >= PASSWORD_RESET_RESEND_DELAY
                if can_send:
                    code = f'{secrets.randbelow(1_000_000):06d}'
                    reset_code.code_hash = make_password(code)
                    reset_code.created_at = now
                    reset_code.expires_at = now + PASSWORD_RESET_CODE_TTL
                    reset_code.attempts = 0
                    reset_code.save()

            if can_send:
                try:
                    sent_count = send_mail(
                        subject='Your EstateHub password reset code',
                        message=(
                            f'Your password reset verification code is {code}.\n\n'
                            'This code expires in 10 minutes. If you did not request '
                            'a password reset, you can ignore this email.'
                        ),
                        from_email=settings.DEFAULT_FROM_EMAIL,
                        recipient_list=[user.email],
                        fail_silently=False,
                    )
                    if sent_count != 1:
                        logger.error('Password reset email was not accepted by the email backend')
                        PasswordResetCode.objects.filter(
                            pk=reset_code.pk,
                            code_hash=reset_code.code_hash,
                        ).delete()
                        messages.error(
                            request,
                            'We could not send your verification code right now. Please try again later.',
                        )
                        return redirect('listings:password_reset_request')
                except (SMTPException, OSError):
                    logger.exception(
                        'Could not send password reset email using backend %s',
                        settings.EMAIL_BACKEND,
                    )
                    PasswordResetCode.objects.filter(
                        pk=reset_code.pk,
                        code_hash=reset_code.code_hash,
                    ).delete()
                    messages.error(
                        request,
                        'We could not send your verification code right now. Please try again later.',
                    )
                    return redirect('listings:password_reset_request')

        if settings.EMAIL_BACKEND == 'django.core.mail.backends.console.EmailBackend':
            messages.info(
                request,
                'If an account exists for that email, its code is available in the application '
                'server console. Email delivery is not configured in this environment.',
            )
        else:
            messages.info(
                request,
                'If an active account exists for that email, a verification code has been sent.',
            )
        return redirect('listings:password_reset_verify')

    return render(request, 'listings/auth/password_reset_request.html', {'form': form})


def password_reset_verify(request):
    if request.user.is_authenticated:
        return redirect('listings:property_list')

    email = request.session.get('password_reset_email')
    if not email:
        messages.info(request, 'Enter your email address to request a password reset code.')
        return redirect('listings:password_reset_request')

    form = PasswordResetCodeForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        user = get_user_model().objects.filter(email__iexact=email, is_active=True).first()
        valid_code = False
        if user:
            with transaction.atomic():
                reset_code = PasswordResetCode.objects.select_for_update().filter(user=user).first()
                now = timezone.now()
                if reset_code and reset_code.expires_at > now and reset_code.attempts < PASSWORD_RESET_MAX_ATTEMPTS:
                    if check_password(form.cleaned_data['code'], reset_code.code_hash):
                        reset_code.delete()
                        valid_code = True
                    else:
                        reset_code.attempts += 1
                        reset_code.save(update_fields=['attempts'])
                        if reset_code.attempts >= PASSWORD_RESET_MAX_ATTEMPTS:
                            reset_code.delete()
                elif reset_code:
                    reset_code.delete()

        if valid_code:
            request.session.cycle_key()
            request.session['password_reset_verified_user_id'] = user.pk
            request.session.set_expiry(PASSWORD_RESET_SESSION_TTL)
            return redirect('listings:password_reset_new')

        form.add_error(None, 'That verification code is invalid or expired. Request a new code and try again.')

    return render(request, 'listings/auth/password_reset_verify.html', {
        'form': form,
        'email': email,
        'email_backend_is_console': (
            settings.EMAIL_BACKEND == 'django.core.mail.backends.console.EmailBackend'
        ),
    })


def password_reset_new(request):
    if request.user.is_authenticated:
        return redirect('listings:property_list')

    user_id = request.session.get('password_reset_verified_user_id')
    user = get_user_model().objects.filter(pk=user_id, is_active=True).first() if user_id else None
    if not user:
        request.session.pop('password_reset_verified_user_id', None)
        messages.info(request, 'Verify your email before choosing a new password.')
        return redirect('listings:password_reset_request')

    form = BuyerSetPasswordForm(user, request.POST or None)
    if request.method == 'POST' and form.is_valid():
        form.save()
        request.session.pop('password_reset_verified_user_id', None)
        request.session.pop('password_reset_email', None)
        messages.success(request, 'Your password has been reset. Log in with your new password.')
        return redirect('listings:auth_login')

    return render(request, 'listings/auth/password_reset_new.html', {'form': form})


@require_POST
def logout_page(request):
    logout(request)
    messages.success(request, 'You have been logged out.')
    return redirect('listings:auth_login')


def _json_body(request):
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _user_data(user):
    return {
        'id': user.pk,
        'fullName': user.get_full_name() or user.email,
        'email': user.email,
    }


@ensure_csrf_cookie
@require_GET
def current_user(request):
    if request.user.is_authenticated:
        return JsonResponse({'authenticated': True, 'user': _user_data(request.user)})
    return JsonResponse({'authenticated': False, 'user': None})


@require_POST
def register(request):
    data = _json_body(request)
    if data is None:
        return JsonResponse({'error': 'Submit a valid registration form.'}, status=400)

    full_name = str(data.get('fullName', '')).strip()
    email = str(data.get('email', '')).strip().lower()
    password = data.get('password')
    if not full_name or len(full_name) > 150:
        return JsonResponse({'error': 'Enter your full name (up to 150 characters).'}, status=400)
    if not isinstance(password, str) or not password:
        return JsonResponse({'error': 'Enter a password.'}, status=400)

    try:
        validate_email(email)
    except ValidationError:
        return JsonResponse({'error': 'Enter a valid email address.'}, status=400)

    User = get_user_model()
    username_field = User.USERNAME_FIELD
    if User.objects.filter(email__iexact=email).exists() or User.objects.filter(
        **{f'{username_field}__iexact': email}
    ).exists():
        return JsonResponse({'error': 'An account with this email already exists. Please log in.'}, status=409)

    user = User(email=email)
    if username_field != 'email':
        setattr(user, username_field, email)
    user.first_name = full_name
    try:
        validate_password(password, user=user)
    except ValidationError as error:
        return JsonResponse({'error': ' '.join(error.messages)}, status=400)

    user.set_password(password)
    user.save()
    login(request, user, backend='django.contrib.auth.backends.ModelBackend')
    return JsonResponse({'user': _user_data(user)}, status=201)


@require_POST
def login_view(request):
    data = _json_body(request)
    if data is None:
        return JsonResponse({'error': 'Submit a valid login form.'}, status=400)

    email = str(data.get('email', '')).strip().lower()
    password = data.get('password')
    if not email or not isinstance(password, str) or not password:
        return JsonResponse({'error': 'Enter your email and password.'}, status=400)

    User = get_user_model()
    user = authenticate(request, username=email, password=password)
    if user is None:
        user = authenticate(request, email=email, password=password)
    if user is None:
        return JsonResponse({'error': 'Email or password is incorrect.'}, status=401)

    login(request, user)
    return JsonResponse({'user': _user_data(user)})


@require_POST
def google_login(request):
    if not settings.GOOGLE_CLIENT_ID:
        return JsonResponse({'error': 'Google sign-in is not configured yet.'}, status=503)

    data = _json_body(request)
    credential = data.get('credential') if data else None
    if not isinstance(credential, str) or not credential:
        return JsonResponse({'error': 'Google did not return a sign-in credential.'}, status=400)

    from google.auth.exceptions import TransportError
    from google.auth.transport.requests import Request
    from google.oauth2 import id_token

    try:
        claims = id_token.verify_oauth2_token(
            credential,
            Request(),
            settings.GOOGLE_CLIENT_ID,
        )
    except ValueError:
        return JsonResponse({'error': 'Google sign-in could not verify your account.'}, status=401)
    except TransportError:
        logger.exception('Google token verification service is unavailable')
        return JsonResponse({'error': 'Google sign-in is temporarily unavailable. Please try again.'}, status=503)

    email = str(claims.get('email', '')).strip().lower()
    if not email or claims.get('email_verified') is not True:
        return JsonResponse({'error': 'Use a Google account with a verified email address.'}, status=401)

    User = get_user_model()
    user = User.objects.filter(email__iexact=email).first()
    if user is None:
        username_field = User.USERNAME_FIELD
        user = User(email=email)
        if username_field != 'email':
            setattr(user, username_field, email)
        user.first_name = str(claims.get('given_name') or claims.get('name') or email).strip()[:150]
        user.last_name = str(claims.get('family_name') or '').strip()[:150]
        user.set_unusable_password()
        user.save()

    login(request, user, backend='django.contrib.auth.backends.ModelBackend')
    needs_profile_completion = not (user.first_name and user.last_name)
    redirect_url = reverse('listings:google_profile_completion') if needs_profile_completion else reverse('listings:property_list')
    return JsonResponse({'user': _user_data(user), 'redirect_to': redirect_url})


@require_POST
def logout_view(request):
    logout(request)
    return JsonResponse({'authenticated': False})

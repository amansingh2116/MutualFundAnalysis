"""apps/core/views.py - Shared views including registration, email verification, and contact."""
import json
import logging
import mimetypes
from pathlib import Path

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model, login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.tokens import default_token_generator
from django.contrib.auth.views import LoginView
from django.utils.decorators import method_decorator
from django.core.mail import EmailMultiAlternatives, send_mail
from django.db import DatabaseError
from django.http import FileResponse, Http404
from django.shortcuts import redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from django.utils.text import slugify
try:
    from django_ratelimit.decorators import ratelimit
except ImportError:
    def ratelimit(*args, **kwargs):
        def decorator(func):
            return func
        return decorator

from .content import (
    BLOGS_DIR,
    IMAGE_SUFFIXES,
    PDF_CATEGORY_CHAPTERS,
    PDF_CATEGORY_HANDBOOK,
    PDF_CATEGORY_OTHER,
    PDF_GUIDE_PDFS_DIR,
    PDF_GUIDES_DIR,
    PDF_SUFFIXES,
    _parse_tags,
    first_markdown_heading,
    first_markdown_paragraph,
    metadata_slug,
    parse_front_matter,
    path_to_base_relative,
    read_pdf_manifest,
    render_blog_markdown,
    resolve_resource_relative,
)
from .forms import ContactForm, RegistrationForm
from .models import LearnBlogPost, LearnPDFGuide

User = get_user_model()
logger = logging.getLogger('mfanalysis')


@method_decorator(ratelimit(key='ip', rate='5/m', method='POST', block=True), name='post')
class RateLimitedLoginView(LoginView):
    """
    Django's built-in LoginView with IP-based rate limiting on POST requests.
    Allows 5 login attempts per minute per IP; blocks after that with HTTP 429.

    NOTE: @ratelimit must be applied via method_decorator (not directly as
    a method decorator) because class methods receive `self` as args[0], but
    the ratelimit decorator expects `request` as args[0]. method_decorator
    properly handles this translation.

    form_invalid override: if the credentials are correct but the account is
    inactive (stuck from old SMTP-failure-delete bug), auto-activate and log in.
    """

    def form_invalid(self, form):
        """Handle failed login — auto-recover inactive accounts with correct password."""
        username = form.data.get('username', '').strip()
        password = form.data.get('password', '')

        if username and password:
            try:
                user = User.objects.get(username=username)
                if not user.is_active and user.check_password(password):
                    # Account exists, password is correct, but stuck inactive
                    # (e.g. email verification was never completed because SMTP failed)
                    user.is_active = True
                    user.save(update_fields=['is_active'])
                    login(
                        self.request,
                        user,
                        backend='django.contrib.auth.backends.ModelBackend',
                    )
                    messages.success(
                        self.request,
                        f'Welcome back, {user.username}! '
                        'Your account has been activated.',
                    )
                    logger.info(
                        'Auto-activated stuck inactive account for user %s', user.username
                    )
                    return redirect(self.get_success_url())
            except User.DoesNotExist:
                pass

        return super().form_invalid(form)


def _send_activation_email(request, user):
    """Send an email-verification link to newly registered user."""
    uid   = urlsafe_base64_encode(force_bytes(user.pk))
    token = default_token_generator.make_token(user)
    activate_url = request.build_absolute_uri(
        reverse('core:activate', kwargs={'uidb64': uid, 'token': token})
    )
    ctx = {
        'user':         user,
        'activate_url': activate_url,
        'site_name':    'MF Analysis',
    }
    subject    = 'Activate your MF Analysis account'
    text_body  = render_to_string('registration/activation_email.txt',  ctx)
    html_body  = render_to_string('registration/activation_email.html', ctx)
    msg = EmailMultiAlternatives(
        subject=subject,
        body=text_body,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[user.email],
    )
    msg.attach_alternative(html_body, 'text/html')
    msg.send(fail_silently=False)


@ratelimit(key='ip', rate='3/m', method='POST', block=True)
def register_view(request):
    """Register a new user.

    If SMTP is configured (EMAIL_HOST_USER is set), creates an inactive account
    and sends an activation email.
    If SMTP is NOT configured (console backend), activates the account immediately
    and logs the user in — so the site is usable without email setup.
    """
    if request.user.is_authenticated:
        return redirect('funds:home')

    if request.method == 'POST':
        form = RegistrationForm(request.POST)
        if form.is_valid():
            user = form.save()  # is_active=False set in form.save()

            email_configured = bool(settings.EMAIL_HOST_USER)

            if email_configured:
                # Full email-verification flow
                try:
                    _send_activation_email(request, user)
                    logger.info('Activation email sent to %s', user.email)
                    return redirect('core:email_verification_sent')
                except Exception as exc:
                    logger.warning(
                        'Activation email failed for %s (%s) — auto-activating instead.',
                        user.email, exc,
                    )
                    # Do NOT delete the account — activate immediately and log in.
                    # Deleting the user on SMTP failure means the visitor can never
                    # register (the form just says "try again later" indefinitely).
                    user.is_active = True
                    user.save(update_fields=['is_active'])
                    login(
                        request,
                        user,
                        backend='django.contrib.auth.backends.ModelBackend',
                    )
                    messages.warning(
                        request,
                        'Your account has been created! '
                        '(We could not send a verification email — '
                        'you have been logged in directly.)',
                    )
                    return redirect('funds:home')
            else:
                # No SMTP configured — activate immediately and log in
                user.is_active = True
                user.save(update_fields=['is_active'])
                login(request, user)
                logger.info(
                    'User %s registered and auto-activated (no SMTP configured)',
                    user.username,
                )
                messages.success(
                    request,
                    f'Welcome, {user.username}! Your account is ready.',
                )
                return redirect('funds:home')
    else:
        form = RegistrationForm()

    # Apply consistent styling to all form widgets
    for field in form.fields.values():
        field.widget.attrs.setdefault('class', 'form-control')

    return render(request, 'registration/register.html', {'form': form})


def email_verification_sent_view(request):
    """Shown after registration — tells user to check inbox."""
    return render(request, 'registration/email_verification_sent.html')


def activate_view(request, uidb64, token):
    """Validate the signed activation link, activate account, and log the user in."""
    try:
        uid  = force_str(urlsafe_base64_decode(uidb64))
        user = User.objects.get(pk=uid)
    except (TypeError, ValueError, OverflowError, User.DoesNotExist):
        user = None

    if user is not None and default_token_generator.check_token(user, token):
        user.is_active = True
        user.save(update_fields=['is_active'])
        login(request, user)
        messages.success(
            request,
            f'Welcome, {user.username}! Your account is now active.',
        )
        return redirect('funds:home')

    # Invalid or expired link
    return render(request, 'registration/activation_invalid.html', status=400)


def _asset_url(relative_path):
    if not relative_path:
        return ''
    return reverse('core:learn_resource_asset', args=[relative_path])


def _guide_card_from_model(guide):
    return {
        'title': guide.title,
        'description': guide.description,
        'accent': guide.accent or guide.title[:5],
        'size_kb': guide.size_kb,
        'cover_url': _asset_url(guide.cover_image_path),
        'pdf_url': reverse('core:learn_pdf_viewer', args=[guide.slug]),
        'source_key': guide.pdf_path,
        'category': guide.category,
        'tags': guide.tag_list(),
        'downloadable': guide.downloadable,
    }


def _blog_card_from_model(post):
    return {
        'title': post.title,
        'description': post.description,
        'tag': 'Blog',
        'read_time': post.read_time,
        'thumbnail_url': _asset_url(post.thumbnail_path),
        'url': reverse('core:learn_blog_detail', args=[post.slug]),
        'source_key': post.markdown_path,
        'tags': post.tag_list(),
        'sort_order': post.sort_order,
        'featured': post.is_featured,
    }


def _guide_card_from_file(pdf_path, meta, index):
    title = meta.get('title') or pdf_path.stem.replace('_', ' ').replace('-', ' ').title()
    cover = meta.get('cover') or meta.get('cover_image') or ''
    cover_path = path_to_base_relative((PDF_GUIDES_DIR / cover).resolve()) if cover else ''
    raw_tags = meta.get('tags', [])
    viewer_slug = slugify(meta.get('slug') or pdf_path.stem)[:140]
    return {
        'title': title,
        'description': meta.get('description') or 'A learning guide from the local PDF library.',
        'accent': meta.get('accent') or title[:5],
        'size_kb': max(1, round(pdf_path.stat().st_size / 1024)),
        'cover_url': _asset_url(cover_path),
        'pdf_url': reverse('core:learn_pdf_viewer', args=[viewer_slug]),
        'sort_order': int(meta.get('order') or meta.get('sort_order') or index * 10),
        'source_key': path_to_base_relative(pdf_path),
        'category': meta.get('category') or PDF_CATEGORY_OTHER,
        'tags': _parse_tags(raw_tags if isinstance(raw_tags, str) else json.dumps(raw_tags)),
        'downloadable': bool(meta.get('downloadable', False)),
    }


def _blog_from_file(markdown_path, index=1):
    markdown_text = markdown_path.read_text(encoding='utf-8')
    meta, body = parse_front_matter(markdown_text)
    title = meta.get('title') or first_markdown_heading(body, markdown_path.stem.replace('_', ' ').title())
    thumbnail = meta.get('thumbnail') or meta.get('cover') or meta.get('cover_image') or ''
    thumbnail_path = path_to_base_relative((markdown_path.parent / thumbnail).resolve()) if thumbnail else ''
    raw_tags = meta.get('tags', [])
    return {
        'slug': metadata_slug(meta, markdown_path),
        'title': title,
        'description': meta.get('description') or first_markdown_paragraph(body, 'A learning article from the local blog library.'),
        'tag': 'Blog',
        'read_time': meta.get('read_time') or '5 min read',
        'thumbnail_url': _asset_url(thumbnail_path),
        'url': reverse('core:learn_blog_detail', args=[metadata_slug(meta, markdown_path)]),
        'sort_order': int(meta.get('order') or meta.get('sort_order') or index * 10),
        'markdown_path': markdown_path,
        'markdown_text': markdown_text,
        'source_key': path_to_base_relative(markdown_path),
        'tags': _parse_tags(raw_tags if isinstance(raw_tags, list) else json.dumps(raw_tags)),
        'featured': bool(meta.get('featured', False)),
    }


def _file_pdf_guides():
    manifest = read_pdf_manifest()
    guides = []
    if not PDF_GUIDE_PDFS_DIR.exists():
        return guides

    pdf_paths = sorted(PDF_GUIDE_PDFS_DIR.glob('*.pdf'), key=lambda item: item.name.lower())
    for index, pdf_path in enumerate(pdf_paths, start=1):
        key = pdf_path.relative_to(PDF_GUIDES_DIR).as_posix()
        meta = manifest.get(key, {})
        if not bool(meta.get('published', meta.get('is_published', True))):
            continue
        guides.append(_guide_card_from_file(pdf_path, meta, index))
    return sorted(guides, key=lambda item: (item['sort_order'], item['title']))


def _file_blog_posts():
    blogs = []
    if not BLOGS_DIR.exists():
        return blogs

    markdown_paths = sorted(BLOGS_DIR.glob('*.md'), key=lambda item: item.name.lower())
    for index, markdown_path in enumerate(markdown_paths, start=1):
        blog = _blog_from_file(markdown_path, index)
        _meta, _body = parse_front_matter(blog['markdown_text'])
        if not bool(_meta.get('published', _meta.get('is_published', True))):
            continue
        blogs.append(blog)
    return sorted(blogs, key=lambda item: (item['sort_order'], item['title']))


def _collect_all_guides_and_blogs():
    """Return (all_pdf_guides, all_blog_posts) merged from DB + files."""
    try:
        all_pdf_keys = set(LearnPDFGuide.objects.values_list('pdf_path', flat=True))
        all_blog_keys = set(LearnBlogPost.objects.values_list('markdown_path', flat=True))
        pdf_guides = [
            _guide_card_from_model(guide)
            for guide in LearnPDFGuide.objects.filter(is_published=True).order_by('sort_order', 'title')
        ]
        blog_posts = [
            _blog_card_from_model(post)
            for post in LearnBlogPost.objects.filter(is_published=True).order_by('sort_order', 'title')
        ]
        pdf_guides.extend(guide for guide in _file_pdf_guides() if guide['source_key'] not in all_pdf_keys)
        blog_posts.extend(blog for blog in _file_blog_posts() if blog['source_key'] not in all_blog_keys)
    except DatabaseError:
        pdf_guides = _file_pdf_guides()
        blog_posts = _file_blog_posts()

    pdf_guides = sorted(pdf_guides, key=lambda item: (item.get('sort_order', 100), item['title']))
    blog_posts = sorted(blog_posts, key=lambda item: (item.get('sort_order', 100), item['title']))
    return pdf_guides, blog_posts


def _collect_all_tags(pdf_guides, blog_posts):
    """Return sorted unique tag lists for PDFs and blogs."""
    pdf_tags = sorted({tag for guide in pdf_guides for tag in guide.get('tags', [])})
    blog_tags = sorted({tag for blog in blog_posts for tag in blog.get('tags', [])})
    return pdf_tags, blog_tags


def learn_resources_view(request):
    """Redirect old resources overview to the dedicated PDF guides page."""
    return redirect('core:learn_pdf_guides')


@login_required
def learn_pdf_guides_view(request):
    """Dedicated full-page view for PDF Guides."""
    pdf_guides, _blog_posts = _collect_all_guides_and_blogs()
    pdf_tags, _ = _collect_all_tags(pdf_guides, [])

    chapter_guides = [g for g in pdf_guides if g.get('category') == PDF_CATEGORY_CHAPTERS]
    handbook_guides = [g for g in pdf_guides if g.get('category') == PDF_CATEGORY_HANDBOOK]
    other_guides = [g for g in pdf_guides if g.get('category') == PDF_CATEGORY_OTHER]

    active_tag = request.GET.get('tag', '').strip()

    return render(request, 'learn/pdf_guides.html', {
        'pdf_guides': pdf_guides,
        'chapter_guides': chapter_guides,
        'handbook_guides': handbook_guides,
        'other_guides': other_guides,
        'pdf_tags': pdf_tags,
        'active_tag': active_tag,
    })


def learn_blogs_view(request):
    """Dedicated full-page view for Blogs."""
    _pdf_guides, blog_posts = _collect_all_guides_and_blogs()
    _, blog_tags = _collect_all_tags([], blog_posts)

    active_tag = request.GET.get('tag', '').strip()

    return render(request, 'learn/blogs.html', {
        'blog_posts': blog_posts,
        'blog_tags': blog_tags,
        'active_tag': active_tag,
    })


def _serve_pdf_response(pdf_path, as_attachment=False):
    """Serve raw PDF bytes with security headers that discourage saving."""
    if not pdf_path.exists() or pdf_path.suffix.lower() not in PDF_SUFFIXES:
        raise Http404('Guide not found')
    response = FileResponse(
        pdf_path.open('rb'),
        content_type='application/pdf',
        as_attachment=as_attachment,
        filename=pdf_path.name if as_attachment else None,
    )
    # Prevent search engine indexing of raw PDF bytes endpoint
    response['X-Robots-Tag'] = 'noindex, nofollow'
    # Instruct browser to display inline — not trigger Save As
    if not as_attachment:
        response['Content-Disposition'] = f'inline; filename="{pdf_path.name}"'
    # Prevent caching so the URL cannot be easily harvested and replayed
    response['Cache-Control'] = 'no-store, no-cache, must-revalidate, private'
    response['Pragma'] = 'no-cache'
    return response


def _find_pdf_path_by_slug(slug):
    manifest = read_pdf_manifest()
    if not PDF_GUIDE_PDFS_DIR.exists():
        return None

    for pdf_path in PDF_GUIDE_PDFS_DIR.glob('*.pdf'):
        key = pdf_path.relative_to(PDF_GUIDES_DIR).as_posix()
        meta = manifest.get(key, {})
        candidate = slugify(meta.get('slug') or pdf_path.stem)[:140]
        if candidate == slug:
            return pdf_path, meta
    return None, {}


def _guide_meta_by_slug(slug):
    """Return (pdf_path, title, downloadable) for a given slug from DB or manifest.

    The manifest's 'downloadable' field is always preferred over the DB value so
    that editing guides.json takes effect immediately without running sync_content.
    """
    manifest_path, manifest_meta = _find_pdf_path_by_slug(slug)
    # Manifest is the live source of truth for downloadable
    manifest_downloadable = bool(manifest_meta.get('downloadable', False)) if manifest_meta else False

    try:
        guide = LearnPDFGuide.objects.filter(slug=slug).first()
        if guide and not guide.is_published:
            return None, None, False
        if guide:
            # Use manifest value for downloadable (live control); DB for everything else
            downloadable = manifest_downloadable if manifest_meta else guide.downloadable
            return resolve_resource_relative(guide.pdf_path), guide.title, downloadable
    except DatabaseError:
        pass

    if not manifest_path:
        return None, None, False
    title = manifest_meta.get('title') or manifest_path.stem.replace('_', ' ').replace('-', ' ').title()
    return manifest_path, title, manifest_downloadable


@login_required
def learn_pdf_viewer_view(request, slug):
    """Render the in-app PDF viewer page — does NOT expose the raw PDF URL in HTML."""
    pdf_path, title, downloadable = _guide_meta_by_slug(slug)
    if not pdf_path:
        raise Http404('Guide not found')
    serve_url = reverse('core:learn_pdf_serve', args=[slug])
    return render(request, 'learn/pdf_viewer.html', {
        'title': title,
        'serve_url': serve_url,
        'downloadable': downloadable,
        'slug': slug,
    })


@login_required
def learn_pdf_serve_view(request, slug):
    """Serve the raw PDF bytes — only intended to be fetched by PDF.js inside the viewer."""
    pdf_path, _title, downloadable = _guide_meta_by_slug(slug)
    if not pdf_path:
        raise Http404('Guide not found')
    # If ?download=1 is requested AND the guide is downloadable, serve as attachment
    wants_download = request.GET.get('download') == '1'
    as_attachment = wants_download and downloadable
    return _serve_pdf_response(pdf_path, as_attachment=as_attachment)


@login_required
def learn_pdf_detail_view(request, slug):
    """Legacy — redirect to in-app viewer."""
    return redirect(reverse('core:learn_pdf_viewer', args=[slug]))


@login_required
def learn_pdf_view(request, filename):
    """Legacy filename-based route — resolve slug and redirect to viewer."""

    safe_name = Path(filename).name
    try:
        guide = LearnPDFGuide.objects.filter(pdf_path__iendswith=f'/{safe_name}', is_published=True).first()
        if guide:
            return redirect(reverse('core:learn_pdf_viewer', args=[guide.slug]))
    except DatabaseError:
        pass
    # Fall back: find by filename in manifest
    manifest = read_pdf_manifest()
    if PDF_GUIDE_PDFS_DIR.exists():
        for pdf_path in PDF_GUIDE_PDFS_DIR.glob('*.pdf'):
            if pdf_path.name == safe_name:
                key = pdf_path.relative_to(PDF_GUIDES_DIR).as_posix()
                meta = manifest.get(key, {})
                candidate_slug = slugify(meta.get('slug') or pdf_path.stem)[:140]
                return redirect(reverse('core:learn_pdf_viewer', args=[candidate_slug]))
    raise Http404('Guide not found')


def _find_blog_file_by_slug(slug):
    for blog in _file_blog_posts():
        if blog['slug'] == slug:
            return blog
    return None


def _report_url():
    try:
        report = LearnPDFGuide.objects.filter(slug='ipo-project-report', is_published=True).first()
        if report:
            return reverse('core:learn_pdf_detail', args=[report.slug])
    except DatabaseError:
        pass

    report_path = PDF_GUIDE_PDFS_DIR / 'ipo_project_report.pdf'
    if report_path.exists():
        return reverse('core:learn_pdf', args=[report_path.name])
    return ''


def learn_blog_detail_view(request, slug):
    blog = None
    markdown_path = None
    markdown_text = None
    try:
        post = LearnBlogPost.objects.filter(slug=slug).first()
        if post and not post.is_published:
            raise Http404('Blog not found')
        if post:
            markdown_path = resolve_resource_relative(post.markdown_path)
            if not markdown_path.exists() or markdown_path.suffix.lower() != '.md':
                raise Http404('Blog not found')
            markdown_text = markdown_path.read_text(encoding='utf-8')
            blog = _blog_card_from_model(post)
    except DatabaseError:
        pass

    if not blog:
        blog = _find_blog_file_by_slug(slug)
        if not blog:
            raise Http404('Blog not found')
        markdown_path = blog['markdown_path']
        markdown_text = blog['markdown_text']

    blog['html'] = render_blog_markdown(markdown_text, markdown_path)
    blog['report_url'] = _report_url()
    return render(request, 'learn/blog_detail.html', {'blog': blog})


def learn_resource_asset_view(request, resource_path):
    try:
        asset_path = resolve_resource_relative(resource_path)
    except ValueError:
        raise Http404('Asset not found')

    if not asset_path.exists() or asset_path.suffix.lower() not in IMAGE_SUFFIXES:
        raise Http404('Asset not found')

    content_type = mimetypes.guess_type(asset_path.name)[0] or 'application/octet-stream'
    return FileResponse(asset_path.open('rb'), content_type=content_type)


def learn_blog_image_view(request, filename):
    legacy_path = BLOGS_DIR / 'images' / 'ipo_analysis' / Path(filename).name
    return learn_resource_asset_view(request, path_to_base_relative(legacy_path))


@login_required(login_url='/accounts/login/')
def learn_community_view(request):
    return render(request, 'learn/community.html', {})


# ── Legal / Info pages ────────────────────────────────────────────────────────

def about_view(request):
    """About page — mission, philosophy, what we cover."""
    return render(request, 'legal/about.html', {})


def terms_view(request):
    """Terms of Service."""
    return render(request, 'legal/terms.html', {})


def privacy_view(request):
    """Privacy Policy."""
    return render(request, 'legal/privacy.html', {})


@ratelimit(key='ip', rate='5/5m', method='POST', block=True)
def contact_view(request):
    """Contact page — validates form and emails the message to the site admin inbox."""
    form = ContactForm()
    submitted = False

    if request.method == 'POST':
        form = ContactForm(request.POST)
        if form.is_valid():
            name     = form.cleaned_data['name']
            email    = form.cleaned_data.get('email') or 'not provided'
            subject_key = form.cleaned_data['subject']
            subject_labels = dict(ContactForm.SUBJECT_CHOICES)
            subject_label  = subject_labels.get(subject_key, subject_key)
            message  = form.cleaned_data['message']

            recipient = getattr(settings, 'CONTACT_RECIPIENT_EMAIL', '')
            if not recipient:
                recipient = settings.DEFAULT_FROM_EMAIL

            email_body = (
                f"New contact message from MF Analysis\n"
                f"{'=' * 48}\n"
                f"Name:    {name}\n"
                f"Email:   {email}\n"
                f"Subject: {subject_label}\n"
                f"{'=' * 48}\n\n"
                f"{message}\n"
            )
            try:
                send_mail(
                    subject=f'[MF Analysis Contact] {subject_label} — {name}',
                    message=email_body,
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[recipient],
                    fail_silently=False,
                )
                submitted = True
                messages.success(request, "Thanks for reaching out! We'll get back to you shortly.")
                logger.info('Contact form submitted by %s (%s) — subject: %s', name, email, subject_label)
            except Exception as exc:
                logger.error('Contact form email failed: %s', exc)
                messages.error(
                    request,
                    'Sorry, we could not send your message right now. '
                    'Please try again or email us directly.',
                )

    return render(request, 'legal/contact.html', {'submitted': submitted, 'form': form})


@login_required
def user_dashboard_view(request):
    """User account dashboard panel."""
    from apps.portfolio.models import Portfolio, SavedStrategy
    from apps.recommendations.models import RecommendationProfile
    from apps.benchmarks.models import UserBenchmarkProfile, UserMarketStripProfile, BenchmarkIndex
    from apps.benchmarks.registry import MARKET_INDICES
    from apps.benchmarks.api_views import DEFAULT_METRIC_KEYS, ALL_METRICS

    # 1. Portfolios
    portfolios = Portfolio.objects.filter(user=request.user).order_by('-created_at')

    # 2. Saved Backtester Strategies
    strategies = SavedStrategy.objects.filter(user=request.user).order_by('-updated_at')

    # 3. Recommendation Profile
    rec_profile = RecommendationProfile.objects.filter(user=request.user).first()
    
    # 4. Fund & ETF Watchlists
    from apps.portfolio.models import Watchlist
    fund_watchlists = list(Watchlist.objects.filter(user=request.user).order_by('-is_default', 'name'))

    # 5. Benchmark Watchlist
    bench_profile = UserBenchmarkProfile.objects.filter(user=request.user).first()
    watchlist_ids = bench_profile.watchlist if bench_profile else []
    watchlist_indices = list(BenchmarkIndex.objects.filter(id__in=watchlist_ids, is_active=True).values_list('name', flat=True))

    # 6. Market Strip Watchlist
    market_profile = UserMarketStripProfile.objects.filter(user=request.user).first()
    chosen_metrics = market_profile.metrics if (market_profile and market_profile.metrics) else DEFAULT_METRIC_KEYS
    # chosen_metrics may contain dicts (fund entries) — filter to string keys only for label display
    chosen_metric_labels = [
        ALL_METRICS[k] for k in chosen_metrics
        if isinstance(k, str) and k in ALL_METRICS
    ]

    return render(request, 'core/user_dashboard.html', {
        'portfolios': portfolios,
        'strategies': strategies,
        'rec_profile': rec_profile,
        'fund_watchlists': fund_watchlists,
        'watchlist_indices': watchlist_indices,
        'chosen_metric_labels': chosen_metric_labels,
    })


@login_required
def user_settings_view(request):
    """User account settings page for password changes, logout, and general account info."""
    from django.contrib.auth.forms import PasswordChangeForm
    from django.contrib.auth import update_session_auth_hash

    form = PasswordChangeForm(user=request.user)
    if request.method == 'POST':
        form = PasswordChangeForm(user=request.user, data=request.POST)
        if form.is_valid():
            user = form.save()
            update_session_auth_hash(request, user)  # Keep the user session active
            messages.success(request, 'Your password was successfully updated!')
            return redirect('core:user_settings')
        else:
            messages.error(request, 'Please correct the errors below.')

    return render(request, 'core/user_settings.html', {
        'form': form,
    })


def data_monitor_view(request):
    """
    Data Quality & Pipeline Monitor — shows what data we have, when it was last
    updated, analytics coverage, and the self-completing weekly pipeline cycle.

    Pipeline: runs every 6 hours via GitHub Actions (--resume --resume-hours=167).
    Each run processes stale funds until the 5h 10min time limit is hit.
    After ~8 runs (2–3 days) all ~2,300 funds are refreshed; remaining runs
    that week complete in < 5 minutes (nothing stale left).
    Next Monday: 7-day window expires → automatic full restart.

    Publicly accessible (no login required).
    """
    from datetime import date, timedelta
    from django.db.models import Count, Max, Q, Exists, OuterRef
    from django.utils import timezone

    from apps.funds.models import (
        Scheme, NAVHistory, FundScreenerSnapshot, FundModelScore, SchemeMeta,
        CategorySnapshot, FundScoreTrend, SchemeAumSnapshot,
    )
    from apps.benchmarks.models import BenchmarkIndex, BenchmarkNAV, BenchmarkReturns
    from apps.analytics.models import TrailingReturn
    from apps.holdings.models import Holding, SectorAllocation, MarketCapAllocation
    from apps.funds.models import IndustryInflow

    today = date.today()
    seven_days_ago = today - timedelta(days=7)
    now = timezone.now()

    # ── Fund universe ────────────────────────────────────────────────────────
    total_schemes = Scheme.objects.filter(is_active=True).count()

    # Primary pipeline universe: Direct Growth (Open-Ended) OR ETFs
    dg_filter = Q(is_direct=True, plan='GROWTH') | Q(is_etf=True)
    dg_schemes = Scheme.objects.filter(is_active=True).filter(dg_filter)
    total_dg   = dg_schemes.count()

    # Breakdown for transparency (ETFs that are also Direct Growth are counted once in total_dg)
    direct_growth_count = Scheme.objects.filter(is_active=True, is_direct=True, plan='GROWTH').count()
    etf_count           = Scheme.objects.filter(is_active=True, is_etf=True).count()
    etf_also_direct     = Scheme.objects.filter(is_active=True, is_etf=True, is_direct=True, plan='GROWTH').count()
    # total_dg = direct_growth_count + etf_count - etf_also_direct  (verified by DB)

    # ── NAV freshness ─────────────────────────────────────────────────────────
    # Use NAVHistory EXISTS subquery — always accurate regardless of whether the
    # denormalized Scheme.nav_date field was properly populated (it can be NULL
    # on the deployed DB even when NAVHistory rows exist for that scheme).
    nav_exists_subq = NAVHistory.objects.filter(scheme=OuterRef('pk'))
    with_nav = dg_schemes.filter(Exists(nav_exists_subq)).count()

    # Latest NAV date from the actual NAVHistory rows (not the cached field)
    latest_nav_date = NAVHistory.objects.aggregate(m=Max('date'))['m']

    # Count of DG funds whose latest NAVHistory row is the most recent trading day
    if latest_nav_date:
        nav_on_latest_date = (
            dg_schemes
            .filter(Exists(NAVHistory.objects.filter(scheme=OuterRef('pk'), date=latest_nav_date)))
            .count()
        )
    else:
        nav_on_latest_date = 0

    # Count of DG funds with any NAV in the past 7 days
    nav_this_week = (
        dg_schemes
        .filter(Exists(NAVHistory.objects.filter(scheme=OuterRef('pk'), date__gte=seven_days_ago)))
        .count()
    )

    total_nav_rows = NAVHistory.objects.count()

    # ── Analytics coverage ────────────────────────────────────────────────────
    with_snapshot    = FundScreenerSnapshot.objects.count()
    with_model_score = FundModelScore.objects.count()
    with_trailing    = TrailingReturn.objects.values('scheme').distinct().count()
    with_metadata    = SchemeMeta.objects.count()

    latest_snapshot_ts  = FundScreenerSnapshot.objects.aggregate(m=Max('updated_at'))['m']
    latest_score_ts     = FundModelScore.objects.aggregate(m=Max('computed_at'))['m']
    latest_trailing_ts  = TrailingReturn.objects.aggregate(m=Max('updated_at'))['m']

    # ── Category snapshots ────────────────────────────────────────────────────
    cat_snapshot_count  = CategorySnapshot.objects.count()
    latest_cat_ts       = CategorySnapshot.objects.aggregate(m=Max('updated_at'))['m']

    # ── Monthly: Portfolio holdings ───────────────────────────────────────────
    with_holdings       = Holding.objects.values('scheme').distinct().count()
    total_holding_rows  = Holding.objects.count()
    holding_months      = list(
        Holding.objects.values_list('as_of_month', flat=True)
        .distinct().order_by('-as_of_month')[:3]
    )
    latest_holding_month = holding_months[0] if holding_months else None
    with_sectors        = SectorAllocation.objects.values('scheme').distinct().count()
    with_cap            = MarketCapAllocation.objects.values('scheme').distinct().count()
    # Source breakdown
    holding_sources = dict(
        Holding.objects.values_list('source')
        .annotate(c=Count('pk'))
        .values_list('source', 'c')
    )

    # ── Monthly: AUM snapshots ────────────────────────────────────────────────
    with_aum_snapshot   = SchemeAumSnapshot.objects.values('scheme').distinct().count()
    aum_snapshot_months = list(
        SchemeAumSnapshot.objects.values_list('as_of_month', flat=True)
        .distinct().order_by('-as_of_month')[:3]
    )
    latest_aum_month    = aum_snapshot_months[0] if aum_snapshot_months else None

    # ── Weekly: Score trend ───────────────────────────────────────────────────
    with_score_trend        = FundScoreTrend.objects.values('scheme').distinct().count()
    latest_score_trend_week = FundScoreTrend.objects.aggregate(m=Max('as_of_week'))['m']
    score_trend_weeks       = FundScoreTrend.objects.values_list('as_of_week', flat=True).distinct().count()

    # ── Monthly: Industry inflows ─────────────────────────────────────────────
    try:
        inflow_months_available = (
            IndustryInflow.objects.values_list('month', flat=True)
            .distinct().order_by('-month')[:3]
        )
        latest_inflow_month = inflow_months_available[0] if inflow_months_available else None
    except Exception:
        latest_inflow_month = None
        inflow_months_available = []

    # ── Benchmark freshness ───────────────────────────────────────────────────
    benchmarks = (
        BenchmarkIndex.objects
        .filter(is_active=True)
        .annotate(
            latest_date=Max('nav_history__date'),
            row_count=Count('nav_history'),
        )
        .values('name', 'yahoo_ticker', 'latest_date', 'row_count')
        .order_by('name')
    )

    # ── 7-day pipeline activity ───────────────────────────────────────────────
    daily_activity = []
    for i in range(7):
        d = today - timedelta(days=i)
        count = FundScreenerSnapshot.objects.filter(updated_at__date=d).count()
        daily_activity.append({
            'date': d,
            'label': d.strftime('%a %d %b'),
            'count': count,
            'is_today': d == today,
        })
    max_daily = max((r['count'] for r in daily_activity), default=1) or 1

    # ── Coverage percentages ──────────────────────────────────────────────────
    def pct(n, d):
        return round(100 * n / d, 1) if d else 0

    coverage = {
        'nav':            pct(with_nav,            total_dg),
        'nav_latest_day': pct(nav_on_latest_date,  total_dg),
        'nav_this_week':  pct(nav_this_week,        total_dg),
        'snapshot':       pct(with_snapshot,        total_dg),
        'model':          pct(with_model_score,     total_dg),
        'trailing':       pct(with_trailing,        total_dg),
        'metadata':       pct(with_metadata,        total_dg),
        'holdings':       pct(with_holdings,        total_dg),
        'sectors':        pct(with_sectors,         total_dg),
        'cap':            pct(with_cap,             total_dg),
        'aum_snapshot':   pct(with_aum_snapshot,   total_dg),
        'score_trend':    pct(with_score_trend,     total_dg),
    }

    # ── Weekly progress (resume-based cycle) ─────────────────────────────────
    # The pipeline runs every 6 hours with --resume --resume-hours=167.
    # "This week" = updated since the most recent Monday 00:00 UTC.
    current_dow = today.isoweekday()   # 1=Mon … 7=Sun
    monday_this_week = today - timedelta(days=current_dow - 1)
    week_start_dt = timezone.make_aware(
        __import__('datetime').datetime.combine(monday_this_week, __import__('datetime').time.min)
    )

    weekly_updated  = FundScreenerSnapshot.objects.filter(updated_at__gte=week_start_dt).count()
    weekly_pct      = round(100 * weekly_updated / total_dg, 1) if total_dg else 0
    weekly_complete = weekly_updated >= total_dg

    # ── Pipeline run history (last 7 days, grouped into 6-hour slots) ────────
    from django.db.models.functions import TruncHour

    hourly_buckets = (
        FundScreenerSnapshot.objects
        .filter(updated_at__gte=now - timedelta(days=7))
        .annotate(hr=TruncHour('updated_at'))
        .values('hr')
        .annotate(count=Count('pk'))
        .order_by('-hr')
    )

    # Merge consecutive hours into "runs" (a run ends when there's a 2+ hour gap)
    pipeline_runs = []
    current_run = None
    for bucket in hourly_buckets:
        if current_run is None:
            current_run = {'start': bucket['hr'], 'end': bucket['hr'], 'count': bucket['count']}
        else:
            gap_hours = (current_run['start'] - bucket['hr']).total_seconds() / 3600
            if gap_hours <= 2:
                current_run['count'] += bucket['count']
                current_run['start'] = bucket['hr']  # extend back
            else:
                pipeline_runs.append(current_run)
                current_run = {'start': bucket['hr'], 'end': bucket['hr'], 'count': bucket['count']}
    if current_run:
        pipeline_runs.append(current_run)

    # Add cumulative weekly count to each run (running total newest→oldest)
    cumulative = 0
    for run in pipeline_runs:
        cumulative += run['count']
        run['cumulative'] = cumulative

    # ── Estimated runs remaining this week ───────────────────────────────────
    remaining_funds = max(0, total_dg - weekly_updated)
    recent_counts   = [r['count'] for r in pipeline_runs[:3]]
    avg_per_run     = int(sum(recent_counts) / len(recent_counts)) if recent_counts else 280
    runs_remaining  = max(0, -(-remaining_funds // max(avg_per_run, 1)))  # ceiling div

    context = {
        # Universe
        'total_schemes':       total_schemes,
        'total_dg':            total_dg,
        'direct_growth_count': direct_growth_count,
        'etf_count':           etf_count,
        'etf_also_direct':     etf_also_direct,
        # NAV
        'with_nav':            with_nav,
        'nav_on_latest_date':  nav_on_latest_date,
        'nav_this_week':       nav_this_week,
        'latest_nav_date':     latest_nav_date,
        'total_nav_rows':      total_nav_rows,
        # Analytics
        'with_snapshot':       with_snapshot,
        'with_model_score':    with_model_score,
        'with_trailing':       with_trailing,
        'with_metadata':       with_metadata,
        'latest_snapshot_ts':  latest_snapshot_ts,
        'latest_score_ts':     latest_score_ts,
        'latest_trailing_ts':  latest_trailing_ts,
        # Categories
        'cat_snapshot_count':  cat_snapshot_count,
        'latest_cat_ts':       latest_cat_ts,
        # Monthly: Portfolio holdings
        'with_holdings':       with_holdings,
        'total_holding_rows':  total_holding_rows,
        'holding_months':      holding_months,
        'latest_holding_month': latest_holding_month,
        'with_sectors':        with_sectors,
        'with_cap':            with_cap,
        'holding_sources':     holding_sources,
        # Monthly: AUM snapshots
        'with_aum_snapshot':   with_aum_snapshot,
        'aum_snapshot_months': aum_snapshot_months,
        'latest_aum_month':    latest_aum_month,
        # Weekly: Score trend
        'with_score_trend':    with_score_trend,
        'latest_score_trend_week': latest_score_trend_week,
        'score_trend_weeks':   score_trend_weeks,
        # Monthly: Industry inflows
        'latest_inflow_month':    latest_inflow_month,
        'inflow_months_available': list(inflow_months_available),
        # Benchmarks
        'benchmarks':          benchmarks,
        # 7-day activity bar chart
        'daily_activity':      daily_activity,
        'max_daily':           max_daily,
        # Coverage percentages
        'coverage':            coverage,
        # Weekly progress
        'weekly_updated':      weekly_updated,
        'weekly_pct':          weekly_pct,
        'weekly_complete':     weekly_complete,
        'remaining_funds':     remaining_funds,
        'runs_remaining':      runs_remaining,
        'avg_per_run':         avg_per_run,
        # Pipeline run history
        'pipeline_runs':       pipeline_runs,
        'today':               today,
        'monday_this_week':    monday_this_week,
    }
    return render(request, 'data_monitor.html', context)

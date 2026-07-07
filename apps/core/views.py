"""apps/core/views.py — Shared views including registration"""
from pathlib import Path
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.forms import UserCreationForm
from django.http import FileResponse, Http404
from django.shortcuts import redirect, render


class RegisterView:
    pass


def register_view(request):
    if request.user.is_authenticated:
        return redirect('funds:home')
    if request.method == 'POST':
        form = UserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            messages.success(request, f'Welcome, {user.username}! Your account has been created.')
            return redirect('funds:home')
    else:
        form = UserCreationForm()

    # Style the form fields
    for field in form.fields.values():
        field.widget.attrs.setdefault('class', 'form-control')

    return render(request, 'registration/register.html', {'form': form})

PDF_GUIDES_DIR = Path(settings.BASE_DIR) / 'Resources' / 'PDF Guides' / 'pdfs'

PDF_GUIDE_COPY = {
    'Goals.pdf': {
        'title': 'Goal-Based Investing',
        'description': 'A practical guide to mapping mutual fund choices to time horizons, priorities, and milestones.',
        'accent': 'Goal',
    },
    'MF_Booklet.pdf': {
        'title': 'Mutual Fund Basics',
        'description': 'A concise primer for understanding schemes, NAV, returns, categories, and portfolio fit.',
        'accent': 'MF',
    },
    'MutualFundBook.pdf': {
        'title': 'Mutual Fund Handbook',
        'description': 'A broader reference guide for fund concepts, investor behavior, and long-term decision making.',
        'accent': 'Book',
    },
    'Risks.pdf': {
        'title': 'Risk Awareness Guide',
        'description': 'Learn the risk types behind mutual funds and how to think about volatility, drawdowns, and suitability.',
        'accent': 'Risk',
    },
}


def _pdf_guides():
    guides = []
    if not PDF_GUIDES_DIR.exists():
        return guides

    for pdf_path in sorted(PDF_GUIDES_DIR.glob('*.pdf'), key=lambda p: p.stem.lower()):
        meta = PDF_GUIDE_COPY.get(pdf_path.name, {})
        guides.append({
            'filename': pdf_path.name,
            'title': meta.get('title', pdf_path.stem.replace('_', ' ')),
            'description': meta.get('description', 'A mutual fund learning guide from the local PDF library.'),
            'accent': meta.get('accent', pdf_path.stem[:4].upper()),
            'size_kb': max(1, round(pdf_path.stat().st_size / 1024)),
        })
    return guides


def learn_resources_view(request):
    featured_blog = {
        'title': 'How to Read a Mutual Fund Factsheet',
        'description': 'A placeholder article for the Learn blog. Replace this with your own mutual fund notes, walkthroughs, or explainers later.',
        'tag': 'Coming soon',
        'read_time': '5 min read',
    }
    return render(request, 'learn/resources.html', {
        'pdf_guides': _pdf_guides(),
        'featured_blog': featured_blog,
    })


def learn_pdf_view(request, filename):
    pdf_path = (PDF_GUIDES_DIR / Path(filename).name).resolve()
    try:
        pdf_path.relative_to(PDF_GUIDES_DIR.resolve())
    except ValueError:
        raise Http404('Guide not found')

    if not pdf_path.exists() or pdf_path.suffix.lower() != '.pdf':
        raise Http404('Guide not found')

    return FileResponse(pdf_path.open('rb'), content_type='application/pdf', filename=pdf_path.name)


def learn_community_view(request):
    posts = [
        {
            'author': 'Aman',
            'title': 'How do you decide between index and active funds?',
            'body': 'I am comparing cost, consistency, and downside behavior. Would love to collect simple frameworks from other investors.',
            'meta': 'Discussion starter',
            'replies': [
                'Look at rolling returns and category rank persistence, not just one-year performance.',
                'For core allocation, I prefer simple funds. For satellite allocation, I compare fund manager style.',
            ],
        },
        {
            'author': 'Community',
            'title': 'Share your rebalancing rules',
            'body': 'A placeholder thread for portfolio rebalancing ideas, mistakes, and practical rules of thumb.',
            'meta': 'Pinned prompt',
            'replies': ['Add your first real community replies here when the feature is connected.'],
        },
    ]
    return render(request, 'learn/community.html', {'posts': posts})
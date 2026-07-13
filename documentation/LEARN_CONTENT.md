# Learn Content Workflow

The Learn section is a file-backed content area for educational PDFs, markdown blogs, and a login-gated community page.

---

## Navigation Structure

| Sidebar Entry | URL | Description |
|---|---|---|
| **PDF Guides** | `/learn/resources/guides/` | PDF learning resources in three sections |
| **Blogs** | `/learn/resources/blogs/` | Markdown-based research and tutorial articles |
| **Community** (own section) | `/learn/community/` | Community feed — **login required** |

> **Note:** The old `/learn/resources/` URL redirects automatically to `/learn/resources/guides/`.

---

## PDF Guides Page Layout

The PDF Guides page has a fixed three-section layout:

### 1. Complete Mutual Fund Handbook *(always visible, not filterable)*
- Displayed as a full-width horizontal hero card at the top.
- Set `"category": "handbook"` in `guides.json`.
- No tags shown on this card — it represents the whole compendium and is intentionally unpinned from the tag filter.

### 2. Filter Bar
- Appears **below** the Handbook, **above** Chapterwise Guides and Other Guides.
- Filters only the Chapterwise and Other Guides sections.
- Allowed tags: `investing`, `fundamentals`, `technicals`, `research`, `analysis`, `mutual funds`, `ipo`
- Clicking a tag hides all non-matching cards in Chapters and Other Guides. The Handbook is always shown.

### 3. Chapterwise Guides *(filterable)*
- Set `"category": "chapters"` in `guides.json`.
- Displayed in a wider grid with chapter-number overlay badge.
- Cards are filterable by the tag filter bar.

### 4. Other Guides *(filterable)*
- Set `"category": "other"` in `guides.json`.
- Displayed in a denser grid.
- Cards are filterable by the tag filter bar.

---

## Adding PDF Guides

Place PDF files under:

```text
Resources/PDF Guides/pdfs/
```

Add or update metadata in:

```text
Resources/PDF Guides/guides.json
```

### guides.json entry format

```json
{
  "file": "pdfs/example.pdf",
  "title": "Example Guide",
  "description": "A short description shown on the PDF Guides page.",
  "slug": "example-guide",
  "accent": "Short Label",
  "cover": "",
  "order": 90,
  "published": true,
  "category": "other",
  "tags": ["investing", "analysis"]
}
```

**Field notes:**
- `file` — path relative to `Resources/PDF Guides/`.
- `category` — one of `"chapters"`, `"handbook"`, or `"other"`.
- `tags` — JSON array. Use only approved tags: `investing`, `fundamentals`, `technicals`, `research`, `analysis`, `mutual funds`, `ipo`.
- `cover` — optional path relative to `Resources/PDF Guides/`. If empty, a styled fallback card is shown using `accent`.
- `accent` — short label used in the generated cover card.
- `order` — controls sort order within each category section.
- `published: false` hides the guide when synced.

### Adding a new chapter

1. Drop the PDF in `Resources/PDF Guides/pdfs/`.
2. Add an entry with `"category": "chapters"` and a sequential `order` value.
3. Run `python manage.py sync_content`.

---

## Adding Blog Posts

Place markdown files under:

```text
Resources/Blogs/
```

Each blog should start with YAML front matter:

```markdown
---
title: "My Blog Title"
description: "Short summary shown on the Blogs page."
slug: "my-blog-title"
thumbnail: "images/my_blog/cover.png"
read_time: "6 min read"
order: 20
published: true
tags: ["ipo", "research", "analysis"]
---
```

**Field notes:**
- `thumbnail` — relative to the markdown file location.
- `tags` — JSON array. Approved tags: `ipo`, `research`, `analysis` (more can be added as needed).
- `order` — controls card ordering; the lowest `order` value is shown as the featured hero article.
- Blog images use standard markdown syntax: `![Alt text](images/my_blog/chart.png)`.
- Supported local image types: PNG, JPG, JPEG, WEBP, GIF.
- `published: false` hides the blog when synced.

---

## Sync Command

After adding or changing Learn content, run:

```bash
python manage.py sync_content
```

The command upserts:
- `LearnPDFGuide` records from `Resources/PDF Guides/guides.json` and PDFs in `pdfs/`.
- `LearnBlogPost` records from markdown front matter in `Resources/Blogs/*.md`.

Tags are stored in the DB as proper JSON arrays (`["tag1", "tag2"]`), not raw Python list strings.

If the database is temporarily unavailable in local development, the guides and blog views fall back to scanning the files directly. The database-backed sync is the intended production/admin workflow.

---

## Community Page

The Community page (`/learn/community/`) is a **login-required** realistic static mockup featuring:
- Post composer (UI only, coming soon)
- Explore / Following tab feed with sample posts, replies, and reactions
- Who to Follow panel and Trending Topics
- Community stats and moderation notices

Unauthenticated users are redirected to `/accounts/login/?next=/learn/community/` and returned after login.

---

## Admin Editing

Synced records are available in Django admin:

- **Core → Learn PDF Guides**
- **Core → Learn Blog Posts**

Admin edits can adjust title, description, category, tags, order, and publish status. Running `sync_content` again will refresh fields from source files — admin-only fields like `is_published` can be toggled without re-running sync.

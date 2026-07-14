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

## In-App PDF Viewer

Clicking any PDF card opens the **in-app viewer** instead of serving the raw file directly in the browser.
This prevents casual downloading and direct URL sharing of the underlying file.

### URL Structure

| Route | Purpose |
|---|---|
| `/learn/resources/guides/view/<slug>/` | Viewer page — rendered HTML with PDF.js |
| `/learn/resources/guides/serve/<slug>/` | Raw PDF bytes — fetched only by PDF.js internally |

> Old-style URLs (`/learn/resources/guides/<slug>/` and `/learn/resources/guides/pdf/<filename>`) redirect automatically to the new viewer.

### Viewer Features

- **PDF.js canvas rendering** — each page is drawn onto a `<canvas>` element; the browser never receives a direct `<a>` link to the file
- **Zoom toolbar**: − / + buttons step through `50% → 75% → 100% → 125% → 150% → 175% → 200% → 250% → 300%`; current zoom % shown; buttons disable at limits
- **Keyboard zoom**: `Ctrl/Cmd` + `+` to zoom in, `Ctrl/Cmd` + `-` to zoom out
- **Pinch-to-zoom** on touch/mobile
- **Go to page**: type a page number and press Enter or click "Go" — smoothly scrolls to that page
- **Page counter**: each page shows "Page N of Total" below the canvas
- **Conditional download button** — shown only when the guide has `"downloadable": true` in `guides.json`; absent from the HTML entirely otherwise

### Security Measures

The viewer applies several layers of protection against casual downloading:

| Measure | Implementation |
|---|---|
| No raw link in HTML | `serve_url` is injected into JS only — never rendered as an `<a href>` |
| No caching | Serve endpoint sets `Cache-Control: no-store, no-cache` and `Pragma: no-cache` |
| No search indexing | Serve endpoint sets `X-Robots-Tag: noindex, nofollow` |
| Right-click blocked | `contextmenu` event prevented on the canvas area |
| Save page blocked | `Ctrl+S` / `Cmd+S` intercepted at capture phase |
| Print blocked | `Ctrl+P` / `Cmd+P` intercepted; `window.print()` replaced with no-op; `@media print` CSS hides the entire page body and shows a "printing disabled" message |
| Drag blocked | `dragstart` prevented on canvas wrap |
| Middle-click blocked | Middle mouse button click prevented on viewer shell |
| `pointer-events: none` | Applied to every canvas element — disables text selection and image drag |

> **Note:** These are client-side deterrents. A determined user with browser DevTools can still locate the serve URL. For true DRM, a server-side image-conversion approach would be required. These measures are sufficient for educational content protection against casual users.

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
  "downloadable": false,
  "category": "other",
  "tags": ["investing", "analysis"]
}
```

**Field reference:**

| Field | Type | Description |
|---|---|---|
| `file` | string | Path relative to `Resources/PDF Guides/` |
| `title` | string | Display title on listing cards and in the viewer header |
| `description` | string | Short summary shown on the PDF Guides listing card |
| `slug` | string | URL slug for viewer (`/view/<slug>/`) and serve (`/serve/<slug>/`) routes |
| `accent` | string | Short label used in the fallback cover card when no `cover` image is provided |
| `cover` | string | Optional path to a cover image, relative to `Resources/PDF Guides/`. Empty = styled fallback |
| `order` | integer | Sort order within each category section; lower = earlier |
| `published` | boolean | `true` to show; `false` to hide. Synced to `is_published` in DB |
| `downloadable` | boolean | `true` shows a Download PDF button in the viewer; `false` (default) hides it entirely |
| `category` | string | One of `"chapters"`, `"handbook"`, or `"other"` |
| `tags` | array | JSON array. Approved tags: `investing`, `fundamentals`, `technicals`, `research`, `analysis`, `mutual funds`, `ipo` |

---

## Controlling the Download Button

The `downloadable` field is the **single control** for per-PDF download access:

```json
"downloadable": true    // Download PDF button visible in viewer
"downloadable": false   // Download button absent from DOM (default)
```

**How it works:**
- The `guides.json` value is **always preferred over the database value** at request time. Changing `guides.json` takes effect on the next page load — **no `sync_content` run needed**.
- Running `sync_content` afterwards will also update the DB record to match.
- When `downloadable: true`, the Download button links to `/serve/<slug>/?download=1`, which triggers a `Content-Disposition: attachment` response.
- When `downloadable: false`, the serve endpoint still responds inline for PDF.js rendering — but no download link appears in the HTML.

**Currently downloadable:**
- Mutual Fund Basics Booklet (`mutual-fund-basics-booklet`)
- Indian IPO Research Project Report (`ipo-project-report`)

---

## Adding a New Guide

1. Drop the PDF in `Resources/PDF Guides/pdfs/`.
2. Add an entry to `guides.json` with all required fields. Set `"downloadable": false` initially.
3. Run `python manage.py sync_content` to create the DB record and make it admin-editable.
4. When ready to enable download, set `"downloadable": true` in `guides.json` — live immediately.

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
featured: yes
tags: ["ipo", "research", "analysis"]
---
```

**Field reference:**

| Field | Type | Description |
|---|---|---|
| `title` | string | Display title shown on listing cards and in the article header |
| `description` | string | Short summary shown on the Blogs listing card |
| `slug` | string | URL slug (`/learn/resources/blogs/<slug>/`) — must be unique |
| `thumbnail` | string | Path to cover image, **relative to the markdown file's own directory** (e.g. `images/my_blog/cover.jpg`) |
| `read_time` | string | Displayed on card and article header (e.g. `"8 min read"`) |
| `order` | integer | Sort position in the blog list — lower number appears first. Has **no effect** on featured status |
| `published` | boolean | `true` to show, `false` to hide. Synced to `is_published` in DB |
| `featured` | boolean | `yes`/`true` to show a ⭐ Featured gold badge on the card. `no`/`false` (default) for normal display. Any number of blogs can be featured at once |
| `tags` | array | JSON array. Approved tags: `ipo`, `research`, `analysis`, `investing`, `taxation`, `mutual funds` (more can be added as needed) |

**Notes:**
- Blog images in the article body use standard markdown syntax: `![Alt text](images/my_blog/chart.png)`.
- Supported local image types: PNG, JPG, JPEG, WEBP, GIF.
- `published: false` hides the blog when synced.
- You do **not** need to add a Table of Contents section — the article reader builds it automatically from `h2`, `h3`, and `h4` headings and displays it as a sticky sidebar.
- Thumbnail images must be placed inside the `Resources/Blogs/images/` folder. The path in `thumbnail` is relative to the markdown file itself (e.g. if the .md is at `Resources/Blogs/my_blog.md`, the thumbnail `images/my_blog/cover.jpg` resolves to `Resources/Blogs/images/my_blog/cover.jpg`).

---

## Sync Command

After adding or changing Learn content, run:

```bash
python manage.py sync_content
```

The command upserts:
- `LearnPDFGuide` records from `Resources/PDF Guides/guides.json` and PDFs in `pdfs/` — all fields, including `downloadable`.
- `LearnBlogPost` records from markdown front matter in `Resources/Blogs/*.md`.

Tags are stored in the DB as proper JSON arrays (`["tag1", "tag2"]`), not raw Python list strings.

The command syncs the following fields for blog posts:

| DB Field | Frontmatter Key |
|---|---|
| `title` | `title` |
| `description` | `description` |
| `thumbnail_path` | `thumbnail` |
| `read_time` | `read_time` |
| `sort_order` | `order` |
| `is_published` | `published` |
| `is_featured` | `featured` |
| `tags` | `tags` |

> **`downloadable` without sync:** Because `guides.json` is always consulted at request time for this field, you do **not** need to run `sync_content` after changing `downloadable`. The change is live immediately.

If the database is temporarily unavailable in local development, the views fall back to reading files directly (including `downloadable` from the manifest).

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

Admin fields for PDF guides include: `title`, `description`, `category`, `tags`, `sort_order`, `is_published`, `downloadable`, and `accent`.

Admin fields for blog posts include: `title`, `description`, `thumbnail_path`, `read_time`, `sort_order`, `is_published`, `is_featured`, and `tags`.

> **Note:** Running `sync_content` will overwrite admin-edited values (except `downloadable` for PDFs, which always reads from `guides.json`). Frontmatter is the canonical source of truth for all blog fields.

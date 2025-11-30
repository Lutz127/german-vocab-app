# German Vocabulary App

### This project is fully deployed at: https://german-vocab-app.onrender.com/

### CS50 Video Demo: URL soon

## Description:

**German Vocabulary App** is my CS50 Final Project: a full-stack, gamified learning platform built with Python (Flask), JavaScript, TailwindCSS, and PostgreSQL/SQLite. The goal of the project is to make learning German vocabulary feel interactive, rewarding, and competitive, more like playing a game rather than studying from a static list.

This README describes how the application works, how the code is organized, and the design decisions that shaped the final result.

## Project Overview

The application lets users practice German vocabulary through quizzes in many categories. Each quiz pulls data from JSON files stored in `/static/data/`. A user chooses a category and a quiz mode, either German → English or English → German. Once a quiz ends, the app shows score, time, and (if the you got 100% score) a leaderboard placement.

Incorrect answers get added to a personal “Failed Words” quiz, which becomes its own study mode. The user can return to failed words at any time for targeted practice.

## User System & Profiles

User accounts are fully supported through registration and login. Passwords are securely hashed using Werkzeug's `generate_password_hash`. The Users table supports:

- username
- hashed password
- level
- XP
- next XP threshold
- streak count
- bio
- last active date
- profile picture filename

Every user has a **public profile** at: /u/username

These pages show:

- profile picture
- biography
- level and XP progress bar
- streak count
- total quizzes completed
- progress per vocabulary category
- global rank (based on XP)

I had to implement an XP system, streak logic, and rank calculation. XP grows through quiz completion, levels scale using a custom XP curve, and the daily streak checks if the user has played within 24 hours.

## Custom Profile Pictures

The user can upload an image, and the server (using Pillow) automatically:

1. Opens the image

2. Crops and resizes it to 256×256

3. Creates a circular mask

4. Applies the mask so the image becomes a round avatar

5. Saves it as a `.png`

6. Stores the filename in the database

To support persistent storage on Render, I switched from `/static/uploads` to a persistent volume mount `(/var/data/uploads)`. This required adjusting routes so Flask can serve uploaded files directly.

## Learning System

Each vocabulary category exists as a `.json` file. When a quiz loads, JavaScript reads the list, shuffles words, and displays questions one by one.

Quizzes include:

- live timer

- progress bar

- strict-article mode

- speedrun mode (no delay after answers)

- support for multiple correct translations like
  `die Mütze / die Kappe / der Hut`

- automatic stripping of German articles when strict mode is OFF

- automatic normalization (lowercase, umlaut equivalents, etc.)

## Gamification

A major focus of the project was to make learning feel more fun. The app includes:

### XP System

XP is calculated based on accuracy, quiz length, and speed bonuses. Level requirements scale non-linearly `(level^1.4 * 120)`.

### Perfect-Run Leaderboards

A leaderboard is shown after any non-failed-words quiz.

- only 100% scores are saved

- each user can appear only once per category

- the displayed score is always the user’s fastest perfect time

## Failed Words

Any incorrect answer gets logged in the database with:

- German word

- English translation

- gender (if provided)

- number of times failed

Users can redo a dedicated “Failed Words” quiz mode or clear them entirely.

## Streak System

Daily login streak that increments when the user completes at least one quiz per day. A simple datetime check compares today with the stored last_active date.

## Project Structure

```
/database
    schema.sql
/static
    /data         JSON vocabulary files
    /js           main.js (quiz engine)
    /img          UI assets + default profile picture
    /sfx          Sound effects (correct / wrong answer, typing)

/templates
    layout.html
    index.html
    login.html
    register.html
    account.html
    settings.html
    public_profile.html
    rankings.html
    (others)

app.py            Main Flask application
requirements.txt  Dependencies
README.md         This file
```

## Backend Design Decisions

### SQLite for local development

SQLite makes it easy to test schema changes and inspect the database directly.

### PostgreSQL for production

Render requires PostgreSQL for reliability and concurrency. All SQL queries use `%s` placeholders, and a custom `execute()` function automatically converts them to SQLite’s `?` when running locally.

### Persistent Disk for user uploads

This was required so avatar images survive deployments.

### XP & Level Storage

XP and next level XP are stored directly in the `users` table for fast access.

### JSON vocabulary

Keeping categories in JSON makes it easy to add/remove categories

# Technical Details & Design Decisions

This section explains the major files in the project, why the architecture is structured the way it is, and the challenges encountered while building the application.

## File Overview

### app.py

This is the core of the entire backend.
It contains:

- all Flask routes (authentication, quiz saving, leaderboards, profiles, settings, avatar uploads)

- database connection logic

- a compatibility layer that allows the same code to run on both SQLite (local) and PostgreSQL (production)

- XP, streak, and level-up logic

- secure avatar upload handling (image processing, validation, and storage)

- serving uploaded files through a dedicated `/uploads/<filename>` route

- JSON responses used by the JavaScript quiz engine

### static/js/main.js

This file contains the entire quiz engine:

- loads category JSON files

- shuffles vocabulary items

- handles strict-article mode

- handles English → German and German → English quiz directions

- normalizes umlauts (`ö → oe`) and case differences

- supports multiple acceptable answers per word

- manages the live timer and formatting of milliseconds → `mm:ss.xx`

- submits results to the backend using `fetch()`

- dynamically loads leaderboard results after each quiz

- tracks user progress using localStorage

This is one of the most logic heavy files in the project.

### static/data/*.json

Each JSON file represents a vocabulary category/subcategory.

Every file contains a list of objects with:
```
[
    {"german": "der Hund", "english": "dog"},
    {"german": "die Katze", "english": "cat"},
    {"german": "der Vogel", "english": "bird"}
]
```

I chose JSON over storing vocab in SQL for two reasons:

1. JSON is easier to modify, especially when expanding the dataset.

2. Database storage would require migrations every time new categories or fields were added.

### Templates

All HTML pages are stored in `/templates`:

- `layout.html` — Base layout, navbar, footer, settings

- `index.html` — Home page with category selection

- `login.html` / `register.html` — Auth pages

- `account.html` — Editable profile, failed words management, avatar upload

- `settings.html` — Theme, sound, strict mode, speedrun toggle

- `public_profile.html` — Public user page with XP, streak, stats, level bar

- `rankings.html` — Global leaderboard

- Quiz interface is rendered dynamically by JavaScript inside `index.html`

Templates use TailwindCSS utility classes for styling.

### schema.sql

Used for initializing local SQLite databases.
It mirrors the production PostgreSQL schema and serves as a reference for what each table stores.

### Why TailwindCSS

I chose Tailwind because:

- It allows very fast UI iteration using utility classes.

- It works great with dynamic elements generated through JavaScript.

- It eliminates the need to manage large `.css` files.

Since this project has many small UI components, Tailwind kept the design consistent.

## Design Decisions

### Leaderboard: why one entry per user

Initially, the leaderboard stored every perfect run, which caused duplicates.
I chose one entry per user to:

- ensure fairness

- highlight each person’s best performance

- reduce database clutter

- prevent spam from repeated attempts

### Avatars saved as circular PNGs

Rounded PNGs ensure all avatars look uniform.
PNG was chosen because:

- supports transparency

- works with circular alpha masks

- stays consistent regardless of the user’s original image format

### Persistent storage on Render

Render wipes the filesystem on every deploy, so avatars could not survive restarts.

The fix was:

- using the `/var/data` persistent volume

- writing uploads there instead of `/static/`

This required adding a dedicated `/uploads/<file>` Flask route to serve files manually.

### SQLite locally, PostgreSQL in production

SQLite is:

- easy to inspect

- perfect for rapid development

- file-based (no setup)

PostgreSQL is:

- production-grade

- required by Render

- safer for concurrency

To support both, I wrote a wrapper that converts `%s` → `?` automatically when running on SQLite.

### Nonlinear XP curve

The formula makes leveling faster early and slower later:

```
next_level_xp = level^1.4 * 120
```

### Speedrun mode

I added speedrun mode because:

- some users want fast-paced drilling

- it enables competitive leaderboards

- it aligns with the gamified design of the project

- it adds replayability

### Recording only 100% leaderboard runs

The decision was intentional:

- ensures a fair comparison between times (same difficulty)

- prevents partially correct runs from cluttering the leaderboard

## Hardest Challenges

### 1. Leaderboard SQL logic

Ensuring only perfect runs, fastest time and one entry per user required a complex SQL query joining multiple subqueries.

### 2. XP + streak system

Streak logic needed:

- comparing dates accurately

- handling missed days

- preventing streak inflation

- updating XP only when the user improves or gets 100%

### 3. Persistent avatars on Render

Tricky because:

- static folder is read-only

- deployment wipes uploaded files

- required a custom file-serving route

- needed Pillow image masks on the server

### 4. German strict-mode parsing

Harder than expected due to:

- words having multiple articles

- multiple correct answers

- umlaut normalization

- English synonyms

- hyphenated words and capitalization

### 5. Supporting multiple answers like:

`"die Mütze / die Kappe / der Hut"`

This required splitting answers, trimming whitespace, normalizing case, and checking arrays of correct synonyms.

## Security Considerations

- **Passwords** are hashed using `generate_password_hash` (Werkzeug)

- **SQL injection** prevented through parameterized queries everywhere

- **Avatar uploads** checked with:

  - file extension validation

  - `secure_filename()`

  - Pillow format conversion (strips metadata)

- **Session protection**:

  - SESSION_COOKIE_HTTPONLY

  - SESSION_COOKIE_SAMESITE=Lax

  - SESSION_COOKIE_SECURE=True
 
## Screenshots (November 30th 2025)

<img width="1919" height="1079" alt="image" src="https://github.com/user-attachments/assets/66e38ae4-0351-4c6d-9be2-c1ecc7f34e15" />

<img width="1919" height="1079" alt="image" src="https://github.com/user-attachments/assets/1f3a1528-13da-43d7-bf69-95cc0c91abdd" />

<img width="1919" height="1079" alt="image" src="https://github.com/user-attachments/assets/14592b4c-8965-4770-9ba9-9189d7975e2a" />

## AI Assistance Notice

Portions of this project were developed with the assistance of AI tools (ChatGPT) for guidance, debugging, and explanations.
All final decisions, architecture, and code were written and implemented by me.

## Acknowledgements

A huge thank you to **Luma** and **ivi** who helped test the app, report bugs, and give feedback during development.

## Final Thoughts

This project became far bigger than the initial idea, and I will keep developing it beyond it being my CS50 Final Project. I am proud of the amount of full-stack engineering involved: authentication, SQL storage, image processing, JavaScript UI, performance optimizations, and game-like elements.

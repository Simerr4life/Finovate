"""A tiny, dependency-free Finovate UI skeleton."""

from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import urlparse


ROOT = Path(__file__).parent
NAV_ITEMS = (
    ("dashboard", "Dashboard", "⌂"),
    ("investing", "Investing", "↗"),
    ("savings", "Savings", "◉"),
    ("budgeting", "Budgeting", "▦"),
    ("settings", "Settings", "⚙"),
)

PAGES = {
    "investing": {
        "eyebrow": "GROW AT YOUR OWN PACE",
        "title": "Investing",
        "description": "A little change can make a big difference. Your investing tools will live here.",
        "icon": "↗",
        "cards": (
            ("Spare-change investing", "Round-ups and portfolio insights are coming soon.", "Coming soon"),
            ("Your portfolio", "A friendly snapshot of your investments will show up here.", "Portfolio"),
        ),
    },
    "savings": {
        "eyebrow": "LITTLE WINS ADD UP",
        "title": "Savings",
        "description": "Set a goal, celebrate every milestone, and watch your savings grow.",
        "icon": "◉",
        "cards": (
            ("Your goals", "Create a savings goal and track your progress here.", "Goals"),
            ("Milestones", "Savings celebrations and progress notifications are coming soon.", "Celebrations"),
        ),
    },
    "budgeting": {
        "eyebrow": "MAKE A PLAN THAT FEELS GOOD",
        "title": "Budgeting",
        "description": "See where your money goes and make a budget that works for you.",
        "icon": "▦",
        "cards": (
            ("Monthly overview", "Your income and spending breakdown will appear here.", "Overview"),
            ("Spending categories", "Organize your spending into simple, colorful categories.", "Categories"),
        ),
    },
    "settings": {
        "eyebrow": "MAKE FINOVATE YOURS",
        "title": "Settings",
        "description": "Your account preferences and notification controls will live here.",
        "icon": "⚙",
        "cards": (
            ("Your profile", "Profile and account management are coming soon.", "Account"),
            ("Notifications", "Choose how you hear about investments and savings milestones.", "Preferences"),
        ),
    },
}


def page_shell(title, active, content):
    nav_items = []
    for key, label, icon in NAV_ITEMS:
        is_active = key == active
        active_class = " active" if is_active else ""
        aria_current = ' aria-current="page"' if is_active else ""
        nav_items.append(
            f'<a class="nav-link{active_class}" href="/{key}"{aria_current}>'
            f'<span class="nav-icon" aria-hidden="true">{icon}</span>{label}</a>'
        )
    nav = "".join(nav_items)
    login_active = active == "login"
    login_class = " active" if login_active else ""
    login_aria_current = ' aria-current="page"' if login_active else ""
    nav += (
        f'<a class="nav-link{login_class}" href="/login"{login_aria_current}>'
        '<span class="nav-icon" aria-hidden="true">↪</span>Log in</a>'
    )
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="theme-color" content="#f8f7ff">
  <title>{title} · Finovate</title>
  <link rel="stylesheet" href="/styles.css">
</head>
<body>
  <div class="app-shell">
    <aside class="sidebar">
      <a class="brand" href="/dashboard" aria-label="Finovate dashboard">
        <span class="brand-mark">f</span><span>finovate<span class="brand-dot">.</span></span>
      </a>
      <p class="nav-caption">YOUR MONEY SPACE</p>
      <nav class="main-nav" aria-label="Main navigation">{nav}</nav>
      <div class="sidebar-note">
        <span class="note-sparkle">✳</span>
        <p><strong>Small steps,</strong><br>bright futures.</p>
        <span class="note-team">TURN IT OFF AND ON AGAIN</span>
      </div>
    </aside>
    <main class="main-content">
      <header class="topbar">
        <span class="breadcrumb">Your space <span aria-hidden="true">/</span> <strong>{title}</strong></span>
        <a class="avatar" href="/settings" aria-label="Go to settings">M</a>
      </header>
      {content}
      <footer class="footer">Made for your next bright idea <span aria-hidden="true">✳</span></footer>
    </main>
  </div>
</body>
</html>
"""


def dashboard():
    content = """
      <section class="welcome hero-dashboard">
        <div class="hero-copy">
          <p class="eyebrow">YOUR FINANCES, A LITTLE MORE FINOVATE</p>
          <h1>Money moves.<br><span>You've got this.</span></h1>
          <p class="hero-description">A fresh start for your finances starts with one small step. Take a look around.</p>
          <a class="button button-dark" href="/budgeting">Explore your budget <span aria-hidden="true">→</span></a>
        </div>
        <div class="hero-art" aria-hidden="true">
          <div class="art-orbit orbit-one"></div><div class="art-orbit orbit-two"></div>
          <div class="art-sun"></div><div class="art-coin coin-one">$</div>
          <div class="art-coin coin-two">✳</div><div class="art-spark">✦</div>
          <div class="art-caption">YOUR MONEY<br>YOUR MOMENT</div>
        </div>
        <span class="hero-sticker">A little<br>goes a long way!</span>
      </section>
      <section class="section-heading">
        <div><p class="eyebrow">YOUR OVERVIEW</p><h2>A good place to start</h2></div>
        <span class="date-pill">YOUR FINANCE HOME</span>
      </section>
      <section class="overview-grid" aria-label="Finance overview">
        <article class="metric-card metric-lilac">
          <div class="metric-top"><span class="metric-icon">▦</span><span class="card-kicker">BUDGET</span></div>
          <p class="metric-title">Monthly plan</p><p class="metric-placeholder">Your budget, at a glance.</p>
          <a class="text-link" href="/budgeting">Go to budgeting <span aria-hidden="true">↗</span></a>
        </article>
        <article class="metric-card metric-peach">
          <div class="metric-top"><span class="metric-icon">◉</span><span class="card-kicker">SAVINGS</span></div>
          <p class="metric-title">Big-dream energy</p><p class="metric-placeholder">Your next savings goal starts here.</p>
          <a class="text-link" href="/savings">See your savings <span aria-hidden="true">↗</span></a>
        </article>
        <article class="metric-card metric-mint">
          <div class="metric-top"><span class="metric-icon">↗</span><span class="card-kicker">INVESTING</span></div>
          <p class="metric-title">Spare change, meet stocks</p><p class="metric-placeholder">Tiny investments. Future possibilities.</p>
          <a class="text-link" href="/investing">Explore investing <span aria-hidden="true">↗</span></a>
        </article>
      </section>
      <section class="bottom-callout">
        <span class="callout-icon">✳</span>
        <div><p class="eyebrow">COMING UP</p><h2>Your personal finance toolkit</h2>
          <p>Budgeting, savings goals, and spare-change investing—all in one happy place.</p>
        </div>
        <a class="button button-light" href="/login">Get started <span aria-hidden="true">→</span></a>
      </section>
"""
    return page_shell("Dashboard", "dashboard", content)


def placeholder_page(key):
    page = PAGES[key]
    cards = "".join(
        f'<article class="placeholder-card"><div class="placeholder-icon">{page["icon"]}</div>'
        f'<p class="card-kicker">{label}</p><h2>{heading}</h2><p>{description}</p>'
        '<span class="coming-badge">Coming soon</span></article>'
        for label, heading, description in page["cards"]
    )
    content = f"""
      <section class="page-intro">
        <div class="page-icon" aria-hidden="true">{page["icon"]}</div>
        <p class="eyebrow">{page["eyebrow"]}</p>
        <h1>{page["title"]}<span class="title-period">.</span></h1>
        <p class="page-description">{page["description"]}</p>
      </section>
      <section class="placeholder-grid">{cards}</section>
      <section class="info-banner"><span aria-hidden="true">✳</span>
        <p>This is a preview of the Finovate app skeleton. No financial data is collected or stored.</p>
      </section>
"""
    return page_shell(page["title"], key, content)


def login_page():
    content = """
      <section class="login-wrap">
        <div class="login-art" aria-hidden="true"><span>✳</span><strong>Your next<br>chapter starts<br>with a little.</strong></div>
        <div class="login-card">
          <p class="eyebrow">WELCOME TO YOUR MONEY SPACE</p>
          <h1>Hey there<span class="title-period">.</span></h1>
          <p class="page-description">Your sign-in experience will go here. This page is a placeholder for now.</p>
          <div class="auth-placeholder"><span class="auth-icon">↪</span><span><strong>Sign-in coming soon</strong><br>Account access will be added in a future step.</span></div>
          <a class="button button-dark" href="/dashboard">Back to dashboard <span aria-hidden="true">→</span></a>
          <p class="login-footnote">No account or personal information is needed for this preview.</p>
        </div>
      </section>
"""
    return page_shell("Log in", "login", content)


class FinovateHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        path = urlparse(self.path).path.rstrip("/") or "/"
        if path == "/styles.css":
            try:
                css = (ROOT / "static" / "styles.css").read_bytes()
            except OSError:
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Type", "text/css; charset=utf-8")
            self.send_header("Content-Length", str(len(css)))
            self.end_headers()
            self.wfile.write(css)
            return

        routes = {
            "/": dashboard,
            "/dashboard": dashboard,
            "/login": login_page,
            **{f"/{key}": lambda key=key: placeholder_page(key) for key in PAGES},
        }
        render = routes.get(path)
        if render is None:
            self.send_error(404, "Page not found")
            return
        body = render().encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        print(f"{self.address_string()} - {format % args}")


if __name__ == "__main__":
    server = HTTPServer(("127.0.0.1", 8000), FinovateHandler)
    print("Finovate is running at http://127.0.0.1:8000 (Ctrl+C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nFinovate stopped.")
    finally:
        server.server_close()

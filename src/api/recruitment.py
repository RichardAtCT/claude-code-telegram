"""Recruitment page endpoint.

Serves a careers page for Unravel (@unraveldottech).
"""

from fastapi import FastAPI
from fastapi.responses import HTMLResponse

RECRUITMENT_HTML = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Careers | Unravel</title>
<style>
  :root {
    --bg: #0f0f13;
    --surface: #18181f;
    --border: #2a2a35;
    --text: #e4e4e8;
    --text-muted: #9494a0;
    --accent: #6d5dfc;
    --accent-light: #8b7ffd;
    --accent-glow: rgba(109, 93, 252, 0.15);
    --green: #34d399;
    --amber: #fbbf24;
  }

  *, *::before, *::after {
    margin: 0;
    padding: 0;
    box-sizing: border-box;
  }

  body {
    font-family: 'SF Mono', 'Fira Code', 'JetBrains Mono', 'Cascadia Code',
                 ui-monospace, monospace;
    background: var(--bg);
    color: var(--text);
    line-height: 1.7;
    min-height: 100vh;
  }

  .container {
    max-width: 720px;
    margin: 0 auto;
    padding: 3rem 1.5rem 4rem;
  }

  /* Header */
  .header {
    text-align: center;
    margin-bottom: 3rem;
  }

  .header h1 {
    font-size: 1.6rem;
    font-weight: 600;
    letter-spacing: -0.02em;
    margin-bottom: 0.5rem;
  }

  .header h1 .at {
    color: var(--accent-light);
  }

  .header .tagline {
    color: var(--text-muted);
    font-size: 0.85rem;
  }

  /* Divider */
  .divider {
    border: none;
    border-top: 1px solid var(--border);
    margin: 2rem 0;
  }

  /* Sections */
  .section {
    margin-bottom: 2.5rem;
  }

  .section-title {
    font-size: 0.75rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    color: var(--accent-light);
    margin-bottom: 1rem;
    display: flex;
    align-items: center;
    gap: 0.5rem;
  }

  .section-title::before {
    content: '>';
    color: var(--accent);
    font-weight: 700;
  }

  /* Cards */
  .card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 1.25rem 1.5rem;
    margin-bottom: 0.75rem;
    transition: border-color 0.2s ease, box-shadow 0.2s ease;
  }

  .card:hover {
    border-color: var(--accent);
    box-shadow: 0 0 20px var(--accent-glow);
  }

  .card p {
    font-size: 0.875rem;
    color: var(--text-muted);
  }

  .card p strong {
    color: var(--text);
    font-weight: 600;
  }

  /* Pitch */
  .pitch-statement {
    font-size: 0.95rem;
    line-height: 1.8;
    color: var(--text);
    padding: 1rem 0;
  }

  .pitch-statement .highlight {
    color: var(--accent-light);
    font-weight: 600;
  }

  .pitch-statement .not-conflict {
    color: var(--green);
    font-style: italic;
  }

  /* Bullet lists */
  .bullet-list {
    list-style: none;
    padding: 0;
  }

  .bullet-list li {
    position: relative;
    padding-left: 1.5rem;
    margin-bottom: 0.75rem;
    font-size: 0.875rem;
    color: var(--text-muted);
  }

  .bullet-list li::before {
    content: '\u2022';
    position: absolute;
    left: 0;
    color: var(--accent);
    font-weight: 700;
  }

  .bullet-list li strong {
    color: var(--text);
  }

  /* How to apply */
  .steps {
    counter-reset: step;
    list-style: none;
    padding: 0;
  }

  .steps li {
    counter-increment: step;
    position: relative;
    padding-left: 2.5rem;
    margin-bottom: 1rem;
    font-size: 0.875rem;
    color: var(--text-muted);
  }

  .steps li::before {
    content: counter(step);
    position: absolute;
    left: 0;
    top: 0;
    width: 1.5rem;
    height: 1.5rem;
    border-radius: 50%;
    background: var(--accent-glow);
    border: 1px solid var(--accent);
    color: var(--accent-light);
    font-size: 0.7rem;
    font-weight: 700;
    display: flex;
    align-items: center;
    justify-content: center;
    line-height: 1;
  }

  .steps li strong {
    color: var(--text);
  }

  .steps li code {
    background: var(--bg);
    border: 1px solid var(--border);
    border-radius: 4px;
    padding: 0.1rem 0.4rem;
    font-size: 0.8rem;
    color: var(--amber);
  }

  /* Requirements */
  .req-tag {
    display: inline-block;
    font-size: 0.7rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    padding: 0.15rem 0.5rem;
    border-radius: 3px;
    margin-right: 0.4rem;
    vertical-align: middle;
  }

  .req-tag.must {
    background: rgba(239, 68, 68, 0.15);
    color: #f87171;
    border: 1px solid rgba(239, 68, 68, 0.3);
  }

  .req-tag.prefer {
    background: rgba(251, 191, 36, 0.15);
    color: #fbbf24;
    border: 1px solid rgba(251, 191, 36, 0.3);
  }

  /* Footer */
  .footer {
    text-align: center;
    color: var(--text-muted);
    font-size: 0.75rem;
    padding-top: 2rem;
    border-top: 1px solid var(--border);
  }

  .footer a {
    color: var(--accent-light);
    text-decoration: none;
  }

  .footer a:hover {
    text-decoration: underline;
  }

  /* Subtle animation */
  @keyframes fadeIn {
    from { opacity: 0; transform: translateY(8px); }
    to { opacity: 1; transform: translateY(0); }
  }

  .section {
    animation: fadeIn 0.4s ease both;
  }

  .section:nth-child(2) { animation-delay: 0.05s; }
  .section:nth-child(3) { animation-delay: 0.1s; }
  .section:nth-child(4) { animation-delay: 0.15s; }
  .section:nth-child(5) { animation-delay: 0.2s; }
  .section:nth-child(6) { animation-delay: 0.25s; }
</style>
</head>
<body>
<div class="container">

  <div class="header">
    <h1><span class="at">@unraveldottech</span> is hiring</h1>
    <p class="tagline">serious engineers who take their craft seriously</p>
  </div>

  <div class="section">
    <div class="pitch-statement">
      We lean heavily into using AI.
      <span class="not-conflict">These two sentences are not in conflict
      with each other.</span>
    </div>
  </div>

  <hr class="divider">

  <div class="section">
    <div class="section-title">Why join us</div>
    <ul class="bullet-list">
      <li>The old way of building software is dying. We believe we have a
        <strong>small lead</strong> over other software shops when it comes
        to understanding this change.</li>
      <li>We are <strong>tooling geeks</strong> and believe in staying on
        the cutting edge of technology.</li>
      <li>We are building <strong>Agentic Systems</strong>. This requires
        us to stay on top of advancements in the AI space.</li>
    </ul>
  </div>

  <div class="section">
    <div class="section-title">What we want</div>
    <ul class="bullet-list">
      <li>We are looking for <strong>SDE-1</strong> and <strong>SDE-2</strong>
        engineers specifically, but we'd love to talk to anyone who is
        interested&mdash;even if you are a senior engineer.</li>
      <li><span class="req-tag must">must</span>
        You need to be a <strong>hands-on programmer</strong> and a
        <strong>great communicator</strong>. These are non-negotiable.</li>
      <li><span class="req-tag prefer">prefer</span>
        <strong>Python or TypeScript</strong> expertise&mdash;but a specific
        language stack is not a barrier. Many of us are programming language
        geeks. As long as you are excellent and willing to work on Python or
        TypeScript projects, we're happy to talk to you.</li>
    </ul>
  </div>

  <hr class="divider">

  <div class="section">
    <div class="section-title">How to apply</div>
    <ol class="steps">
      <li>Point an agent to our profiles and ask it to figure out
        <strong>whom to send your resume to</strong>.</li>
      <li>The founder with <strong>PR</strong> in the name accepts your
        resumes on his
        <code>first-name@unravel.tech</code> email address.</li>
      <li>Your subject line should include the words:
        <code>Apply</code>, <code>DSPy</code>, and a
        <strong>third rhyming word</strong> of your choice.</li>
      <li>Your email should contain your <strong>resume as an
        attachment</strong> and should be a <strong>cover letter</strong>
        for why we should hire you.</li>
      <li>The email should be signed by you <strong>and your agent</strong>.
        <br>Example: <em>"Thanks, Vedang (with assistance from
        Claude Code)"</em></li>
    </ol>
  </div>

  <div class="section">
    <div class="card">
      <p>If you are <strong>smart</strong>, <strong>curious</strong>,
        and want to know more&mdash;reach out to us.</p>
    </div>
  </div>

  <div class="footer">
    <p>unravel.tech</p>
  </div>

</div>
</body>
</html>
"""


def register_recruitment_routes(app: FastAPI) -> None:
    """Register the /careers recruitment page route."""

    @app.get("/careers", response_class=HTMLResponse)
    async def careers_page() -> str:
        """Serve the recruitment page."""
        return RECRUITMENT_HTML

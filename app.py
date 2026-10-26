"""Dependency-free browser front end for the existing CatalogIQ agent."""

# Basic local-host front end for manually entering and submitting agent questions.

import asyncio
from html import escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs

from vendor_catalog_agent import ask_agent


PAGE = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>CatalogIQ</title>
  <style>
    :root {
      color-scheme: light;
      --ink: #16213a;
      --muted: #65718a;
      --line: #dce2ec;
      --panel: #ffffff;
      --accent: #0b6b57;
      --accent-hover: #075643;
      --page: #edf1f6;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      min-height: 100vh;
      background:
        linear-gradient(135deg, rgba(11, 107, 87, 0.08), transparent 38%),
        var(--page);
      color: var(--ink);
      font-family: Georgia, "Times New Roman", serif;
    }
    main {
      width: min(860px, calc(100% - 32px));
      margin: 0 auto;
      padding: 52px 0;
    }
    header { margin-bottom: 24px; }
    h1 {
      margin: 0;
      font-size: clamp(2.25rem, 7vw, 4.25rem);
      line-height: 0.95;
      letter-spacing: 0;
    }
    .subtitle {
      max-width: 600px;
      margin: 14px 0 0;
      color: var(--muted);
      font-family: Arial, sans-serif;
      line-height: 1.5;
    }
    form, .answer {
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--panel);
      box-shadow: 0 16px 48px rgba(22, 33, 58, 0.08);
    }
    form { padding: 20px; }
    label {
      display: block;
      margin-bottom: 8px;
      font-family: Arial, sans-serif;
      font-weight: 700;
      font-size: 0.9rem;
    }
    textarea {
      width: 100%;
      min-height: 110px;
      resize: vertical;
      border: 1px solid #bdc6d5;
      border-radius: 6px;
      padding: 14px;
      color: var(--ink);
      background: #fbfcfe;
      font: 1.05rem/1.5 Arial, sans-serif;
    }
    textarea:focus {
      outline: 3px solid rgba(11, 107, 87, 0.16);
      border-color: var(--accent);
    }
    .actions {
      display: flex;
      align-items: center;
      gap: 12px;
      margin-top: 14px;
    }
    button {
      border: 0;
      border-radius: 6px;
      padding: 12px 18px;
      background: var(--accent);
      color: white;
      font: 700 0.95rem Arial, sans-serif;
      cursor: pointer;
    }
    button:hover { background: var(--accent-hover); }
    button:focus-visible { outline: 3px solid rgba(11, 107, 87, 0.25); }
    button:disabled {
      background: #5d786f;
      cursor: wait;
      opacity: 0.88;
    }
    .spinner {
      display: none;
      width: 16px;
      height: 16px;
      border: 2px solid rgba(255, 255, 255, 0.55);
      border-top-color: white;
      border-radius: 50%;
      animation: spin 0.8s linear infinite;
    }
    button:disabled .spinner { display: inline-block; }
    .button-content {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      gap: 8px;
    }
    .loading-message {
      display: none;
      color: var(--accent);
      font: 700 0.86rem Arial, sans-serif;
    }
    .loading-message.is-visible { display: inline; }
    @keyframes spin { to { transform: rotate(360deg); } }
    .examples {
      color: var(--muted);
      font: 0.82rem/1.4 Arial, sans-serif;
    }
    .error {
      margin: 16px 0 0;
      border-left: 4px solid #bd3545;
      padding: 10px 12px;
      color: #861d29;
      background: #fff1f3;
      font-family: Arial, sans-serif;
    }
    .answer {
      margin-top: 20px;
      padding: 24px;
    }
    .answer h2 {
      margin: 0 0 14px;
      font: 700 1.15rem Arial, sans-serif;
    }
    .answer pre {
      margin: 0;
      white-space: pre-wrap;
      overflow-wrap: anywhere;
      font: 0.95rem/1.62 Arial, sans-serif;
    }
    @media (max-width: 560px) {
      main { width: min(100% - 20px, 860px); padding: 28px 0; }
      .actions { align-items: stretch; flex-direction: column; }
      button { width: 100%; }
    }
  </style>
</head>
<body>
  <main>
    <header>
      <h1>CatalogIQ</h1>
      <p class="subtitle">Compare products across your vendor catalogs on price, quality, and material.</p>
    </header>
    <form method="post" action="/">
      <label for="question">What would you like to compare?</label>
      <textarea id="question" name="question" maxlength="2000" required placeholder="Compare holiday string lights across the vendors.">{question}</textarea>
      <div class="actions">
        <button id="ask-button" type="submit">
          <span class="button-content"><span class="spinner" aria-hidden="true"></span><span id="button-label">Ask CatalogIQ</span></span>
        </button>
        <span id="loading-message" class="loading-message" role="status" aria-live="polite">CatalogIQ is comparing vendor data...</span>
        <span class="examples">Try holiday string lights, restaurant nitrile gloves, or brake pads.</span>
      </div>
    </form>
    {error}
    {answer}
  </main>
  <script>
    const form = document.querySelector("form");
    const button = document.getElementById("ask-button");
    const buttonLabel = document.getElementById("button-label");
    const loadingMessage = document.getElementById("loading-message");

    form.addEventListener("submit", (event) => {
      if (!form.checkValidity()) return;
      event.preventDefault();
      button.disabled = true;
      button.setAttribute("aria-busy", "true");
      buttonLabel.textContent = "Thinking...";
      loadingMessage.classList.add("is-visible");
      form.submit();
    });
  </script>
</body>
</html>"""


def render_page(question="", answer=None, error=None):
    error_html = f'<p class="error" role="alert">{escape(error)}</p>' if error else ""
    answer_html = ""
    if answer is not None:
        answer_html = (
            '<section class="answer" aria-live="polite">'
            '<h2>Agent response</h2>'
            f"<pre>{escape(answer)}</pre></section>"
        )
    return (
        PAGE.replace("{question}", escape(question))
        .replace("{error}", error_html)
        .replace("{answer}", answer_html)
    )


class CatalogIQHandler(BaseHTTPRequestHandler):
    """Serve a simple local form and delegate answers to the existing agent."""

    def do_GET(self):
        if self.path != "/":
            self.send_error(404)
            return
        self._send_html(render_page())

    def do_POST(self):
        if self.path != "/":
            self.send_error(404)
            return

        try:
            content_length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            content_length = 0
        if content_length > 16_384:
            self.send_error(413, "Question is too long")
            return

        form = parse_qs(self.rfile.read(content_length).decode("utf-8"))
        question = form.get("question", [""])[0].strip()
        if not question:
            self._send_html(render_page(error="Enter a question before submitting."), 400)
            return

        try:
            answer = asyncio.run(ask_agent(question))
        except Exception as error:
            message = str(error) or "The agent could not complete the request."
            self._send_html(render_page(question, error=message), 500)
            return

        self._send_html(render_page(question, answer=answer))

    def _send_html(self, content, status=200):
        encoded = content.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def log_message(self, format, *args):
        print(f"[web] {format % args}")


if __name__ == "__main__":
    server = ThreadingHTTPServer(("127.0.0.1", 5000), CatalogIQHandler)
    print("CatalogIQ front end: http://127.0.0.1:5000")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()

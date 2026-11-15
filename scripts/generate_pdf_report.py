import os
import sys
import subprocess

# Convert Markdown to HTML
md_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "REPORT.md"))
html_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "report.html"))
pdf_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "EventSphere_Submission_Report.pdf"))

with open(md_path, "r", encoding="utf-8") as f:
    md_content = f.read()

# Build HTML with GitHub Markdown styling and CSS
html_content = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>IT4123 ICA 02 - EventSphere Multi-Agent System Report</title>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/github-markdown-css@5.5.1/github-markdown.min.css">
<style>
    body {{
        box-sizing: border-box;
        min-width: 200px;
        max-width: 980px;
        margin: 0 auto;
        padding: 45px;
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
    }}
    table {{
        border-collapse: collapse;
        width: 100%;
        margin-bottom: 16px;
    }}
    th, td {{
        border: 1px solid #d0d7de;
        padding: 8px 12px;
        text-align: left;
    }}
    th {{
        background-color: #f6f8fa;
    }}
    pre {{
        background-color: #f6f8fa;
        padding: 16px;
        border-radius: 6px;
        overflow-x: auto;
    }}
    code {{
        background-color: rgba(175, 184, 193, 0.2);
        padding: 2px 4px;
        border-radius: 4px;
        font-family: ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, monospace;
    }}
    h1, h2, h3 {{
        border-bottom: 1px solid #d0d7de;
        padding-bottom: 6px;
    }}
</style>
</head>
<body class="markdown-body">
<pre style="white-space: pre-wrap; font-family: inherit; background: transparent; border: none; padding: 0;">
{md_content}
</pre>
</body>
</html>
"""

with open(html_path, "w", encoding="utf-8") as f:
    f.write(html_content)

print(f"Generated {html_path}")

# Run headless Edge to generate PDF
edge_path = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
if os.path.exists(edge_path):
    cmd = [
        edge_path,
        "--headless",
        "--disable-gpu",
        f"--print-to-pdf={pdf_path}",
        html_path
    ]
    try:
        subprocess.run(cmd, check=True)
        print(f"Generated PDF successfully: {pdf_path}")
    except Exception as e:
        print(f"Headless print error: {e}")
else:
    print("Edge not found at standard path")

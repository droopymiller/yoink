import os
import argparse

def generate_index(pdf_dir: str):
    pdf_dir = os.path.abspath(pdf_dir)
    output_file = os.path.join(pdf_dir, "index.html")
    file_extensions = (".html")

    if not os.path.isdir(pdf_dir):
        print(f"❌ Error: {pdf_dir} is not a valid directory.")
        return

    # Gather files
    pdf_files = sorted(
        [f for f in os.listdir(pdf_dir) if not f.lower().endswith(file_extensions)],
        key=str.casefold
    )

    # Generate HTML
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>PDF Index</title>
  <style>
    body {{ font-family: sans-serif; margin: 2em; }}
    input[type="text"] {{ width: 300px; padding: 8px; margin-bottom: 20px; }}
    ul {{ list-style-type: none; padding: 0; }}
    li {{ margin: 6px 0; }}
    a {{ text-decoration: none; color: #0066cc; }}
    a:hover {{ text-decoration: underline; }}
  </style>
  <script>
    window.onload = () => {{
        document.getElementById('search').focus();
        }};
    function search() {{
      const input = document.getElementById('search').value.toLowerCase();
      const items = document.querySelectorAll('li');
      items.forEach(item => {{
        const text = item.textContent.toLowerCase();
        item.style.display = text.includes(input) ? '' : 'none';
      }});
    }}
  </script>
</head>
<body>
  <h1>{os.path.basename(pdf_dir)}</h1>
  <input type="text" id="search" onkeyup="search()" placeholder="Search PDFs...">
  <ul>
"""

    for filename in pdf_files:
        html += f'    <li><a href="{filename}">{filename}</a></li>\n'

    html += """  </ul>
</body>
</html>
"""

    # Write to file
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"✅ index.html generated with {len(pdf_files)} files.")
    print(f"📂 Location: {output_file}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate a searchable PDF index page.")
    parser.add_argument(
        "directory",
        nargs="?",
        default=".",
        help="Path to the folder containing PDFs (default: current directory)"
    )

    args = parser.parse_args()
    generate_index(args.directory)

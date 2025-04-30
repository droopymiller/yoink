import os
import yaml
import requests
import hashlib
import shutil
import argparse
import re
from datetime import datetime
from urllib.parse import quote_plus
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm
from PyPDF2 import PdfReader


def load_downloads_config(yaml_file):
    """
    Load the raw YAML configuration file.

    Args:
        yaml_file (str): Path to the YAML file.

    Returns:
        dict: Parsed configuration.
    """
    with open(yaml_file, 'r') as f:
        return yaml.safe_load(f)


def validate_config(config):
    """
    Validates the structure of the parsed YAML configuration,
    including schema version and per-category rules.

    Args:
        config (dict): Parsed configuration dictionary.

    Raises:
        ValueError: If required fields are missing or incorrectly formatted.
    """
    if not isinstance(config, dict):
        raise ValueError("Top-level YAML structure must be a dictionary.")

    if 'version' not in config:
        raise ValueError("Missing 'version' field in YAML.")

    if config['version'] != 1:
        raise ValueError(f"Unsupported config version: {config['version']}")

    if 'downloads' not in config:
        raise ValueError("Missing 'downloads' section in YAML.")

    downloads = config['downloads']

    if not isinstance(downloads, dict):
        raise ValueError("'downloads' section must be a dictionary of categories.")

    for category, settings in downloads.items():
        if not isinstance(settings, dict):
            raise ValueError(f"Category '{category}' must be a dictionary.")

        if 'folder' not in settings or not isinstance(settings['folder'], str):
            raise ValueError(f"Category '{category}' is missing a valid 'folder' string.")

        if 'base_url' not in settings or not isinstance(settings['base_url'], str):
            raise ValueError(f"Category '{category}' is missing a valid 'base_url' string.")

        if 'filename_mode' in settings and settings['filename_mode'] not in ['item', 'title']:
            raise ValueError(f"Category '{category}' has invalid 'filename_mode'. Must be 'item' or 'title'.")

        if 'items' not in settings or not isinstance(settings['items'], list) or not all(isinstance(i, str) for i in settings['items']):
            raise ValueError(f"Category '{category}' must have a list of item strings under 'items'.")


def prepare_folders(base_folder):
    """
    Create necessary directories for storing and archiving downloads.

    Args:
        base_folder (str): Path to the main folder for storing files.

    Returns:
        str: Path to the archive subfolder.
    """
    os.makedirs(base_folder, exist_ok=True)
    archive_path = os.path.join(base_folder, 'archive')
    os.makedirs(archive_path, exist_ok=True)
    return archive_path


def file_checksum(path):
    """
    Calculate the SHA256 checksum of a file.

    Args:
        path (str): Path to the file.

    Returns:
        str: SHA256 checksum as a hexadecimal string.
    """
    sha256 = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(4096), b''):
            sha256.update(chunk)
    return sha256.hexdigest()


def download_file(url, dest_path):
    """
    Download a file from a URL to a local path.

    Args:
        url (str): The file URL.
        dest_path (str): Local destination path.

    Returns:
        bool: True if download succeeded, False otherwise.
    """
    resp = requests.get(url, stream=True)
    if resp.status_code == 200:
        with open(dest_path, 'wb') as f:
            for chunk in resp.iter_content(1024):
                f.write(chunk)
        return True
    return False


def resolve_pdf_url(base_url, item):
    """
    Resolve the final PDF URL for a given item using TI's redirect mechanism.

    Args:
        base_url (str): The base search URL.
        item (str): The item identifier (e.g., part number or app note).

    Returns:
        str or None: The final PDF URL, or None if not found.
    """
    full_url = f"{base_url}{quote_plus(item)}"
    resp = requests.get(full_url, allow_redirects=True)
    if resp.status_code == 200 and ".pdf" in resp.url:
        return resp.url
    return None


def get_pdf_title(path):
    """
    Extracts the PDF title from metadata or returns None if not found.

    Args:
        path (str): Path to the PDF file.

    Returns:
        str or None: Title string or None.
    """
    try:
        reader = PdfReader(path)
        title = reader.metadata.get('/Title')
        if title:
            return re.sub(r'[\\/*?:"<>|]', "", title).strip()
    except Exception:
        pass
    return None


def process_item(category, item, base_url, folder, archive_folder, filename_mode):
    """
    Handle downloading, updating, and archiving a document for a single item.

    Args:
        category (str): The category name (e.g., 'parts').
        item (str): The item identifier.
        base_url (str): The base search URL.
        folder (str): Path to the folder where the file will be stored.
        archive_folder (str): Path to the folder where old files will be archived.
        filename_mode (str): Naming mode for files ('item' or 'title').
    """
    print(f"[{category}] [{item}] Checking...")

    resolved_url = resolve_pdf_url(base_url, item)
    if not resolved_url:
        print(f"[{category}] [{item}] PDF URL not found.")
        return

    temp_file = os.path.join(folder, f"{item}_new.pdf")

    if not download_file(resolved_url, temp_file):
        print(f"[{category}] [{item}] Download failed.")
        return

    if filename_mode == "title":
        title = get_pdf_title(temp_file)
        if not title:
            print(f"[{category}] [{item}] No title found, using item as filename.")
            title = item
        final_name = f"{title}.pdf"
    else:
        final_name = f"{item}.pdf"

    final_file = os.path.join(folder, final_name)

    if os.path.exists(final_file):
        old_hash = file_checksum(final_file)
        new_hash = file_checksum(temp_file)
        if old_hash != new_hash:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            archived_name = os.path.join(archive_folder, f"{os.path.splitext(final_name)[0]}_{timestamp}.pdf")
            shutil.move(final_file, archived_name)
            shutil.move(temp_file, final_file)
            print(f"[{category}] [{item}] Updated. Old version archived.")
        else:
            os.remove(temp_file)
            print(f"[{category}] [{item}] Up to date.")
    else:
        shutil.move(temp_file, final_file)
        print(f"[{category}] [{item}] Downloaded.")


def main():
    """
    Entry point for the script. Parses arguments, loads config,
    validates schema, and coordinates document downloads.
    """
    parser = argparse.ArgumentParser(description="Download categorized documents from TI.")
    parser.add_argument('--input', type=str, default='downloads.yaml', help='YAML config file (default: downloads.yaml)')
    parser.add_argument('--threads', type=int, default=4, help='Max concurrent downloads (default: 4)')
    args = parser.parse_args()

    raw_config = load_downloads_config(args.input)
    validate_config(raw_config)
    config = raw_config['downloads']

    tasks = []
    with ThreadPoolExecutor(max_workers=args.threads) as executor:
        for category, details in config.items():
            folder = details['folder']
            base_url = details['base_url']
            filename_mode = details.get('filename_mode', 'item')
            items = details['items']
            archive_folder = prepare_folders(folder)

            for item in items:
                future = executor.submit(
                    process_item, category, item, base_url, folder, archive_folder, filename_mode
                )
                tasks.append(future)

        for _ in tqdm(as_completed(tasks), total=len(tasks), desc="Processing", unit="item"):
            pass

    print("✅ All downloads processed.")


if __name__ == "__main__":
    main()

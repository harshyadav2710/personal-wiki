import os
import re
import time
import zipfile
import requests
from urllib.parse import quote


# ============================================================
# SETTINGS
# ============================================================

OUTPUT_DIR = "public_domain_stories"
ZIP_NAME = "public_domain_stories.zip"

MAX_LINES = 5000

SEARCH_TIMEOUT = 30
DOWNLOAD_TIMEOUT = 120

# Delay between searches/downloads
DELAY = 0.5

os.makedirs(OUTPUT_DIR, exist_ok=True)


# ============================================================
# 200 STORY TITLES
# ============================================================

STORIES = [
    "The Gift of the Magi",
    "The Last Leaf",
    "After Twenty Years",
    "The Ransom of Red Chief",
    "The Cop and the Anthem",
    "A Retrieved Reformation",
    "The Green Door",
    "The Furnished Room",
    "The Pendulum",
    "The Trimmed Lamp",

    "The Tell-Tale Heart",
    "The Black Cat",
    "The Cask of Amontillado",
    "The Pit and the Pendulum",
    "The Gold-Bug",
    "The Purloined Letter",
    "Ligeia",
    "The Fall of the House of Usher",
    "The Masque of the Red Death",
    "The Murders in the Rue Morgue",

    "The Monkey's Paw",
    "The Open Window",
    "Tobermory",
    "Sredni Vashtar",
    "The Schartz-Metterklume Method",
    "The Lumber Room",
    "Gabriel-Ernest",
    "The Story-Teller",
    "The Interlopers",
    "The Unrest-Cure",

    "Rip Van Winkle",
    "The Legend of Sleepy Hollow",
    "The Devil and Tom Walker",
    "The Spectre Bridegroom",
    "The Adventure of the German Student",
    "Dolph Heyliger",
    "Kidd the Pirate",
    "The Broken Heart",
    "The Wife",
    "Westminster Abbey",

    "The Mutability of Literature",
    "Adventure of My Aunt",
    "The Boar's Head Tavern",
    "The Stout Gentleman",
    "The Art of Bookmaking",
    "Mountjoy",
    "The Adventure of the Mysterious Picture",
    "Philip of Pokanoket",
    "The Voyage",
    "Wolfert Webber",

    "A Scandal in Bohemia",
    "The Red-Headed League",
    "A Case of Identity",
    "The Boscombe Valley Mystery",
    "The Five Orange Pips",
    "The Man with the Twisted Lip",
    "The Blue Carbuncle",
    "The Speckled Band",
    "The Engineer's Thumb",
    "The Noble Bachelor",

    "The Beryl Coronet",
    "The Copper Beeches",
    "Silver Blaze",
    "The Yellow Face",
    "The Stockbroker's Clerk",
    "The Gloria Scott",
    "The Musgrave Ritual",
    "The Reigate Puzzle",
    "The Crooked Man",
    "The Resident Patient",

    "The Greek Interpreter",
    "The Naval Treaty",
    "The Final Problem",
    "The Empty House",
    "The Norwood Builder",
    "The Dancing Men",
    "The Solitary Cyclist",
    "Black Peter",
    "Charles Augustus Milverton",
    "The Six Napoleons",

    "The Three Students",
    "The Golden Pince-Nez",
    "The Missing Three-Quarter",
    "The Abbey Grange",
    "The Second Stain",
    "Wisteria Lodge",
    "The Bruce-Partington Plans",
    "The Devil's Foot",
    "The Red Circle",
    "Lady Frances Carfax",

    "The Dying Detective",
    "The Disappearance of Lady Frances Carfax",
    "The Sussex Vampire",
    "The Creeping Man",
    "The Lion's Mane",
    "The Veiled Lodger",
    "Shoscombe Old Place",
    "The Retired Colourman",
    "The Cardboard Box",
    "The Blanched Soldier",

    "The Damned Thing",
    "An Occurrence at Owl Creek Bridge",
    "Chickamauga",
    "The Boarded Window",
    "One Summer Night",
    "A Horseman in the Sky",
    "Parker Adderson, Philosopher",
    "The Suitable Surroundings",
    "The Death of Halpin Frayser",
    "Moxon's Master",

    "The Moonlit Road",
    "Present at a Hanging",
    "A Watcher by the Dead",
    "The Secret of Macarger's Gulch",
    "The Middle Toe of the Right Foot",
    "The Realm of the Unreal",
    "The Applicant",
    "Beyond the Wall",
    "The Stranger",
    "The Night-Doings at Deadman's",

    "The Yellow Wallpaper",
    "The Giant Wisteria",
    "Three Thanksgivings",
    "Turned",
    "If I Were a Man",
    "The Rocking-Horse Winner",
    "Odour of Chrysanthemums",
    "The Prussian Officer",
    "The Horse Dealer's Daughter",
    "England, My England",

    "Tickets, Please",
    "The Blind Man",
    "New Eve and Old Adam",
    "Sun",
    "The Lovely Lady",
    "The Fox",
    "The Virgin and the Gypsy",
    "The Ladybird",
    "The Captain's Doll",
    "Rawdon's Roof",

    "The White Stocking",
    "You Touched Me",
    "Wintry Peacock",
    "The Shades of Spring",
    "Samson and Delilah",
    "Daughters of the Vicar",
    "Monkey Nuts",
    "Things",
    "Love Among the Haystacks",
    "The Merry-Go-Round",

    "The Happy Prince",
    "The Nightingale and the Rose",
    "The Selfish Giant",
    "The Devoted Friend",
    "The Remarkable Rocket",
    "The Young King",
    "The Birthday of the Infanta",
    "The Fisherman and His Soul",
    "The Star-Child",
    "Lord Arthur Savile's Crime",

    "The Canterville Ghost",
    "The Sphinx Without a Secret",
    "The Model Millionaire",
    "The Portrait of Mr. W.H.",
    "Markheim",
    "The Sire de Malétroit's Door",
    "The Pavilion on the Links",
    "Thrawn Janet",
    "Will o' the Mill",
    "Olalla",

    "The Merry Men",
    "The Beach of Falesá",
    "The Bottle Imp",
    "The Isle of Voices",
    "Wee Willie Winkie",
    "The Man Who Would Be King",
    "Baa Baa, Black Sheep",
    "The Phantom Rickshaw",
    "The Strange Ride of Morrowbie Jukes",
    "The Gardener",

    "Wireless",
    "The Door in the Wall",
    "The Country of the Blind",
    "The Crystal Egg",
    "The Star",
    "The Cone",
    "A Dream of Armageddon",
    "The New Accelerator",
    "The Stolen Bacillus",
    "The Lord of the Dynamos",

    "The Magic Shop",
    "The Valley of Spiders",
    "Jimmy Goggles the God",
    "The Empire of the Ants",
    "The Purple Pileus",
    "The Remarkable Case of Davidson's Eyes",
    "The Truth About Pyecraft",
    "The Red Room",
    "Pollock and the Porroh Man",
    "The Story of the Late Mr. Elvesham",
]


# ============================================================
# CHECK NUMBER OF TITLES
# ============================================================

print("=" * 70)
print("PUBLIC DOMAIN STORY DOWNLOADER")
print("=" * 70)

print(f"Titles in list: {len(STORIES)}")

if len(STORIES) != 200:
    print("WARNING: The list does not contain exactly 200 titles.")


# ============================================================
# CLEAN TITLE FOR FILENAME
# ============================================================

def clean_filename(title):

    # Remove apostrophes
    title = title.replace("'", "")

    # Replace special characters with -
    title = re.sub(r"[^A-Za-z0-9]+", "-", title)

    # Remove duplicate -
    title = re.sub(r"-+", "-", title)

    # Remove - from beginning/end
    title = title.strip("-")

    return title


# ============================================================
# SEARCH GUTENBERG
# ============================================================

def search_gutenberg(title):

    url = "https://gutendex.com/books/"

    params = {
        "search": title
    }

    try:

        response = requests.get(
            url,
            params=params,
            timeout=SEARCH_TIMEOUT
        )

        response.raise_for_status()

        data = response.json()

        results = data.get("results", [])

        if not results:
            return None

        title_lower = title.lower().strip()

        # First try exact title
        for book in results:

            book_title = book.get("title", "").lower().strip()

            if book_title == title_lower:
                return book

        # Then try title contained in result
        for book in results:

            book_title = book.get("title", "").lower().strip()

            if title_lower in book_title:
                return book

        # Otherwise first result
        return results[0]

    except requests.exceptions.Timeout:

        print("    Search timeout")

        return None

    except requests.exceptions.RequestException as e:

        print(f"    Search error: {e}")

        return None

    except Exception as e:

        print(f"    Unexpected search error: {e}")

        return None


# ============================================================
# FIND TEXT FORMAT
# ============================================================

def get_text_url(book):

    formats = book.get("formats", {})

    preferred = [
        "text/plain; charset=utf-8",
        "text/plain",
    ]

    for format_name in preferred:

        if format_name in formats:

            return formats[format_name]

    # Fallback
    for format_name, url in formats.items():

        if format_name.startswith("text/plain"):

            return url

    return None


# ============================================================
# DOWNLOAD TEXT
# ============================================================

def download_text(url):

    try:

        response = requests.get(
            url,
            timeout=DOWNLOAD_TIMEOUT
        )

        response.raise_for_status()

        response.encoding = "utf-8"

        return response.text

    except requests.exceptions.Timeout:

        print("    Download timeout")

        return None

    except requests.exceptions.RequestException as e:

        print(f"    Download error: {e}")

        return None

    except Exception as e:

        print(f"    Unexpected download error: {e}")

        return None


# ============================================================
# SAVE STORY
# ============================================================

def save_story(title, text, number):

    clean_title = clean_filename(title)

    # 5-digit number
    filename = f"{number:05d}-{clean_title}.txt"

    path = os.path.join(
        OUTPUT_DIR,
        filename
    )

    with open(
        path,
        "w",
        encoding="utf-8"
    ) as file:

        file.write(text)

    return path


# ============================================================
# DOWNLOAD ONE STORY
# ============================================================

def download_story(title, number):

    print()
    print("-" * 70)
    print(f"[{number:03d}/200] {title}")
    print("-" * 70)

    # --------------------------------------------------------
    # Search
    # --------------------------------------------------------

    print("Searching Gutenberg...")

    book = search_gutenberg(title)

    if book is None:

        print("[NOT FOUND]")

        return False

    book_id = book.get("id")
    matched_title = book.get("title", "")

    print(f"Gutenberg ID : {book_id}")
    print(f"Matched title: {matched_title}")

    # --------------------------------------------------------
    # Find TXT
    # --------------------------------------------------------

    text_url = get_text_url(book)

    if text_url is None:

        print("[NO TXT FORMAT]")

        return False

    print("Downloading...")

    # --------------------------------------------------------
    # Download
    # --------------------------------------------------------

    text = download_text(text_url)

    if text is None:

        return False

    # --------------------------------------------------------
    # Count lines
    # --------------------------------------------------------

    lines = len(text.splitlines())

    print(f"Line count: {lines}")

    # --------------------------------------------------------
    # Check maximum lines
    # --------------------------------------------------------

    if lines > MAX_LINES:

        print(
            f"[SKIPPED] More than {MAX_LINES} lines"
        )

        return False

    # --------------------------------------------------------
    # Save
    # --------------------------------------------------------

    path = save_story(
        title,
        text,
        number
    )

    print(f"[SAVED] {path}")

    return True


# ============================================================
# CREATE ZIP
# ============================================================

def create_zip():

    print()
    print("=" * 70)
    print("CREATING ZIP FILE")
    print("=" * 70)

    if not os.path.exists(OUTPUT_DIR):

        print("Output folder does not exist.")

        return

    files = []

    for filename in os.listdir(OUTPUT_DIR):

        path = os.path.join(
            OUTPUT_DIR,
            filename
        )

        if os.path.isfile(path):

            files.append(path)

    if not files:

        print("No downloaded files.")

        return

    with zipfile.ZipFile(
        ZIP_NAME,
        "w",
        compression=zipfile.ZIP_DEFLATED
    ) as zip_file:

        for path in files:

            zip_file.write(
                path,
                arcname=os.path.basename(path)
            )

    print(f"ZIP created: {ZIP_NAME}")
    print(f"Files added: {len(files)}")


# ============================================================
# MAIN
# ============================================================

def main():

    successful = 0
    failed = []

    total = len(STORIES)

    for index, title in enumerate(
        STORIES,
        start=1
    ):

        try:

            result = download_story(
                title,
                index
            )

            if result:

                successful += 1

            else:

                failed.append(title)

        except KeyboardInterrupt:

            print()
            print("Stopped by user.")

            break

        except Exception as e:

            print(
                f"Unexpected error for "
                f"{title}: {e}"
            )

            failed.append(title)

        time.sleep(DELAY)

    # --------------------------------------------------------
    # ZIP
    # --------------------------------------------------------

    create_zip()

    # --------------------------------------------------------
    # Save failed titles
    # --------------------------------------------------------

    if failed:

        with open(
            "failed_books.txt",
            "w",
            encoding="utf-8"
        ) as file:

            for title in failed:

                file.write(
                    title + "\n"
                )

    # --------------------------------------------------------
    # Summary
    # --------------------------------------------------------

    print()
    print("=" * 70)
    print("FINISHED")
    print("=" * 70)

    print(f"Requested : {total}")
    print(f"Downloaded: {successful}")
    print(f"Failed    : {len(failed)}")

    print()
    print(f"Output folder: {OUTPUT_DIR}")
    print(f"ZIP file     : {ZIP_NAME}")

    if failed:

        print()
        print("Failed/skipped titles:")
        print("-" * 70)

        for title in failed:

            print(title)

        print()
        print(
            "Full failed list saved to "
            "failed_books.txt"
        )


# ============================================================
# START PROGRAM
# ============================================================

if __name__ == "__main__":
    main()
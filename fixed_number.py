import os
import re


# ============================================================
# FOLDER
# ============================================================

FOLDER = os.path.join(
    "source_files",
    "gutenberg"
)


# ============================================================
# CHECK FOLDER
# ============================================================

if not os.path.exists(FOLDER):

    print("ERROR: Folder not found:")
    print(os.path.abspath(FOLDER))
    input("\nPress Enter to exit...")
    exit()


# ============================================================
# GET TXT FILES
# ============================================================

files = [
    filename
    for filename in os.listdir(FOLDER)
    if filename.lower().endswith(".txt")
]


# ============================================================
# SORT FILES
# ============================================================
#
# We sort using:
#
# 1. Existing number
# 2. Filename
#
# Example:
#
# 00001-A.txt
# 00001-B.txt
# 00002-C.txt
# 00004-D.txt
#
# ============================================================

def sort_key(filename):

    match = re.match(
        r"^(\d+)-(.*)$",
        filename
    )

    if match:

        number = int(match.group(1))
        title = match.group(2).lower()

        return (
            number,
            title
        )

    # Files without numbers go at the end
    return (
        999999999,
        filename.lower()
    )


files.sort(key=sort_key)


# ============================================================
# DISPLAY
# ============================================================

print("=" * 70)
print("GUTENBERG FILE NUMBER FIXER")
print("=" * 70)

print()
print("Folder:")
print(os.path.abspath(FOLDER))

print()
print(f"TXT files found: {len(files)}")

print()


# ============================================================
# SHOW PREVIEW
# ============================================================

print("=" * 70)
print("PREVIEW")
print("=" * 70)

for index, filename in enumerate(
    files,
    start=1
):

    match = re.match(
        r"^(\d+)-(.*)$",
        filename
    )

    if match:

        old_number = match.group(1)
        title = match.group(2)

    else:

        old_number = "NONE"
        title = filename

    new_filename = (
        f"{index:05d}-{title}"
    )

    print(
        f"{old_number:>8} -> "
        f"{index:05d} | "
        f"{title}"
    )


# ============================================================
# ASK CONFIRMATION
# ============================================================

print()

answer = input(
    "Do you want to rename these files? (yes/no): "
)

if answer.lower() not in [
    "yes",
    "y"
]:

    print()
    print("Cancelled.")
    input("Press Enter to exit...")
    exit()


# ============================================================
# STEP 1:
# TEMPORARY NAMES
# ============================================================
#
# IMPORTANT:
#
# We cannot directly rename:
#
# 00001-A.txt -> 00001-A.txt
# 00001-B.txt -> 00002-B.txt
#
# because Windows can encounter filename conflicts.
#
# So first every file gets a temporary name.
#
# ============================================================

print()
print("=" * 70)
print("STEP 1: Creating temporary names")
print("=" * 70)

temporary_files = []


for index, filename in enumerate(
    files,
    start=1
):

    old_path = os.path.join(
        FOLDER,
        filename
    )

    temp_filename = (
        f"__TEMP_GUTENBERG_{index:06d}__.txt"
    )

    temp_path = os.path.join(
        FOLDER,
        temp_filename
    )

    os.rename(
        old_path,
        temp_path
    )

    temporary_files.append(
        (
            temp_path,
            filename
        )
    )

    print(
        f"{index:05d}: "
        f"{filename}"
    )


# ============================================================
# STEP 2:
# FINAL NAMES
# ============================================================

print()
print("=" * 70)
print("STEP 2: Assigning unique numbers")
print("=" * 70)


for new_number, (
    temp_path,
    old_filename
) in enumerate(
    temporary_files,
    start=1
):

    # --------------------------------------------------------
    # Remove old number
    # --------------------------------------------------------

    match = re.match(
        r"^\d+-(.*)$",
        old_filename
    )

    if match:

        title = match.group(1)

    else:

        title = old_filename

    # --------------------------------------------------------
    # Create new filename
    # --------------------------------------------------------

    new_filename = (
        f"{new_number:05d}-{title}"
    )

    new_path = os.path.join(
        FOLDER,
        new_filename
    )

    # --------------------------------------------------------
    # Rename
    # --------------------------------------------------------

    os.rename(
        temp_path,
        new_path
    )

    print(
        f"{new_number:05d} -> "
        f"{new_filename}"
    )


# ============================================================
# VERIFY
# ============================================================

print()
print("=" * 70)
print("VERIFYING")
print("=" * 70)


final_files = [
    filename
    for filename in os.listdir(FOLDER)
    if filename.lower().endswith(".txt")
]


numbers = []
duplicates = []


for filename in final_files:

    match = re.match(
        r"^(\d+)-",
        filename
    )

    if match:

        number = int(
            match.group(1)
        )

        if number in numbers:

            duplicates.append(
                filename
            )

        numbers.append(number)


numbers.sort()


# ============================================================
# RESULT
# ============================================================

print()

if duplicates:

    print("WARNING: Duplicate numbers found!")

    for filename in duplicates:

        print(
            f"  {filename}"
        )

else:

    print(
        "SUCCESS: No duplicate numbers found."
    )


print()
print(
    f"Total TXT files: {len(final_files)}"
)

if numbers:

    print(
        f"First ID: {numbers[0]:05d}"
    )

    print(
        f"Last ID : {numbers[-1]:05d}"
    )


print()
print("=" * 70)
print("DONE")
print("=" * 70)

input("\nPress Enter to exit...")
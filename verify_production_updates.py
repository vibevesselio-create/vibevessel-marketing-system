#!/usr/bin/env python3
"""Verify production updates: Notion, files, and Eagle."""
import sys
from pathlib import Path

try:
    from shared_core.notion.token_manager import get_notion_client
    from unified_config import get_unified_config
except ImportError:
    print("ERROR: Could not import required modules")
    sys.exit(1)


def get_prop_value(prop):
    """Extract value from Notion property."""
    if not prop:
        return None
    prop_type = prop.get("type")
    if prop_type == "title":
        title_array = prop.get("title", [])
        if title_array:
            return title_array[0].get("plain_text", "")
    elif prop_type == "rich_text":
        rich_text_array = prop.get("rich_text", [])
        if rich_text_array:
            return rich_text_array[0].get("plain_text", "")
    elif prop_type == "url":
        return prop.get("url")
    elif prop_type == "checkbox":
        return prop.get("checkbox", False)
    return None


def verify_notion_updates(page_id: str):
    """Verify Notion page has fingerprint and file paths updated."""
    print(f"\n🔍 Verifying Notion page: {page_id}")
    print("=" * 80)

    notion = get_notion_client()
    if not notion:
        print("ERROR: Notion client not available")
        return False

    try:
        page = notion.pages.retrieve(page_id=page_id)
        props = page.get("properties", {})

        title = get_prop_value(props.get("Title") or props.get("title"))
        artist = get_prop_value(props.get("Artist Name") or props.get("Artist"))

        print(f"Title: {title}")
        print(f"Artist: {artist}")

        # Check fingerprint
        fingerprint = None
        for fp_prop_name in ["Fingerprint", "fingerprint", "Fingerprint SHA", "fingerprint_sha"]:
            fp_prop = props.get(fp_prop_name)
            if fp_prop:
                fingerprint = get_prop_value(fp_prop)
                if fingerprint:
                    print(f"✅ Fingerprint ({fp_prop_name}): {fingerprint[:64]}...")
                    break

        if not fingerprint:
            print("❌ Fingerprint: NOT FOUND")

        # Check file paths
        wav_path = get_prop_value(props.get("WAV File Path"))
        aiff_path = get_prop_value(props.get("AIFF File Path"))
        m4a_path = get_prop_value(props.get("M4A File Path"))

        file_paths = []
        if wav_path:
            print(f"✅ WAV File Path: {wav_path}")
            file_paths.append(("WAV", wav_path))
        if aiff_path:
            print(f"✅ AIFF File Path: {aiff_path}")
            file_paths.append(("AIFF", aiff_path))
        if m4a_path:
            print(f"✅ M4A File Path: {m4a_path}")
            file_paths.append(("M4A", m4a_path))

        if not file_paths:
            print("⚠️  No file paths found")

        # Check Eagle File ID
        eagle_id = get_prop_value(props.get("Eagle File ID"))
        if eagle_id:
            print(f"✅ Eagle File ID: {eagle_id}")
        else:
            print("⚠️  Eagle File ID: NOT FOUND")

        # Check DL status
        dl = props.get("DL", {}).get("checkbox", False) if props.get("DL") else False
        print(f"DL Status: {'✅ True' if dl else '⚠️  False'}")

        return {
            "has_fingerprint": bool(fingerprint),
            "fingerprint": fingerprint,
            "file_paths": file_paths,
            "has_eagle_id": bool(eagle_id),
            "eagle_id": eagle_id,
            "dl_status": dl
        }

    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
        return None


def verify_file_fingerprint(file_path: str):
    """Verify file has fingerprint embedded."""
    if not file_path:
        return None

    file_path_obj = Path(file_path)
    if not file_path_obj.exists():
        print(f"⚠️  File does not exist: {file_path}")
        return None

    print(f"\n🔍 Verifying file: {file_path}")
    print("=" * 80)

    try:
        import mutagen
        from mutagen.id3 import ID3NoHeaderError

        audio_file = mutagen.File(str(file_path_obj))
        if not audio_file:
            print("⚠️  Could not read audio file metadata")
            return None

        # Check for fingerprint in common tags
        fingerprint = None
        for tag_name in ["TXXX:FINGERPRINT", "TXXX:Fingerprint", "TXXX:FINGERPRINT SHA", "TXXX:Fingerprint SHA"]:
            if tag_name in audio_file:
                fingerprint = str(audio_file[tag_name][0])
                print(f"✅ Found fingerprint tag ({tag_name}): {fingerprint[:64]}...")
                break

        if not fingerprint:
            # Try reading all TXXX tags
            for key in audio_file.keys():
                if key.startswith("TXXX"):
                    print(f"  Found tag: {key} = {audio_file[key][0]}")

        if not fingerprint:
            print("❌ Fingerprint NOT FOUND in file metadata")

        return {
            "file_exists": True,
            "has_fingerprint": bool(fingerprint),
            "fingerprint": fingerprint
        }

    except Exception as e:
        print(f"ERROR reading file: {e}")
        import traceback
        traceback.print_exc()
        return None


if __name__ == "__main__":
    # Page ID from the production run log
    page_id = "2e7e7361-6c27-81e5-891f-fc0af3aaf971"  # Inciting Ferdinand

    print("=" * 80)
    print("PRODUCTION UPDATE VERIFICATION")
    print("=" * 80)

    notion_result = verify_notion_updates(page_id)

    if notion_result and notion_result.get("file_paths"):
        # Verify first file path
        file_type, file_path = notion_result["file_paths"][0]
        file_result = verify_file_fingerprint(file_path)

        print("\n" + "=" * 80)
        print("VERIFICATION SUMMARY")
        print("=" * 80)
        print(f"Notion Fingerprint: {'✅' if notion_result.get('has_fingerprint') else '❌'}")
        print(f"File Fingerprint: {'✅' if file_result and file_result.get('has_fingerprint') else '❌'}")
        print(f"Eagle ID: {'✅' if notion_result.get('has_eagle_id') else '⚠️'}")
        print(f"File Paths: {len(notion_result.get('file_paths', []))}")
    else:
        print("\n⚠️  Could not verify file updates (no file paths found)")

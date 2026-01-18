#!/usr/bin/env python3
"""Check all properties on a Notion page."""
import sys
import json

try:
    from shared_core.notion.token_manager import get_notion_client
except ImportError:
    print("ERROR: Could not import required modules")
    sys.exit(1)


def check_all_properties(page_id: str) -> None:
    """List all properties on a Notion page."""
    print(f"\n🔍 Checking all properties for page: {page_id}")
    print("=" * 80)

    notion = get_notion_client()
    if not notion:
        print("ERROR: Notion client not available")
        return

    try:
        page = notion.pages.retrieve(page_id=page_id)
        props = page.get("properties", {})

        print(f"\nFound {len(props)} properties:\n")

        for prop_name, prop_data in props.items():
            prop_type = prop_data.get("type", "unknown")
            print(f"{prop_name} ({prop_type}):")

            if prop_type == "title":
                title_array = prop_data.get("title", [])
                if title_array:
                    print(f"  Value: {title_array[0].get('plain_text', '')}")
            elif prop_type == "rich_text":
                rich_text = prop_data.get("rich_text", [])
                if rich_text:
                    print(f"  Value: {rich_text[0].get('plain_text', '')}")
            elif prop_type == "url":
                url = prop_data.get("url")
                print(f"  Value: {url}")
            elif prop_type == "checkbox":
                checkbox = prop_data.get("checkbox", False)
                print(f"  Value: {checkbox}")
            elif prop_type == "number":
                number = prop_data.get("number")
                print(f"  Value: {number}")
            elif prop_type == "date":
                date = prop_data.get("date")
                print(f"  Value: {date}")
            elif prop_type == "multi_select":
                multi_select = prop_data.get("multi_select", [])
                values = [item.get("name") for item in multi_select]
                print(f"  Value: {values}")
            else:
                print(f"  Raw: {json.dumps(prop_data, indent=2)[:200]}...")

            print()

    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    page_id = "2e7e7361-6c27-81e5-891f-fc0af3aaf971"  # Inciting Ferdinand
    check_all_properties(page_id)

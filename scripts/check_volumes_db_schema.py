#!/usr/bin/env python3
"""Check Volumes database schema"""
import os
from notion_client import Client
from dotenv import load_dotenv

load_dotenv()
notion = Client(auth=os.getenv("NOTION_TOKEN") or os.getenv("NOTION_API_KEY"))

VOLUMES_DB_ID = "26ce7361-6c27-8148-8719-fbd26a627d17"

db = notion.databases.retrieve(database_id=VOLUMES_DB_ID)
print("Volumes Database Properties:")
for prop_name, prop_data in db["properties"].items():
    print(f"  {prop_name}: {prop_data['type']}")

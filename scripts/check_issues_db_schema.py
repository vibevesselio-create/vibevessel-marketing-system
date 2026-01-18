#!/usr/bin/env python3
"""Check Issues database schema"""
import os
from notion_client import Client
from dotenv import load_dotenv

load_dotenv()
notion = Client(auth=os.getenv("NOTION_TOKEN") or os.getenv("NOTION_API_KEY"))

ISSUES_DB_ID = "229e73616c27808ebf06c202b10b5166"

db = notion.databases.retrieve(database_id=ISSUES_DB_ID)
print("Properties:")
for prop_name, prop_data in db["properties"].items():
    print(f"  {prop_name}: {prop_data['type']}")

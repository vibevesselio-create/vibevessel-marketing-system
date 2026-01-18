#!/usr/bin/env python3
"""Check Agent-Tasks database schema"""
import os
from notion_client import Client
from dotenv import load_dotenv

load_dotenv()
notion = Client(auth=os.getenv("NOTION_TOKEN") or os.getenv("NOTION_API_KEY"))

AGENT_TASKS_DB_ID = "284e73616c278018872aeb14e82e0392"

db = notion.databases.retrieve(database_id=AGENT_TASKS_DB_ID)
print("Properties:")
for prop_name, prop_data in db["properties"].items():
    print(f"  {prop_name}: {prop_data['type']}")

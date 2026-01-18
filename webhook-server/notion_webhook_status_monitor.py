#!/usr/bin/env python3
"""
Notion Webhook Status Monitor
=============================

Enhanced screenshot service that captures the Notion integration status page,
processes the image with OCR to extract status information, and provides
parsed data for webhook server status updates.

Features:
- Full-page screenshot capture using Playwright
- OCR text extraction using pytesseract
- Status parsing (Active/Inactive)
- Enhanced image processing
- Notion API integration for status updates
"""

import asyncio
import os
import base64
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, Tuple
import json

try:
    from playwright.async_api import async_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False
    print("⚠️ Playwright not available")

try:
    import pytesseract
    from PIL import Image, ImageEnhance, ImageFilter
    OCR_AVAILABLE = True
except ImportError:
    OCR_AVAILABLE = False
    print("⚠️ OCR libraries not available (pytesseract, PIL)")

try:
    from notion_client import Client
    NOTION_AVAILABLE = True
except ImportError:
    NOTION_AVAILABLE = False
    print("⚠️ Notion client not available")


class NotionWebhookStatusMonitor:
    """Monitor and parse Notion webhook integration status"""
    
    def __init__(
        self,
        notion_url: str = "https://www.notion.so/profile/integrations/internal/17d886f6-74c9-48fe-8948-c37564125be1",
        output_dir: str = "/Volumes/SYSTEM_SSD/Dropbox/screenshots",
        notion_token: Optional[str] = None,
        scripts_database_id: Optional[str] = None
    ):
        self.notion_url = notion_url
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Notion API setup
        self.notion_token = notion_token or os.getenv("NOTION_API_TOKEN") or os.getenv("NOTION_TOKEN")
        self.scripts_database_id = scripts_database_id or os.getenv("SCRIPT_DB_ID") or os.getenv("SCRIPTS_DB_ID") or os.getenv("NOTION_SCRIPTS_DATABASE_ID")
        self.notion_client = None
        if NOTION_AVAILABLE and self.notion_token:
            self.notion_client = Client(auth=self.notion_token)
    
    async def capture_screenshot(
        self,
        wait_time: int = 3,
        full_page: bool = True,
        viewport_width: int = 1920,
        viewport_height: int = 1080
    ) -> Tuple[str, bytes]:
        """
        Capture screenshot of Notion integration status page
        
        Returns:
            Tuple of (file_path, image_bytes)
        """
        if not PLAYWRIGHT_AVAILABLE:
            raise RuntimeError("Playwright is not available. Install with: pip install playwright && playwright install")
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"notion_webhook_status_{timestamp}.png"
        file_path = self.output_dir / filename
        
        async with async_playwright() as p:
            # Launch browser in headless mode
            browser = await p.chromium.launch(
                headless=True,
                args=['--no-sandbox', '--disable-setuid-sandbox']
            )
            
            # Create context with viewport
            context = await browser.new_context(
                viewport={'width': viewport_width, 'height': viewport_height},
                user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
            )
            
            page = await context.new_page()
            
            try:
                # Navigate to the page
                await page.goto(self.notion_url, wait_until='networkidle', timeout=30000)
                
                # Wait for page to fully load
                await asyncio.sleep(wait_time)
                
                # Wait for specific elements that indicate the page has loaded
                try:
                    await page.wait_for_selector('text=Event Subscriptions', timeout=10000)
                except:
                    pass  # Continue even if selector not found
                
                # Take full-page screenshot
                screenshot_bytes = await page.screenshot(
                    path=str(file_path),
                    full_page=full_page,
                    type='png'
                )
                
                return str(file_path), screenshot_bytes
                
            finally:
                await browser.close()
    
    def enhance_image(self, image_path: str) -> str:
        """
        Enhance screenshot image for better OCR accuracy
        
        Returns:
            Path to enhanced image
        """
        if not OCR_AVAILABLE:
            return image_path
        
        try:
            # Load image
            img = Image.open(image_path)
            
            # Convert to RGB if necessary
            if img.mode != 'RGB':
                img = img.convert('RGB')
            
            # Enhance contrast
            enhancer = ImageEnhance.Contrast(img)
            img = enhancer.enhance(1.5)
            
            # Enhance sharpness
            enhancer = ImageEnhance.Sharpness(img)
            img = enhancer.enhance(2.0)
            
            # Apply slight denoising
            img = img.filter(ImageFilter.MedianFilter(size=3))
            
            # Save enhanced image
            enhanced_path = str(Path(image_path).with_suffix('.enhanced.png'))
            img.save(enhanced_path, 'PNG', quality=95)
            
            return enhanced_path
        except Exception as e:
            print(f"⚠️ Image enhancement failed: {e}")
            return image_path
    
    def extract_text_with_ocr(self, image_path: str) -> str:
        """
        Extract text from screenshot using OCR
        
        Returns:
            Extracted text string
        """
        if not OCR_AVAILABLE:
            return ""
        
        try:
            # Use enhanced image if available
            enhanced_path = str(Path(image_path).with_suffix('.enhanced.png'))
            ocr_image_path = enhanced_path if os.path.exists(enhanced_path) else image_path
            
            # Extract text with OCR
            text = pytesseract.image_to_string(
                Image.open(ocr_image_path),
                config='--psm 6 -c tessedit_char_whitelist=0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz:/-_.,()[]{} '
            )
            
            return text
        except Exception as e:
            print(f"⚠️ OCR extraction failed: {e}")
            return ""
    
    def parse_status(self, ocr_text: str, screenshot_path: str) -> Dict[str, Any]:
        """
        Parse status information from OCR text and screenshot
        
        Returns:
            Dictionary with parsed status information
        """
        status_info = {
            'status': 'Unknown',
            'is_active': False,
            'subscription_status': None,
            'last_event': None,

            'webhook_url': None,
            'confidence': 'low',
            'raw_text': ocr_text[:500],  # First 500 chars for debugging
            'timestamp': datetime.now().isoformat(),
            'screenshot_path': screenshot_path
        }
        
        # Normalize text for parsing
        text_lower = ocr_text.lower()
        
        # Look for active/inactive indicators
        active_indicators = [
            'active', 'enabled', 'running', 'connected', 'online',
            'subscription active', 'webhook active'
        ]
        inactive_indicators = [
            'inactive', 'disabled', 'stopped', 'disconnected', 'offline',
            'subscription inactive', 'webhook inactive', 'error', 'failed'
        ]
        
        # Check for active status
        active_count = sum(1 for indicator in active_indicators if indicator in text_lower)
        inactive_count = sum(1 for indicator in inactive_indicators if indicator in text_lower)
        
        if active_count > inactive_count:
            status_info['status'] = 'Active'
            status_info['is_active'] = True
            status_info['confidence'] = 'high' if active_count >= 2 else 'medium'
        elif inactive_count > active_count:
            status_info['status'] = 'Inactive'
            status_info['is_active'] = False
            status_info['confidence'] = 'high' if inactive_count >= 2 else 'medium'
        else:
            # Try to find specific status text
            if 'subscription' in text_lower:
                if 'active' in text_lower:
                    status_info['status'] = 'Active'
                    status_info['is_active'] = True
                elif 'inactive' in text_lower:
                    status_info['status'] = 'Inactive'
                    status_info['is_active'] = False
        
        # Extract webhook URL if present
        import re
        url_pattern = r'https?://[^\s]+'
        urls = re.findall(url_pattern, ocr_text)
        if urls:
            status_info['webhook_url'] = urls[0]
        
        # Extract subscription status
        if 'subscription' in text_lower:
            if 'active' in text_lower:
                status_info['subscription_status'] = 'active'
            elif 'inactive' in text_lower or 'paused' in text_lower:
                status_info['subscription_status'] = 'inactive'
        
        return status_info
    
    async def monitor_and_parse(self) -> Dict[str, Any]:
        """
        Complete monitoring workflow: capture, enhance, OCR, parse
        
        Returns:
            Dictionary with complete status information
        """
        result = {
            'success': False,
            'screenshot_path': None,
            'enhanced_path': None,
            'status_info': None,
            'error': None,
            'timestamp': datetime.now().isoformat()
        }
        
        try:
            # Step 1: Capture screenshot
            print("📸 Capturing screenshot...")
            screenshot_path, screenshot_bytes = await self.capture_screenshot()
            result['screenshot_path'] = screenshot_path
            print(f"✅ Screenshot saved: {screenshot_path}")
            
            # Step 2: Enhance image
            if OCR_AVAILABLE:
                print("🎨 Enhancing image for OCR...")
                enhanced_path = self.enhance_image(screenshot_path)
                result['enhanced_path'] = enhanced_path
                print(f"✅ Enhanced image saved: {enhanced_path}")
            
            # Step 3: Extract text with OCR
            if OCR_AVAILABLE:
                print("🔍 Extracting text with OCR...")
                ocr_text = self.extract_text_with_ocr(screenshot_path)
                print(f"✅ Extracted {len(ocr_text)} characters")
            else:
                ocr_text = ""
            
            # Step 4: Parse status
            print("📊 Parsing status information...")
            status_info = self.parse_status(ocr_text, screenshot_path)
            result['status_info'] = status_info
            print(f"✅ Status parsed: {status_info['status']} (confidence: {status_info['confidence']})")
            
            result['success'] = True
            
        except Exception as e:
            result['error'] = str(e)
            print(f"❌ Error in monitoring workflow: {e}")
            import traceback
            traceback.print_exc()
        
        return result
    
    async def update_notion_status(
        self,
        status_info: Dict[str, Any],
        script_name: str = "Notion Webhook Status Monitor"
    ) -> bool:
        """
        Update Notion scripts database with current status
        
        Args:
            status_info: Parsed status information
            script_name: Name of the script in the database
            
        Returns:
            True if update successful, False otherwise
        """
        if not self.notion_client or not self.scripts_database_id:
            print("⚠️ Notion client or database ID not configured")
            return False
        
        try:
            # Query database for the script
            response = self.notion_client.databases.query(
                database_id=self.scripts_database_id,
                filter={
                    "property": "Name",
                    "title": {
                        "equals": script_name
                    }
                }
            )
            
            if not response.get('results'):
                print(f"⚠️ Script '{script_name}' not found in database")
                return False
            
            page_id = response['results'][0]['id']
            
            # Determine status value
            status_value = "Active" if status_info.get('is_active', False) else "Inactive"
            
            # Update the page
            self.notion_client.pages.update(
                page_id=page_id,
                properties={
                    "Status": {
                        "select": {
                            "name": status_value
                        }
                    }
                }
            )
            
            print(f"✅ Updated Notion database: Status = {status_value}")
            return True
            
        except Exception as e:
            print(f"❌ Error updating Notion database: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def get_screenshot_base64(self, image_path: str) -> str:
        """Convert screenshot to base64 for API transmission"""
        try:
            with open(image_path, 'rb') as f:
                image_bytes = f.read()
                return base64.b64encode(image_bytes).decode('utf-8')
        except Exception as e:
            print(f"⚠️ Error encoding image: {e}")
            return ""


async def main():
    """Main function for standalone execution"""
    monitor = NotionWebhookStatusMonitor()
    
    # Run monitoring workflow
    result = await monitor.monitor_and_parse()
    
    # Print results
    print("\n" + "="*60)
    print("MONITORING RESULTS")
    print("="*60)
    print(json.dumps(result, indent=2, default=str))
    
    # Update Notion if status was parsed
    if result['success'] and result['status_info']:
        await monitor.update_notion_status(result['status_info'])


if __name__ == "__main__":
    asyncio.run(main())


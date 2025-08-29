import requests
from bs4 import BeautifulSoup
import csv
import json
import time
import re
import os
from urllib.parse import urljoin
from datetime import datetime
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class AlphaCardScraper:
    def __init__(self):
        self.base_url = "https://www.alphacard.com"
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Connection': 'keep-alive'
        })
        self.printers_data = []
        
    def get_page(self, url, retries=3):
        """Fetch page with error handling"""
        for attempt in range(retries):
            try:
                time.sleep(2)  # Be respectful
                logger.info(f"Fetching: {url}")
                response = self.session.get(url, timeout=30)
                response.raise_for_status()
                return BeautifulSoup(response.content, 'html.parser')
            except Exception as e:
                logger.warning(f"Attempt {attempt + 1} failed: {e}")
                if attempt == retries - 1:
                    logger.error(f"All attempts failed for {url}")
                    return None
                time.sleep(5 * (attempt + 1))
        return None

    def find_printer_urls(self):
        """Find all printer product URLs"""
        printer_urls = set()
        
        # Category pages to scan
        categories = [
            "/id-card-printers/view-all-id-printers",
            "/id-card-printers",
            "/id-card-printers/id-card-printers-by-manufacturer/alphacard-printers",
            "/id-card-printers/id-card-printers-by-manufacturer/magicard-printers", 
            "/id-card-printers/id-card-printers-by-manufacturer/fargo-printers",
            "/id-card-printers/id-card-printers-by-manufacturer/zebra-printers",
            "/id-card-printers/id-card-printers-by-manufacturer/evolis-printers"
        ]
        
        for category in categories:
            soup = self.get_page(self.base_url + category)
            if not soup:
                continue
                
            # Find product links
            links = soup.find_all('a', href=True)
            for link in links:
                href = link.get('href', '')
                if self.is_printer_url(href):
                    full_url = urljoin(self.base_url, href)
                    printer_urls.add(full_url)
        
        logger.info(f"Found {len(printer_urls)} printer URLs")
        return list(printer_urls)
    
    def is_printer_url(self, url):
        """Check if URL is a printer product page"""
        if not url:
            return False
            
        url_lower = url.lower()
        
        # Exclude non-product URLs
        excludes = ['/blog/', '/support/', '/software/', '/supplies/', '/ribbons/', 
                   '.pdf', '.jpg', '/compare/', '/category/', '/view-all', '/manufacturer']
        if any(ex in url_lower for ex in excludes):
            return False
        
        # Include printer URLs - must contain printer path AND not be a category page
        includes = ['/id-card-printers/', '/printer/', 'card-printer']
        has_printer_path = any(inc in url_lower for inc in includes)
        
        # Additional check: URL should have a specific product (not just category)
        url_parts = url.strip('/').split('/')
        is_specific_product = len(url_parts) >= 3 and not url_lower.endswith('printers')
        
        return has_printer_path and is_specific_product

    def extract_product_description(self, soup):
        """Extract the detailed product description HTML without wrapper divs"""
        description_html = ""
        
        # Look for the specific product description div
        desc_div = soup.find('div', class_='product attribute description')
        if desc_div:
            value_div = desc_div.find('div', class_='value')
            if value_div:
                # Look for the inner content div with data attributes
                inner_div = value_div.find('div', attrs={'data-content-type': 'html'})
                if inner_div:
                    # Extract just the inner HTML content, not the div wrapper
                    description_html = inner_div.decode_contents()
                    logger.info("✅ Found detailed product description (clean)")
                else:
                    # Fallback: get all content inside value div but skip wrapper divs
                    description_html = value_div.decode_contents()
                    logger.info("✅ Found description content (fallback)")
            else:
                # Fallback to the outer div content
                description_html = desc_div.decode_contents()
                logger.info("✅ Found description (outer fallback)")
        else:
            # Additional fallback selectors
            fallback_selectors = [
                '.product-description',
                '.description',
                '[data-content-type="html"]',
                '.product-info-main .description',
                '.product-attribute-description'
            ]
            
            for selector in fallback_selectors:
                element = soup.select_one(selector)
                if element:
                    description_html = element.decode_contents()
                    logger.info(f"✅ Found description using fallback: {selector}")
                    break
            
            if not description_html:
                logger.warning("⚠️ No detailed product description found")
        
        # Clean up the HTML and remove wrapper div artifacts
        if description_html:
            # Remove any remaining wrapper div tags that might have been included
            description_html = re.sub(r'<div[^>]*data-content-type="html"[^>]*>', '', description_html)
            description_html = re.sub(r'<div[^>]*data-appearance="default"[^>]*>', '', description_html)
            description_html = re.sub(r'<div[^>]*data-element="main"[^>]*>', '', description_html)
            description_html = re.sub(r'<div[^>]*data-decoded="true"[^>]*>', '', description_html)
            description_html = re.sub(r'<div[^>]*class="value"[^>]*>', '', description_html)
            
            # Remove closing </div> tags that are now orphaned (be careful not to remove content divs)
            # Count opening and closing div tags to balance them
            open_divs = len(re.findall(r'<div[^>]*>', description_html))
            close_divs = len(re.findall(r'</div>', description_html))
            
            # Remove excess closing divs from the end
            excess_closes = close_divs - open_divs
            if excess_closes > 0:
                # Remove the last N closing div tags
                for _ in range(excess_closes):
                    description_html = re.sub(r'</div>(?!.*</div>)', '', description_html, count=1)
            
            # Clean up whitespace
            description_html = re.sub(r'\s+', ' ', description_html)
            description_html = description_html.strip()
        
        return description_html

    def extract_printer_data(self, url):
        """Extract printer specifications including detailed description"""
        soup = self.get_page(url)
        if not soup:
            return None
            
        data = {
            'url': url,
            'scraped_date': datetime.now().isoformat(),
            'brand': '',
            'model': '',
            'full_name': '',
            'description': '',  # NEW: HTML description field
            'print_speed_color': '',
            'print_speed_mono': '', 
            'print_resolution': '',
            'card_capacity': '',
            'connectivity': '',
            'dimensions': '',
            'weight': '',
            'warranty': '',
            'price': '',
            'features': '',
            'printing_method': '',
            'card_sizes': '',
            'encoding_options': ''
        }
        
        try:
            # Extract title and model
            title = soup.find('title')
            if title:
                data['full_name'] = title.text.strip()
                
            h1 = soup.find('h1')
            if h1:
                data['model'] = h1.text.strip()
            elif title:
                data['model'] = title.text.split('|')[0].strip()
            
            # Detect brand
            model_lower = data['model'].lower()
            brands = {
                'alphacard': 'AlphaCard', 'magicard': 'Magicard', 'fargo': 'Fargo',
                'zebra': 'Zebra', 'evolis': 'Evolis', 'datacard': 'Entrust Datacard',
                'entrust': 'Entrust Datacard', 'idp': 'IDP', 'swiftcolor': 'SwiftColor',
                'matica': 'Matica'
            }
            for key, brand in brands.items():
                if key in model_lower:
                    data['brand'] = brand
                    break
            
            # Extract detailed product description (NEW)
            data['description'] = self.extract_product_description(soup)
            
            # Extract specifications from tables
            tables = soup.find_all('table')
            for table in tables:
                rows = table.find_all('tr')
                for row in rows:
                    cells = row.find_all(['td', 'th'])
                    if len(cells) >= 2:
                        key = cells[0].get_text(strip=True).lower()
                        value = cells[1].get_text(strip=True)
                        self.map_specification(key, value, data)
            
            # Extract features from lists (but avoid duplicating description content)
            features = []
            for ul in soup.find_all(['ul', 'ol']):
                # Skip lists that are inside the product description to avoid duplication
                if not ul.find_parent('div', class_='product attribute description'):
                    for li in ul.find_all('li'):
                        text = li.get_text(strip=True)
                        if 10 < len(text) < 200:
                            features.append(text)
            data['features'] = '; '.join(features[:10])
            
            # Extract price and speed from text
            page_text = soup.get_text()
            
            # Price patterns
            price_match = re.search(r'\$[\d,]+\.?\d*', page_text)
            if price_match:
                data['price'] = price_match.group()
            
            # Speed patterns (enhanced to catch more variations)
            speed_patterns = [
                r'(\d+)\s*cards?\s*per\s*hour',
                r'(\d+)\s*cph',
                r'full\s*color.*?(\d+)\s*seconds?',
                r'print.*?(\d+)\s*seconds?',
                r'speed[:\s]*(\d+)'
            ]
            
            for pattern in speed_patterns:
                match = re.search(pattern, page_text, re.I)
                if match:
                    if 'seconds' in pattern:
                        # Convert seconds to cards/hour estimate
                        seconds = int(match.group(1))
                        cards_per_hour = int(3600 / seconds) if seconds > 0 else 0
                        data['print_speed_color'] = f"{cards_per_hour} cards/hour (estimated from {seconds}s per card)"
                    else:
                        data['print_speed_color'] = f"{match.group(1)} cards/hour"
                    break
            
            # Resolution patterns  
            res_match = re.search(r'(\d+\s*x\s*\d+|\d+)\s*dpi', page_text, re.I)
            if res_match:
                data['print_resolution'] = res_match.group()
            
            # Enhanced warranty detection
            warranty_patterns = [
                r'(\d+)\s*year\s*warranty',
                r'warranty[:\s]*(\d+)\s*years?',
                r'(\d+)-year\s*warranty'
            ]
            
            for pattern in warranty_patterns:
                match = re.search(pattern, page_text, re.I)
                if match:
                    data['warranty'] = f"{match.group(1)} years"
                    break
                
        except Exception as e:
            logger.error(f"Error extracting from {url}: {e}")
            
        return data if data['model'] else None
    
    def map_specification(self, key, value, data):
        """Map specification keys to data fields"""
        if not value or len(value) > 300:
            return
            
        key_lower = key.lower()
        
        if 'speed' in key_lower and not data['print_speed_color']:
            data['print_speed_color'] = value
        elif 'resolution' in key_lower and not data['print_resolution']:
            data['print_resolution'] = value
        elif ('capacity' in key_lower or 'hopper' in key_lower) and not data['card_capacity']:
            data['card_capacity'] = value
        elif 'connectivity' in key_lower and not data['connectivity']:
            data['connectivity'] = value
        elif 'dimension' in key_lower and not data['dimensions']:
            data['dimensions'] = value
        elif 'weight' in key_lower and not data['weight']:
            data['weight'] = value
        elif 'warranty' in key_lower and not data['warranty']:
            data['warranty'] = value
        elif ('encoding' in key_lower or 'magnetic' in key_lower) and not data['encoding_options']:
            data['encoding_options'] = value
        elif 'card' in key_lower and 'size' in key_lower and not data['card_sizes']:
            data['card_sizes'] = value

    def scrape_all_printers(self):
        """Main scraping method"""
        logger.info("🕷️ Starting AlphaCard scraper...")
        
        printer_urls = self.find_printer_urls()
        if not printer_urls:
            logger.error("❌ No printer URLs found!")
            return []
            
        logger.info(f"📋 Found {len(printer_urls)} printers to scrape")
        
        for i, url in enumerate(printer_urls, 1):
            logger.info(f"Processing {i}/{len(printer_urls)}")
            data = self.extract_printer_data(url)
            
            if data:
                self.printers_data.append(data)
                desc_preview = data['description'][:100] + "..." if data['description'] else "No description"
                logger.info(f"✅ {data['brand']} {data['model']} | Desc: {desc_preview}")
            else:
                logger.warning(f"❌ Failed to extract data from {url}")
                
        logger.info(f"🎉 Completed! Scraped {len(self.printers_data)} printers")
        return self.printers_data

    def save_results(self):
        """Save results in multiple formats"""
        if not self.printers_data:
            logger.warning("No data to save!")
            return
            
        # Save CSV
        with open('alphacard_printers.csv', 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=self.printers_data[0].keys())
            writer.writeheader()
            writer.writerows(self.printers_data)
        logger.info(f"💾 Saved CSV: {len(self.printers_data)} printers")
        
        # Save JSON
        with open('alphacard_printers.json', 'w', encoding='utf-8') as f:
            json.dump(self.printers_data, f, indent=2, ensure_ascii=False)
        logger.info("💾 Saved JSON")
        
        # Generate enhanced summary
        summary = {
            'total_printers': len(self.printers_data),
            'scraped_at': datetime.now().isoformat(),
            'brands': {},
            'with_prices': sum(1 for p in self.printers_data if p['price']),
            'with_speeds': sum(1 for p in self.printers_data if p['print_speed_color']),
            'with_descriptions': sum(1 for p in self.printers_data if p['description']),
            'avg_description_length': 0
        }
        
        # Calculate average description length
        desc_lengths = [len(p['description']) for p in self.printers_data if p['description']]
        if desc_lengths:
            summary['avg_description_length'] = int(sum(desc_lengths) / len(desc_lengths))
        
        for printer in self.printers_data:
            brand = printer['brand'] or 'Unknown'
            summary['brands'][brand] = summary['brands'].get(brand, 0) + 1
            
        with open('scrape_summary.json', 'w') as f:
            json.dump(summary, f, indent=2)
            
        logger.info("📊 Summary:")
        logger.info(f"  Total: {summary['total_printers']} printers")
        logger.info(f"  With prices: {summary['with_prices']}")
        logger.info(f"  With speeds: {summary['with_speeds']}")
        logger.info(f"  With descriptions: {summary['with_descriptions']}")
        logger.info(f"  Avg description length: {summary['avg_description_length']} chars")
        for brand, count in summary['brands'].items():
            logger.info(f"  {brand}: {count}")

def main():
    scraper = AlphaCardScraper()
    
    try:
        printers = scraper.scrape_all_printers()
        
        if printers:
            scraper.save_results()
            logger.info("🎯 Scraping completed successfully!")
            
            # Show sample of description data
            for i, printer in enumerate(printers[:3]):
                if printer['description']:
                    desc_preview = printer['description'][:200] + "..." if len(printer['description']) > 200 else printer['description']
                    logger.info(f"📄 Sample description {i+1}: {desc_preview}")
        else:
            logger.error("💥 No printers scraped!")
            exit(1)
            
    except Exception as e:
        logger.error(f"💥 Scraping failed: {e}")
        exit(1)

if __name__ == "__main__":
    main()

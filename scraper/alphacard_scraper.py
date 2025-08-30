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

class WooCommerceAlphaCardScraper:
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
        self.all_spec_columns = set()
        
    def get_page(self, url, retries=3):
        """Fetch page with error handling"""
        for attempt in range(retries):
            try:
                time.sleep(2)
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
        excludes = ['/blog/', '/support/', '/software/', '/supplies/', '/ribbons/', 
                   '.pdf', '.jpg', '/compare/', '/category/', '/view-all', '/manufacturer']
        if any(ex in url_lower for ex in excludes):
            return False
        
        includes = ['/id-card-printers/', '/printer/', 'card-printer']
        has_printer_path = any(inc in url_lower for inc in includes)
        url_parts = url.strip('/').split('/')
        is_specific_product = len(url_parts) >= 3 and not url_lower.endswith('printers')
        
        return has_printer_path and is_specific_product

    def extract_product_images(self, soup):
        """Extract product images for WooCommerce gallery"""
        images = []
        
        image_selectors = [
            '.product-image img',
            '.product-media img',
            '.gallery-image img',
            '.fotorama img',
            '.product-image-main img',
            'img[data-zoom-image]'
        ]
        
        for selector in image_selectors:
            imgs = soup.select(selector)
            for img in imgs:
                src = img.get('src') or img.get('data-src') or img.get('data-zoom-image')
                if src and 'placeholder' not in src and 'loading' not in src:
                    if src.startswith('/'):
                        src = self.base_url + src
                    if src not in images and src.startswith('http'):
                        images.append(src)
        
        logger.info(f"✅ Found {len(images)} product images")
        return images

    def extract_product_categories(self, soup):
        """Extract product categories/breadcrumbs for WooCommerce categorization"""
        categories = []
        
        breadcrumb_selectors = [
            '.breadcrumbs a',
            '.breadcrumb a', 
            '.nav-breadcrumb a',
            '.page-title-wrapper .breadcrumbs a'
        ]
        
        for selector in breadcrumb_selectors:
            links = soup.select(selector)
            for link in links:
                category_text = link.get_text(strip=True)
                if category_text and category_text.lower() not in ['home', 'shop', 'products']:
                    categories.append(category_text)
        
        return categories

    def extract_product_tags(self, soup, data):
        """Generate relevant tags for WooCommerce based on features and specs"""
        tags = []
        
        if data.get('brand'):
            tags.append(data['brand'])
        
        text_content = (data.get('highlights', '') + ' ' + data.get('description', '')).lower()
        
        tag_keywords = {
            'dual-sided': ['dual-sided', 'dual sided', 'duplex'],
            'single-sided': ['single-sided', 'single sided', 'simplex'],
            'wifi': ['wifi', 'wi-fi', 'wireless'],
            'ethernet': ['ethernet', 'network', 'lan'],
            'usb': ['usb'],
            'magnetic-stripe': ['magnetic stripe', 'mag stripe', 'magstripe'],
            'smart-card': ['smart card', 'smartcard', 'chip'],
            'rfid': ['rfid', 'proximity'],
            'contactless': ['contactless'],
            'high-volume': ['high volume', 'enterprise', 'large batch'],
            'compact': ['compact', 'small', 'desktop'],
            'laminating': ['laminating', 'lamination'],
            'retransfer': ['retransfer', 're-transfer', 'reverse transfer'],
            'dye-sublimation': ['dye sublimation', 'dye-sublimation']
        }
        
        for tag, keywords in tag_keywords.items():
            if any(keyword in text_content for keyword in keywords):
                tags.append(tag)
        
        return tags

    def extract_seo_data(self, soup):
        """Extract SEO-relevant data for WooCommerce"""
        seo_data = {}
        
        meta_desc = soup.find('meta', attrs={'name': 'description'})
        if meta_desc:
            seo_data['meta_description'] = meta_desc.get('content', '')
        
        meta_keywords = soup.find('meta', attrs={'name': 'keywords'})
        if meta_keywords:
            seo_data['meta_keywords'] = meta_keywords.get('content', '')
        
        schema_scripts = soup.find_all('script', type='application/ld+json')
        schema_data = []
        for script in schema_scripts:
            try:
                schema_json = json.loads(script.string)
                schema_data.append(schema_json)
            except:
                pass
        seo_data['schema_data'] = json.dumps(schema_data) if schema_data else ''
        
        return seo_data

    def extract_stock_availability(self, soup):
        """Extract stock status for WooCommerce inventory"""
        stock_info = {
            'stock_status': 'instock',
            'stock_quantity': '',
            'backorders': 'no'
        }
        
        stock_selectors = [
            '.stock',
            '.availability', 
            '.inventory',
            '.product-stock',
            '[class*="stock"]'
        ]
        
        for selector in stock_selectors:
            elements = soup.select(selector)
            for element in elements:
                text = element.get_text().lower()
                if 'out of stock' in text or 'unavailable' in text:
                    stock_info['stock_status'] = 'outofstock'
                elif 'in stock' in text:
                    stock_info['stock_status'] = 'instock'
                elif 'backorder' in text or 'special order' in text:
                    stock_info['backorders'] = 'yes'
                
                qty_match = re.search(r'(\d+)\s*(?:in stock|available)', text)
                if qty_match:
                    stock_info['stock_quantity'] = qty_match.group(1)
        
        return stock_info

    def extract_related_products(self, soup):
        """Extract related/cross-sell products"""
        related_products = []
        
        related_selectors = [
            '.related-products a',
            '.cross-sell a',
            '.upsell a',
            '.recommended-products a',
            '[class*="related"] a[href*="id-card-printers"]'
        ]
        
        for selector in related_selectors:
            links = soup.select(selector)
            for link in links:
                href = link.get('href')
                title = link.get('title') or link.get_text(strip=True)
                if href and self.is_printer_url(href):
                    related_products.append({
                        'url': urljoin(self.base_url, href),
                        'title': title
                    })
        
        return related_products[:10]

    def convert_measurements(self, text):
        """Convert measurements to metric units (mm for dimensions, kg for weight)"""
        if not text:
            return text
        
        converted_text = text
        
        # Convert inches to mm (1 inch = 25.4 mm)
        inch_patterns = [
            r'(\d+\.?\d*)\s*(?:inches?|in|")',
            r'(\d+\.?\d*)\s*(?:inch|inches)'
        ]
        
        for pattern in inch_patterns:
            matches = re.finditer(pattern, converted_text, re.IGNORECASE)
            for match in matches:
                inches = float(match.group(1))
                mm = round(inches * 25.4, 1)
                # Replace the match with mm equivalent
                old_text = match.group(0)
                new_text = f"{mm}mm"
                converted_text = converted_text.replace(old_text, new_text, 1)
        
        # Convert feet to mm (1 foot = 304.8 mm)
        foot_patterns = [
            r'(\d+\.?\d*)\s*(?:feet|foot|ft|\')',
        ]
        
        for pattern in foot_patterns:
            matches = re.finditer(pattern, converted_text, re.IGNORECASE)
            for match in matches:
                feet = float(match.group(1))
                mm = round(feet * 304.8, 1)
                old_text = match.group(0)
                new_text = f"{mm}mm"
                converted_text = converted_text.replace(old_text, new_text, 1)
        
        # Convert pounds to kg (1 lb = 0.453592 kg)
        weight_patterns = [
            r'(\d+\.?\d*)\s*(?:lbs?|pounds?|pound)',
        ]
        
        for pattern in weight_patterns:
            matches = re.finditer(pattern, converted_text, re.IGNORECASE)
            for match in matches:
                pounds = float(match.group(1))
                kg = round(pounds * 0.453592, 2)
                old_text = match.group(0)
                new_text = f"{kg}kg"
                converted_text = converted_text.replace(old_text, new_text, 1)
        
        return converted_text

    def parse_dimensions(self, dimensions_text):
        """Parse dimensions and convert to mm, return individual measurements"""
        if not dimensions_text:
            return {'length': '', 'width': '', 'height': '', 'weight': ''}
        
        result = {'length': '', 'width': '', 'height': '', 'weight': ''}
        
        # First convert all measurements to metric
        converted_text = self.convert_measurements(dimensions_text)
        
        # Parse dimensions like "457.2mm x 304.8mm x 101.6mm" or "18" x 12" x 4""
        # Try multiple dimension patterns
        dimension_patterns = [
            # Already converted to mm
            r'(\d+\.?\d*)\s*mm.*?x.*?(\d+\.?\d*)\s*mm.*?x.*?(\d+\.?\d*)\s*mm',
            # Original inches that we'll convert
            r'(\d+\.?\d*)\s*(?:inches?|in|").*?x.*?(\d+\.?\d*)\s*(?:inches?|in|").*?x.*?(\d+\.?\d*)\s*(?:inches?|in|")',
            # Mixed units
            r'(\d+\.?\d*)\s*(?:mm|inches?|in|").*?x.*?(\d+\.?\d*)\s*(?:mm|inches?|in|").*?x.*?(\d+\.?\d*)\s*(?:mm|inches?|in|")',
        ]
        
        for pattern in dimension_patterns:
            match = re.search(pattern, dimensions_text, re.IGNORECASE)
            if match:
                # Convert to mm if needed
                dim1 = float(match.group(1))
                dim2 = float(match.group(2)) 
                dim3 = float(match.group(3))
                
                # Check if original was in inches and convert
                if '"' in match.group(0) or 'inch' in match.group(0).lower():
                    dim1 = round(dim1 * 25.4, 1)
                    dim2 = round(dim2 * 25.4, 1)
                    dim3 = round(dim3 * 25.4, 1)
                
                result['length'] = str(dim1)
                result['width'] = str(dim2)
                result['height'] = str(dim3)
                break
        
        # Parse weight separately
        weight_patterns = [
            r'(\d+\.?\d*)\s*kg',
            r'(\d+\.?\d*)\s*(?:lbs?|pounds?)',
        ]
        
        for pattern in weight_patterns:
            match = re.search(pattern, converted_text, re.IGNORECASE)
            if match:
                weight = float(match.group(1))
                # Convert lbs to kg if needed
                if 'lb' in match.group(0).lower() or 'pound' in match.group(0).lower():
                    weight = round(weight * 0.453592, 2)
                result['weight'] = str(weight)
                break
        
        return result

    def convert_usd_to_aud(self, usd_price, conversion_rate=0.62):
        """Convert USD price to AUD using specified conversion rate"""
        if not usd_price:
            return ''
        
        try:
            # Clean the price string and convert to float
            clean_price = str(usd_price).replace('
        """Extract price from the specific price container"""
        price = ''
        
        # Look for the specific price container pattern
        price_selectors = [
            # Primary selector for the specific container
            'span[id*="product-price"] span.price',
            'span[data-price-amount] span.price',
            '.price-wrapper span.price',
            
            # Fallback selectors
            '.price-box .price',
            '.regular-price .price',
            '.special-price .price',
            '.price',
            '[class*="price"] [class*="price"]'
        ]
        
        for selector in price_selectors:
            price_element = soup.select_one(selector)
            if price_element:
                price_text = price_element.get_text(strip=True)
                # Extract numerical price
                price_match = re.search(r'\$?([\d,]+\.?\d*)', price_text)
                if price_match:
                    price = price_match.group(1).replace(',', '')
                    logger.info(f"✅ Found price: ${price} using selector: {selector}")
                    break
        
        # Also check for data-price-amount attribute
        if not price:
            price_container = soup.select_one('[data-price-amount]')
            if price_container:
                price_amount = price_container.get('data-price-amount')
                if price_amount:
                    try:
                        price = str(float(price_amount))
                        logger.info(f"✅ Found price from data attribute: ${price}")
                    except ValueError:
                        pass
        
        if not price:
            logger.warning("⚠️ No price found in containers")
        
        return price

    def extract_sale_price(self, soup):
        """Extract sale/special price if available"""
        sale_price = ''
        
        # Look for sale price indicators
        sale_selectors = [
            '.special-price .price',
            '.sale-price .price',
            '.discount-price .price',
            '.old-price + .price',  # Price after old price
            '[class*="sale"] .price',
            '[class*="special"] .price'
        ]
        
        for selector in sale_selectors:
            sale_element = soup.select_one(selector)
            if sale_element:
                sale_text = sale_element.get_text(strip=True)
                price_match = re.search(r'\$?([\d,]+\.?\d*)', sale_text)
                if price_match:
                    sale_price = price_match.group(1).replace(',', '')
                    logger.info(f"✅ Found sale price: ${sale_price}")
                    break
        
        return sale_price

    def extract_price_from_container(self, soup):

    def generate_product_slug(self, model, brand):
        """Generate WooCommerce-friendly URL slug"""
        slug_text = f"{brand} {model}".lower()
        slug = re.sub(r'[^\w\s-]', '', slug_text)
        slug = re.sub(r'[-\s]+', '-', slug)
        slug = slug.strip('-')
        return slug

    def extract_product_description(self, soup):
        """Extract the detailed product description HTML without wrapper divs"""
        description_html = ""
        
        desc_div = soup.find('div', class_='product attribute description')
        if desc_div:
            value_div = desc_div.find('div', class_='value')
            if value_div:
                inner_div = value_div.find('div', attrs={'data-content-type': 'html'})
                if inner_div:
                    description_html = inner_div.decode_contents()
                    logger.info("✅ Found detailed product description (clean)")
                else:
                    description_html = value_div.decode_contents()
                    logger.info("✅ Found description content (fallback)")
            else:
                description_html = desc_div.decode_contents()
                logger.info("✅ Found description (outer fallback)")
        
        if description_html:
            description_html = re.sub(r'<div[^>]*data-content-type="html"[^>]*>', '', description_html)
            description_html = re.sub(r'<div[^>]*data-appearance="default"[^>]*>', '', description_html)
            description_html = re.sub(r'<div[^>]*data-element="main"[^>]*>', '', description_html)
            description_html = re.sub(r'<div[^>]*data-decoded="true"[^>]*>', '', description_html)
            description_html = re.sub(r'<div[^>]*class="value"[^>]*>', '', description_html)
            
            open_divs = len(re.findall(r'<div[^>]*>', description_html))
            close_divs = len(re.findall(r'</div>', description_html))
            excess_closes = close_divs - open_divs
            if excess_closes > 0:
                for _ in range(excess_closes):
                    description_html = re.sub(r'</div>(?!.*</div>)', '', description_html, count=1)
            
            description_html = re.sub(r'\s+', ' ', description_html).strip()
        
        return description_html

    def extract_product_highlights(self, soup):
        """Extract product highlights as clean HTML"""
        highlights_html = ""
        
        highlights_div = soup.find('div', class_='product attribute highlights')
        if highlights_div:
            value_div = highlights_div.find('div', class_='value')
            if value_div:
                highlights_html = value_div.decode_contents()
                logger.info("✅ Found product highlights")
        
        if highlights_html:
            highlights_html = re.sub(r'<div[^>]*class="value"[^>]*>', '', highlights_html)
            highlights_html = re.sub(r'\s+', ' ', highlights_html).strip()
        
        return highlights_html

    def extract_specifications_table(self, soup):
        """Extract specifications from the table"""
        specs = {}
        
        spec_table = soup.find('table', {'id': 'product-attribute-specs-table'})
        if not spec_table:
            spec_table = soup.find('table', class_='additional-attributes')
            if not spec_table:
                spec_table = soup.find('table', class_='data table')
        
        if spec_table:
            rows = spec_table.find_all('tr')
            logger.info(f"✅ Found specifications table with {len(rows)} rows")
            
            for row in rows:
                header = row.find('th', class_='col label')
                data = row.find('td', class_='col data')
                
                if header and data:
                    key = header.get_text(strip=True)
                    value = data.get_text(strip=True)
                    
                    clean_key = self.clean_column_name(key)
                    if clean_key and value:
                        # Apply unit conversion to specification values
                        converted_value = self.convert_measurements(value)
                        specs[clean_key] = converted_value
                        self.all_spec_columns.add(clean_key)
        
        return specs

    def clean_column_name(self, name):
        """Clean column names to be CSV-friendly"""
        if not name:
            return None
            
        clean = re.sub(r'[^\w\s]', '', name.lower())
        clean = re.sub(r'\s+', '_', clean.strip())
        clean = clean.replace('_options', '').replace('_capability', '').replace('_accepted', '')
        
        replacements = {
            'weight_dimensions': 'dimensions_weight',
            'os_compatibility': 'operating_systems', 
            'card_sizes_accepted': 'card_sizes',
            'card_thickness_accepted': 'card_thickness',
            'printer_color_capability': 'color_capability',
            'print_resolution_dpi': 'print_resolution',
            'printing_speeds_seccard': 'print_speed_seconds',
            'printing_capability': 'print_sides',
            'input_hopper_capacity': 'input_capacity',
            'output_hopper_capacity': 'output_capacity'
        }
        
        return replacements.get(clean, clean)

    def extract_printer_data(self, url):
        """Extract comprehensive printer data for WooCommerce"""
        soup = self.get_page(url)
        if not soup:
            return None
            
        data = {
            # Core product info
            'url': url,
            'scraped_date': datetime.now().isoformat(),
            'brand': '',
            'model': '',
            'full_name': '',
            'product_slug': '',
            
            # Content
            'description': '',
            'short_description': '',
            'highlights': '',
            
            # Pricing & Stock
            'price': '',
            'regular_price': '',
            'regular_price_aud': '',  # NEW: AUD pricing
            'sale_price': '',
            'sale_price_aud': '',     # NEW: AUD sale price
            'stock_status': 'instock',
            'stock_quantity': '',
            'backorders': 'no',
            
            # Images & Media
            'featured_image': '',
            'gallery_images': '',
            
            # Categorization
            'categories': '',
            'tags': '',
            
            # Shipping
            'weight': '',
            'length': '',
            'width': '',
            'height': '',
            
            # SEO
            'meta_description': '',
            'meta_keywords': '',
            'schema_data': '',
            
            # Related products
            'related_products': '',
            'cross_sells': '',
            
            # Additional WooCommerce fields
            'product_type': 'simple',
            'visibility': 'visible',
            'tax_status': 'taxable',
            'tax_class': '',
            'manage_stock': 'yes',
            'featured': 'no'
        }
        
        try:
            title = soup.find('title')
            if title:
                data['full_name'] = title.text.strip()
                
            h1 = soup.find('h1')
            if h1:
                data['model'] = h1.text.strip()
            elif title:
                data['model'] = title.text.split('|')[0].strip()
            
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
            
            data['product_slug'] = self.generate_product_slug(data['model'], data['brand'])
            
            data['description'] = self.extract_product_description(soup)
            data['highlights'] = self.extract_product_highlights(soup)
            
            if data['highlights']:
                highlight_text = BeautifulSoup(data['highlights'], 'html.parser').get_text()
                data['short_description'] = highlight_text[:200] + '...' if len(highlight_text) > 200 else highlight_text
            elif data['description']:
                desc_soup = BeautifulSoup(data['description'], 'html.parser')
                first_p = desc_soup.find('p')
                if first_p:
                    data['short_description'] = first_p.get_text()[:200] + '...'
            
            specifications = self.extract_specifications_table(soup)
            data.update(specifications)
            
            images = self.extract_product_images(soup)
            if images:
                data['featured_image'] = images[0]
                data['gallery_images'] = '|'.join(images[1:])
            
            categories = self.extract_product_categories(soup)
            data['categories'] = '|'.join(categories)
            
            tags = self.extract_product_tags(soup, data)
            data['tags'] = '|'.join(tags)
            
            stock_info = self.extract_stock_availability(soup)
            data.update(stock_info)
            
            # Extract shipping dimensions with conversion (UPDATED)
            dimensions_text = specifications.get('dimensions_weight', '') or specifications.get('weight', '') or specifications.get('dimensions', '')
            if dimensions_text:
                parsed_dims = self.parse_dimensions(dimensions_text)
                data['length'] = parsed_dims['length']
                data['width'] = parsed_dims['width'] 
                data['height'] = parsed_dims['height']
                data['weight'] = parsed_dims['weight']
            
            seo_info = self.extract_seo_data(soup)
            data.update(seo_info)
            
            related = self.extract_related_products(soup)
            data['related_products'] = '|'.join([p['url'] for p in related])
            data['cross_sells'] = ''
            
            # Extract price from specific container (UPDATED)
            price = self.extract_price_from_container(soup)
            if price:
                data['price'] = price
                data['regular_price'] = price
            else:
                # Fallback to general text search
                page_text = soup.get_text()
                price_match = re.search(r'\$[\d,]+\.?\d*', page_text)
                if price_match:
                    price_str = price_match.group().replace('
                
        except Exception as e:
            logger.error(f"Error extracting from {url}: {e}")
            
        return data if data['model'] else None

    def scrape_all_printers(self):
        """Main scraping method"""
        logger.info("🕷️ Starting WooCommerce-optimized scraper...")
        
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
                usd_price = data.get('price', 'N/A')
                aud_price = data.get('regular_price_aud', 'N/A')
                images_count = len(data['gallery_images'].split('|')) if data['gallery_images'] else 0
                logger.info(f"✅ {data['brand']} {data['model']} | USD: ${usd_price} | AUD: ${aud_price} | Images: {images_count}")
            else:
                logger.warning(f"❌ Failed to extract data from {url}")
                
        logger.info(f"🎉 Completed! Scraped {len(self.printers_data)} printers")
        return self.printers_data

    def save_results(self):
        """Save results optimized for WooCommerce import"""
        if not self.printers_data:
            logger.warning("No data to save!")
            return
        
        woo_fields = [
            'product_type', 'product_slug', 'full_name', 'short_description', 'description',
            'regular_price', 'regular_price_aud', 'sale_price', 'sale_price_aud', 
            'stock_status', 'stock_quantity', 'manage_stock',
            'categories', 'tags', 'featured_image', 'gallery_images',
            'weight', 'length', 'width', 'height',
            'brand', 'model', 'highlights',
            'url', 'scraped_date', 'price', 'backorders', 'visibility', 'featured',
            'meta_description', 'meta_keywords', 'related_products', 'cross_sells',
            'tax_status', 'tax_class', 'schema_data'
        ]
        
        spec_fields = sorted(list(self.all_spec_columns))
        all_fields = woo_fields + spec_fields
        
        for record in self.printers_data:
            for field in all_fields:
                if field not in record:
                    record[field] = ''
            
        with open('alphacard_printers_woocommerce.csv', 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=all_fields)
            writer.writeheader()
            writer.writerows(self.printers_data)
        logger.info(f"💾 Saved WooCommerce CSV: {len(self.printers_data)} printers")
        
        woo_import_fields = [
            'product_type', 'product_slug', 'full_name', 'short_description', 'description',
            'regular_price', 'regular_price_aud', 'stock_status', 'categories', 'tags', 
            'featured_image', 'gallery_images', 'weight', 'length', 'width', 'height'
        ]
        
        with open('woocommerce_import_ready.csv', 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=woo_import_fields)
            writer.writeheader()
            for record in self.printers_data:
                woo_record = {field: record.get(field, '') for field in woo_import_fields}
                writer.writerow(woo_record)
        logger.info(f"💾 Saved WooCommerce import-ready CSV")
        
        with open('alphacard_printers.json', 'w', encoding='utf-8') as f:
            json.dump(self.printers_data, f, indent=2, ensure_ascii=False)
        
        summary = {
            'total_printers': len(self.printers_data),
            'scraped_at': datetime.now().isoformat(),
            'woocommerce_ready': True,
            'currency_conversion_rate': 0.62,  # USD per AUD (0.62 USD = 1 AUD)
            'with_usd_prices': sum(1 for p in self.printers_data if p.get('price')),
            'with_aud_prices': sum(1 for p in self.printers_data if p.get('regular_price_aud')),
            'with_images': sum(1 for p in self.printers_data if p.get('featured_image')),
            'with_descriptions': sum(1 for p in self.printers_data if p.get('description')),
            'with_highlights': sum(1 for p in self.printers_data if p.get('highlights')),
            'with_categories': sum(1 for p in self.printers_data if p.get('categories')),
            'avg_images_per_product': 0,
            'price_range_usd': {'min': 0, 'max': 0, 'avg': 0},
            'price_range_aud': {'min': 0, 'max': 0, 'avg': 0}
        }
        
        total_images = sum(len(p.get('gallery_images', '').split('|')) + (1 if p.get('featured_image') else 0) 
                          for p in self.printers_data)
        if self.printers_data:
            summary['avg_images_per_product'] = round(total_images / len(self.printers_data), 1)
        
        with open('scrape_summary.json', 'w') as f:
            json.dump(summary, f, indent=2)
            
        logger.info("📊 WooCommerce Summary:")
        logger.info(f"  Total products: {summary['total_printers']}")
        logger.info(f"  With USD prices: {summary['with_usd_prices']}")
        logger.info(f"  With AUD prices: {summary['with_aud_prices']}")
        logger.info(f"  USD price range: ${summary['price_range_usd']['min']}-${summary['price_range_usd']['max']} (avg: ${summary['price_range_usd']['avg']})")
        logger.info(f"  AUD price range: ${summary['price_range_aud']['min']}-${summary['price_range_aud']['max']} (avg: ${summary['price_range_aud']['avg']})")
        logger.info(f"  With images: {summary['with_images']}")
        logger.info(f"  Avg images per product: {summary['avg_images_per_product']}")
        logger.info(f"  Currency conversion: $0.62 USD = $1.00 AUD")
        logger.info(f"  Ready for WooCommerce import: ✅")

def main():
    scraper = WooCommerceAlphaCardScraper()
    
    try:
        printers = scraper.scrape_all_printers()
        
        if printers:
            scraper.save_results()
            logger.info("🎯 WooCommerce scraping completed successfully!")
        else:
            logger.error("💥 No printers scraped!")
            exit(1)
            
    except Exception as e:
        logger.error(f"💥 Scraping failed: {e}")
        exit(1)

if __name__ == "__main__":
    main()
, '').replace(',', '')
                    data['price'] = price_str
                    data['regular_price'] = price_str
                
        except Exception as e:
            logger.error(f"Error extracting from {url}: {e}")
            
        return data if data['model'] else None

    def scrape_all_printers(self):
        """Main scraping method"""
        logger.info("🕷️ Starting WooCommerce-optimized scraper...")
        
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
                logger.info(f"✅ {data['brand']} {data['model']} | Price: ${data.get('price', 'N/A')} | Images: {len(data['gallery_images'].split('|')) if data['gallery_images'] else 0}")
            else:
                logger.warning(f"❌ Failed to extract data from {url}")
                
        logger.info(f"🎉 Completed! Scraped {len(self.printers_data)} printers")
        return self.printers_data

    def save_results(self):
        """Save results optimized for WooCommerce import"""
        if not self.printers_data:
            logger.warning("No data to save!")
            return
        
        woo_fields = [
            'product_type', 'product_slug', 'full_name', 'short_description', 'description',
            'regular_price', 'sale_price', 'stock_status', 'stock_quantity', 'manage_stock',
            'categories', 'tags', 'featured_image', 'gallery_images',
            'weight', 'length', 'width', 'height',
            'brand', 'model', 'highlights',
            'url', 'scraped_date', 'price', 'backorders', 'visibility', 'featured',
            'meta_description', 'meta_keywords', 'related_products', 'cross_sells',
            'tax_status', 'tax_class', 'schema_data'
        ]
        
        spec_fields = sorted(list(self.all_spec_columns))
        all_fields = woo_fields + spec_fields
        
        for record in self.printers_data:
            for field in all_fields:
                if field not in record:
                    record[field] = ''
            
        with open('alphacard_printers_woocommerce.csv', 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=all_fields)
            writer.writeheader()
            writer.writerows(self.printers_data)
        logger.info(f"💾 Saved WooCommerce CSV: {len(self.printers_data)} printers")
        
        woo_import_fields = [
            'product_type', 'product_slug', 'full_name', 'short_description', 'description',
            'regular_price', 'stock_status', 'categories', 'tags', 'featured_image', 
            'gallery_images', 'weight', 'length', 'width', 'height'
        ]
        
        with open('woocommerce_import_ready.csv', 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=woo_import_fields)
            writer.writeheader()
            for record in self.printers_data:
                woo_record = {field: record.get(field, '') for field in woo_import_fields}
                writer.writerow(woo_record)
        logger.info(f"💾 Saved WooCommerce import-ready CSV")
        
        with open('alphacard_printers.json', 'w', encoding='utf-8') as f:
            json.dump(self.printers_data, f, indent=2, ensure_ascii=False)
        
        summary = {
            'total_printers': len(self.printers_data),
            'scraped_at': datetime.now().isoformat(),
            'woocommerce_ready': True,
            'with_prices': sum(1 for p in self.printers_data if p.get('price')),
            'with_images': sum(1 for p in self.printers_data if p.get('featured_image')),
            'with_descriptions': sum(1 for p in self.printers_data if p.get('description')),
            'with_highlights': sum(1 for p in self.printers_data if p.get('highlights')),
            'with_categories': sum(1 for p in self.printers_data if p.get('categories')),
            'avg_images_per_product': 0
        }
        
        total_images = sum(len(p.get('gallery_images', '').split('|')) + (1 if p.get('featured_image') else 0) 
                          for p in self.printers_data)
        if self.printers_data:
            summary['avg_images_per_product'] = round(total_images / len(self.printers_data), 1)
        
        with open('scrape_summary.json', 'w') as f:
            json.dump(summary, f, indent=2)
            
        logger.info("📊 WooCommerce Summary:")
        logger.info(f"  Total products: {summary['total_printers']}")
        logger.info(f"  With prices: {summary['with_prices']}")
        logger.info(f"  With images: {summary['with_images']}")
        logger.info(f"  Avg images per product: {summary['avg_images_per_product']}")
        logger.info(f"  Ready for WooCommerce import: ✅")

def main():
    scraper = WooCommerceAlphaCardScraper()
    
    try:
        printers = scraper.scrape_all_printers()
        
        if printers:
            scraper.save_results()
            logger.info("🎯 WooCommerce scraping completed successfully!")
        else:
            logger.error("💥 No printers scraped!")
            exit(1)
            
    except Exception as e:
        logger.error(f"💥 Scraping failed: {e}")
        exit(1)

if __name__ == "__main__":
    main()
, '').replace(',', '').strip()
            if not clean_price:
                return ''
                
            usd_amount = float(clean_price)
            # Convert USD to AUD (if 1 USD = 0.62 AUD, then AUD = USD * 0.62)
            aud_amount = usd_amount * conversion_rate
            
            # Round to 2 decimal places for currency
            aud_rounded = round(aud_amount, 2)
            
            logger.info(f"💱 Converted ${usd_amount} USD → ${aud_rounded} AUD (rate: {conversion_rate})")
            return str(aud_rounded)
            
        except (ValueError, TypeError) as e:
            logger.warning(f"⚠️ Error converting price to AUD: {e}")
            return ''
        """Extract price from the specific price container"""
        price = ''
        
        # Look for the specific price container pattern
        price_selectors = [
            # Primary selector for the specific container
            'span[id*="product-price"] span.price',
            'span[data-price-amount] span.price',
            '.price-wrapper span.price',
            
            # Fallback selectors
            '.price-box .price',
            '.regular-price .price',
            '.special-price .price',
            '.price',
            '[class*="price"] [class*="price"]'
        ]
        
        for selector in price_selectors:
            price_element = soup.select_one(selector)
            if price_element:
                price_text = price_element.get_text(strip=True)
                # Extract numerical price
                price_match = re.search(r'\$?([\d,]+\.?\d*)', price_text)
                if price_match:
                    price = price_match.group(1).replace(',', '')
                    logger.info(f"✅ Found price: ${price} using selector: {selector}")
                    break
        
        # Also check for data-price-amount attribute
        if not price:
            price_container = soup.select_one('[data-price-amount]')
            if price_container:
                price_amount = price_container.get('data-price-amount')
                if price_amount:
                    try:
                        price = str(float(price_amount))
                        logger.info(f"✅ Found price from data attribute: ${price}")
                    except ValueError:
                        pass
        
        if not price:
            logger.warning("⚠️ No price found in containers")
        
        return price

    def generate_product_slug(self, model, brand):
        """Generate WooCommerce-friendly URL slug"""
        slug_text = f"{brand} {model}".lower()
        slug = re.sub(r'[^\w\s-]', '', slug_text)
        slug = re.sub(r'[-\s]+', '-', slug)
        slug = slug.strip('-')
        return slug

    def extract_product_description(self, soup):
        """Extract the detailed product description HTML without wrapper divs"""
        description_html = ""
        
        desc_div = soup.find('div', class_='product attribute description')
        if desc_div:
            value_div = desc_div.find('div', class_='value')
            if value_div:
                inner_div = value_div.find('div', attrs={'data-content-type': 'html'})
                if inner_div:
                    description_html = inner_div.decode_contents()
                    logger.info("✅ Found detailed product description (clean)")
                else:
                    description_html = value_div.decode_contents()
                    logger.info("✅ Found description content (fallback)")
            else:
                description_html = desc_div.decode_contents()
                logger.info("✅ Found description (outer fallback)")
        
        if description_html:
            description_html = re.sub(r'<div[^>]*data-content-type="html"[^>]*>', '', description_html)
            description_html = re.sub(r'<div[^>]*data-appearance="default"[^>]*>', '', description_html)
            description_html = re.sub(r'<div[^>]*data-element="main"[^>]*>', '', description_html)
            description_html = re.sub(r'<div[^>]*data-decoded="true"[^>]*>', '', description_html)
            description_html = re.sub(r'<div[^>]*class="value"[^>]*>', '', description_html)
            
            open_divs = len(re.findall(r'<div[^>]*>', description_html))
            close_divs = len(re.findall(r'</div>', description_html))
            excess_closes = close_divs - open_divs
            if excess_closes > 0:
                for _ in range(excess_closes):
                    description_html = re.sub(r'</div>(?!.*</div>)', '', description_html, count=1)
            
            description_html = re.sub(r'\s+', ' ', description_html).strip()
        
        return description_html

    def extract_product_highlights(self, soup):
        """Extract product highlights as clean HTML"""
        highlights_html = ""
        
        highlights_div = soup.find('div', class_='product attribute highlights')
        if highlights_div:
            value_div = highlights_div.find('div', class_='value')
            if value_div:
                highlights_html = value_div.decode_contents()
                logger.info("✅ Found product highlights")
        
        if highlights_html:
            highlights_html = re.sub(r'<div[^>]*class="value"[^>]*>', '', highlights_html)
            highlights_html = re.sub(r'\s+', ' ', highlights_html).strip()
        
        return highlights_html

    def extract_specifications_table(self, soup):
        """Extract specifications from the table"""
        specs = {}
        
        spec_table = soup.find('table', {'id': 'product-attribute-specs-table'})
        if not spec_table:
            spec_table = soup.find('table', class_='additional-attributes')
            if not spec_table:
                spec_table = soup.find('table', class_='data table')
        
        if spec_table:
            rows = spec_table.find_all('tr')
            logger.info(f"✅ Found specifications table with {len(rows)} rows")
            
            for row in rows:
                header = row.find('th', class_='col label')
                data = row.find('td', class_='col data')
                
                if header and data:
                    key = header.get_text(strip=True)
                    value = data.get_text(strip=True)
                    
                    clean_key = self.clean_column_name(key)
                    if clean_key and value:
                        # Apply unit conversion to specification values
                        converted_value = self.convert_measurements(value)
                        specs[clean_key] = converted_value
                        self.all_spec_columns.add(clean_key)
        
        return specs

    def clean_column_name(self, name):
        """Clean column names to be CSV-friendly"""
        if not name:
            return None
            
        clean = re.sub(r'[^\w\s]', '', name.lower())
        clean = re.sub(r'\s+', '_', clean.strip())
        clean = clean.replace('_options', '').replace('_capability', '').replace('_accepted', '')
        
        replacements = {
            'weight_dimensions': 'dimensions_weight',
            'os_compatibility': 'operating_systems', 
            'card_sizes_accepted': 'card_sizes',
            'card_thickness_accepted': 'card_thickness',
            'printer_color_capability': 'color_capability',
            'print_resolution_dpi': 'print_resolution',
            'printing_speeds_seccard': 'print_speed_seconds',
            'printing_capability': 'print_sides',
            'input_hopper_capacity': 'input_capacity',
            'output_hopper_capacity': 'output_capacity'
        }
        
        return replacements.get(clean, clean)

    def extract_printer_data(self, url):
        """Extract comprehensive printer data for WooCommerce"""
        soup = self.get_page(url)
        if not soup:
            return None
            
        data = {
            # Core product info
            'url': url,
            'scraped_date': datetime.now().isoformat(),
            'brand': '',
            'model': '',
            'full_name': '',
            'product_slug': '',
            
            # Content
            'description': '',
            'short_description': '',
            'highlights': '',
            
            # Pricing & Stock
            'price': '',
            'regular_price': '',
            'sale_price': '',
            'stock_status': 'instock',
            'stock_quantity': '',
            'backorders': 'no',
            
            # Images & Media
            'featured_image': '',
            'gallery_images': '',
            
            # Categorization
            'categories': '',
            'tags': '',
            
            # Shipping
            'weight': '',
            'length': '',
            'width': '',
            'height': '',
            
            # SEO
            'meta_description': '',
            'meta_keywords': '',
            'schema_data': '',
            
            # Related products
            'related_products': '',
            'cross_sells': '',
            
            # Additional WooCommerce fields
            'product_type': 'simple',
            'visibility': 'visible',
            'tax_status': 'taxable',
            'tax_class': '',
            'manage_stock': 'yes',
            'featured': 'no'
        }
        
        try:
            title = soup.find('title')
            if title:
                data['full_name'] = title.text.strip()
                
            h1 = soup.find('h1')
            if h1:
                data['model'] = h1.text.strip()
            elif title:
                data['model'] = title.text.split('|')[0].strip()
            
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
            
            data['product_slug'] = self.generate_product_slug(data['model'], data['brand'])
            
            data['description'] = self.extract_product_description(soup)
            data['highlights'] = self.extract_product_highlights(soup)
            
            if data['highlights']:
                highlight_text = BeautifulSoup(data['highlights'], 'html.parser').get_text()
                data['short_description'] = highlight_text[:200] + '...' if len(highlight_text) > 200 else highlight_text
            elif data['description']:
                desc_soup = BeautifulSoup(data['description'], 'html.parser')
                first_p = desc_soup.find('p')
                if first_p:
                    data['short_description'] = first_p.get_text()[:200] + '...'
            
            specifications = self.extract_specifications_table(soup)
            data.update(specifications)
            
            images = self.extract_product_images(soup)
            if images:
                data['featured_image'] = images[0]
                data['gallery_images'] = '|'.join(images[1:])
            
            categories = self.extract_product_categories(soup)
            data['categories'] = '|'.join(categories)
            
            tags = self.extract_product_tags(soup, data)
            data['tags'] = '|'.join(tags)
            
            stock_info = self.extract_stock_availability(soup)
            data.update(stock_info)
            
            # Extract shipping dimensions with conversion (UPDATED)
            dimensions_text = specifications.get('dimensions_weight', '') or specifications.get('weight', '') or specifications.get('dimensions', '')
            if dimensions_text:
                parsed_dims = self.parse_dimensions(dimensions_text)
                data['length'] = parsed_dims['length']
                data['width'] = parsed_dims['width'] 
                data['height'] = parsed_dims['height']
                data['weight'] = parsed_dims['weight']
            
            seo_info = self.extract_seo_data(soup)
            data.update(seo_info)
            
            related = self.extract_related_products(soup)
            data['related_products'] = '|'.join([p['url'] for p in related])
            data['cross_sells'] = ''
            
            # Extract price from specific container (UPDATED)
            price = self.extract_price_from_container(soup)
            if price:
                data['price'] = price
                data['regular_price'] = price
            else:
                # Fallback to general text search
                page_text = soup.get_text()
                price_match = re.search(r'\$[\d,]+\.?\d*', page_text)
                if price_match:
                    price_str = price_match.group().replace('
                
        except Exception as e:
            logger.error(f"Error extracting from {url}: {e}")
            
        return data if data['model'] else None

    def scrape_all_printers(self):
        """Main scraping method"""
        logger.info("🕷️ Starting WooCommerce-optimized scraper...")
        
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
                logger.info(f"✅ {data['brand']} {data['model']} | Price: ${data.get('price', 'N/A')} | Images: {len(data['gallery_images'].split('|')) if data['gallery_images'] else 0}")
            else:
                logger.warning(f"❌ Failed to extract data from {url}")
                
        logger.info(f"🎉 Completed! Scraped {len(self.printers_data)} printers")
        return self.printers_data

    def save_results(self):
        """Save results optimized for WooCommerce import"""
        if not self.printers_data:
            logger.warning("No data to save!")
            return
        
        woo_fields = [
            'product_type', 'product_slug', 'full_name', 'short_description', 'description',
            'regular_price', 'sale_price', 'stock_status', 'stock_quantity', 'manage_stock',
            'categories', 'tags', 'featured_image', 'gallery_images',
            'weight', 'length', 'width', 'height',
            'brand', 'model', 'highlights',
            'url', 'scraped_date', 'price', 'backorders', 'visibility', 'featured',
            'meta_description', 'meta_keywords', 'related_products', 'cross_sells',
            'tax_status', 'tax_class', 'schema_data'
        ]
        
        spec_fields = sorted(list(self.all_spec_columns))
        all_fields = woo_fields + spec_fields
        
        for record in self.printers_data:
            for field in all_fields:
                if field not in record:
                    record[field] = ''
            
        with open('alphacard_printers_woocommerce.csv', 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=all_fields)
            writer.writeheader()
            writer.writerows(self.printers_data)
        logger.info(f"💾 Saved WooCommerce CSV: {len(self.printers_data)} printers")
        
        woo_import_fields = [
            'product_type', 'product_slug', 'full_name', 'short_description', 'description',
            'regular_price', 'stock_status', 'categories', 'tags', 'featured_image', 
            'gallery_images', 'weight', 'length', 'width', 'height'
        ]
        
        with open('woocommerce_import_ready.csv', 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=woo_import_fields)
            writer.writeheader()
            for record in self.printers_data:
                woo_record = {field: record.get(field, '') for field in woo_import_fields}
                writer.writerow(woo_record)
        logger.info(f"💾 Saved WooCommerce import-ready CSV")
        
        with open('alphacard_printers.json', 'w', encoding='utf-8') as f:
            json.dump(self.printers_data, f, indent=2, ensure_ascii=False)
        
        summary = {
            'total_printers': len(self.printers_data),
            'scraped_at': datetime.now().isoformat(),
            'woocommerce_ready': True,
            'with_prices': sum(1 for p in self.printers_data if p.get('price')),
            'with_images': sum(1 for p in self.printers_data if p.get('featured_image')),
            'with_descriptions': sum(1 for p in self.printers_data if p.get('description')),
            'with_highlights': sum(1 for p in self.printers_data if p.get('highlights')),
            'with_categories': sum(1 for p in self.printers_data if p.get('categories')),
            'avg_images_per_product': 0
        }
        
        total_images = sum(len(p.get('gallery_images', '').split('|')) + (1 if p.get('featured_image') else 0) 
                          for p in self.printers_data)
        if self.printers_data:
            summary['avg_images_per_product'] = round(total_images / len(self.printers_data), 1)
        
        with open('scrape_summary.json', 'w') as f:
            json.dump(summary, f, indent=2)
            
        logger.info("📊 WooCommerce Summary:")
        logger.info(f"  Total products: {summary['total_printers']}")
        logger.info(f"  With prices: {summary['with_prices']}")
        logger.info(f"  With images: {summary['with_images']}")
        logger.info(f"  Avg images per product: {summary['avg_images_per_product']}")
        logger.info(f"  Ready for WooCommerce import: ✅")

def main():
    scraper = WooCommerceAlphaCardScraper()
    
    try:
        printers = scraper.scrape_all_printers()
        
        if printers:
            scraper.save_results()
            logger.info("🎯 WooCommerce scraping completed successfully!")
        else:
            logger.error("💥 No printers scraped!")
            exit(1)
            
    except Exception as e:
        logger.error(f"💥 Scraping failed: {e}")
        exit(1)

if __name__ == "__main__":
    main()
, '').replace(',', '')
                    data['price'] = price_str
                    data['regular_price'] = price_str
                
        except Exception as e:
            logger.error(f"Error extracting from {url}: {e}")
            
        return data if data['model'] else None

    def scrape_all_printers(self):
        """Main scraping method"""
        logger.info("🕷️ Starting WooCommerce-optimized scraper...")
        
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
                logger.info(f"✅ {data['brand']} {data['model']} | Price: ${data.get('price', 'N/A')} | Images: {len(data['gallery_images'].split('|')) if data['gallery_images'] else 0}")
            else:
                logger.warning(f"❌ Failed to extract data from {url}")
                
        logger.info(f"🎉 Completed! Scraped {len(self.printers_data)} printers")
        return self.printers_data

    def save_results(self):
        """Save results optimized for WooCommerce import"""
        if not self.printers_data:
            logger.warning("No data to save!")
            return
        
        woo_fields = [
            'product_type', 'product_slug', 'full_name', 'short_description', 'description',
            'regular_price', 'sale_price', 'stock_status', 'stock_quantity', 'manage_stock',
            'categories', 'tags', 'featured_image', 'gallery_images',
            'weight', 'length', 'width', 'height',
            'brand', 'model', 'highlights',
            'url', 'scraped_date', 'price', 'backorders', 'visibility', 'featured',
            'meta_description', 'meta_keywords', 'related_products', 'cross_sells',
            'tax_status', 'tax_class', 'schema_data'
        ]
        
        spec_fields = sorted(list(self.all_spec_columns))
        all_fields = woo_fields + spec_fields
        
        for record in self.printers_data:
            for field in all_fields:
                if field not in record:
                    record[field] = ''
            
        with open('alphacard_printers_woocommerce.csv', 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=all_fields)
            writer.writeheader()
            writer.writerows(self.printers_data)
        logger.info(f"💾 Saved WooCommerce CSV: {len(self.printers_data)} printers")
        
        woo_import_fields = [
            'product_type', 'product_slug', 'full_name', 'short_description', 'description',
            'regular_price', 'stock_status', 'categories', 'tags', 'featured_image', 
            'gallery_images', 'weight', 'length', 'width', 'height'
        ]
        
        with open('woocommerce_import_ready.csv', 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=woo_import_fields)
            writer.writeheader()
            for record in self.printers_data:
                woo_record = {field: record.get(field, '') for field in woo_import_fields}
                writer.writerow(woo_record)
        logger.info(f"💾 Saved WooCommerce import-ready CSV")
        
        with open('alphacard_printers.json', 'w', encoding='utf-8') as f:
            json.dump(self.printers_data, f, indent=2, ensure_ascii=False)
        
        summary = {
            'total_printers': len(self.printers_data),
            'scraped_at': datetime.now().isoformat(),
            'woocommerce_ready': True,
            'with_prices': sum(1 for p in self.printers_data if p.get('price')),
            'with_images': sum(1 for p in self.printers_data if p.get('featured_image')),
            'with_descriptions': sum(1 for p in self.printers_data if p.get('description')),
            'with_highlights': sum(1 for p in self.printers_data if p.get('highlights')),
            'with_categories': sum(1 for p in self.printers_data if p.get('categories')),
            'avg_images_per_product': 0
        }
        
        total_images = sum(len(p.get('gallery_images', '').split('|')) + (1 if p.get('featured_image') else 0) 
                          for p in self.printers_data)
        if self.printers_data:
            summary['avg_images_per_product'] = round(total_images / len(self.printers_data), 1)
        
        with open('scrape_summary.json', 'w') as f:
            json.dump(summary, f, indent=2)
            
        logger.info("📊 WooCommerce Summary:")
        logger.info(f"  Total products: {summary['total_printers']}")
        logger.info(f"  With prices: {summary['with_prices']}")
        logger.info(f"  With images: {summary['with_images']}")
        logger.info(f"  Avg images per product: {summary['avg_images_per_product']}")
        logger.info(f"  Ready for WooCommerce import: ✅")

def main():
    scraper = WooCommerceAlphaCardScraper()
    
    try:
        printers = scraper.scrape_all_printers()
        
        if printers:
            scraper.save_results()
            logger.info("🎯 WooCommerce scraping completed successfully!")
        else:
            logger.error("💥 No printers scraped!")
            exit(1)
            
    except Exception as e:
        logger.error(f"💥 Scraping failed: {e}")
        exit(1)

if __name__ == "__main__":
    main()

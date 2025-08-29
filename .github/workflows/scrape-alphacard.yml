# .github/workflows/scrape-alphacard.yml
name: Scrape AlphaCard Printers

on:
  workflow_dispatch: # Manual triggering only
    inputs:
      max_printers:
        description: 'Maximum number of printers to scrape (optional)'
        required: false
        default: '1000'
      delay_seconds:
        description: 'Delay between requests (seconds)'
        required: false
        default: '2'
  push:
    branches: [ main ]
    paths: 
      - 'scraper/**'
      - '.github/workflows/**'

jobs:
  scrape:
    runs-on: ubuntu-latest
    
    steps:
    - name: Checkout repository
      uses: actions/checkout@v4
    
    - name: Set up Python
      uses: actions/setup-python@v5
      with:
        python-version: '3.12'
    
    - name: Install dependencies
      run: |
        python -m pip install --upgrade pip
        pip install requests beautifulsoup4 lxml pandas
    
    - name: Run scraper
      run: |
        cd scraper
        python alphacard_scraper.py
      env:
        PYTHONUNBUFFERED: 1
        MAX_PRINTERS: ${{ github.event.inputs.max_printers }}
        SCRAPER_DELAY: ${{ github.event.inputs.delay_seconds }}
    
    - name: Check results and display summary
      run: |
        cd scraper
        if [ -f "alphacard_printers_woocommerce.csv" ]; then
          echo "✅ WooCommerce CSV file created successfully"
          echo "📊 Number of lines: $(wc -l < alphacard_printers_woocommerce.csv)"
          echo "📄 File size: $(ls -lh alphacard_printers_woocommerce.csv | awk '{print $5}')"
          
          if [ -f "woocommerce_import_ready.csv" ]; then
            echo "✅ Import-ready CSV created successfully"
            echo "📊 Import CSV lines: $(wc -l < woocommerce_import_ready.csv)"
            echo "📄 Import CSV size: $(ls -lh woocommerce_import_ready.csv | awk '{print $5}')"
          fi
          
          # Show first few lines of main CSV
          echo ""
          echo "📋 First 3 lines of WooCommerce CSV:"
          head -3 alphacard_printers_woocommerce.csv
          
          # Show summary if available
          if [ -f "scrape_summary.json" ]; then
            echo ""
            echo "📊 Scraping Summary:"
            cat scrape_summary.json | python -m json.tool
          fi
        else
          echo "❌ WooCommerce CSV file not found"
          echo "📁 Files in directory:"
          ls -la
          exit 1
        fi
    
    - name: Upload results as artifacts
      uses: actions/upload-artifact@v4
      if: always()
      with:
        name: alphacard-printers-data-${{ github.run_number }}
        path: |
          scraper/alphacard_printers_woocommerce.csv
          scraper/woocommerce_import_ready.csv
          scraper/alphacard_printers.json
          scraper/scrape_summary.json
        retention-days: 30
        compression-level: 6

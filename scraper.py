import time
import pandas as pd
from selenium import webdriver
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.common.exceptions import NoSuchElementException
import os

def get_driver():
    chrome_options = webdriver.ChromeOptions()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    
    # Check if running on Render (or Linux environment where we might need specific binary location)
    # For local windows, ChromeDriverManager handles it.
    # For Render, we usually need to specify the binary location if we use a buildpack, 
    # but webdriver_manager is often enough if chrome is in path.
    # We will stick to standard setup which works on local and often on cloud if chrome is installed.
    
    try:
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=chrome_options)
        return driver
    except Exception as e:
        print(f"Error setting up driver: {e}")
        return None

def scrape_nahdi(base_url_input, progress_callback=None, pause_event=None):
    driver = get_driver()
    if not driver:
        return None, 0, 0

    products = []
    
    # Handle URL formatting for pagination
    # If URL already has query params, we might need to be careful.
    # Assuming the user gives a PLP url like .../plp/12345
    if "?page=" in base_url_input:
        base_url = base_url_input.split("?page=")[0] + "?page={}"
    elif "?" in base_url_input:
        base_url = base_url_input + "&page={}"
    else:
        base_url = base_url_input + "?page={}"

    page = 1
    scraped_pages_count = 0
    
    try:
        while True:
            # Check for pause
            if pause_event:
                pause_event.wait()

            url = base_url.format(page)
            print(f"Scraping {url}")
            driver.get(url)
            time.sleep(5) # Wait for load

            # Scroll to bottom
            last_height = driver.execute_script("return document.body.scrollHeight")
            while True:
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(2)
                new_height = driver.execute_script("return document.body.scrollHeight")
                if new_height == last_height:
                    break
                last_height = new_height
            
            # Find products
            product_cards = driver.find_elements(By.CSS_SELECTOR, "a.flex.h-full.flex-col")
            
            if not product_cards:
                print(f"No products found on page {page}, stopping.")
                break
                
            print(f"Found {len(product_cards)} product cards on page {page}.")
            scraped_pages_count += 1
            
            for card in product_cards:
                # Skip hidden elements (e.g. mobile/desktop duplicates or carousel items not in view)
                if not card.is_displayed():
                    continue

                try:
                    name = card.find_element(By.CSS_SELECTOR, "span.line-clamp-3.text-xs").text.strip()
                except NoSuchElementException:
                    name = ""
                
                try:
                    price_without_discount = card.find_element(By.CSS_SELECTOR, "span.flex.items-center.flex.items-center.text-custom-sm.font-semibold.lg\\:text-base.text-gray-dark").text.strip()
                except NoSuchElementException:
                    price_without_discount = ""
                
                try:
                    regular_price = card.find_element(By.CSS_SELECTOR, "span.flex.items-center.flex.items-center.text-xs.font-bold.text-gray.line-through").text.strip()
                except NoSuchElementException:
                    regular_price = ""
                
                try:
                    price_after_discount = card.find_element(By.CSS_SELECTOR, "span.flex.items-center.flex.items-center.text-custom-sm.font-semibold.lg\\:text-base.text-red").text.strip()
                except NoSuchElementException:
                    price_after_discount = ""
                
                try:
                    discount_percent = card.find_element(By.CSS_SELECTOR, "span.text-custom-xs.font-semibold.text-white").text.strip()
                except NoSuchElementException:
                    discount_percent = ""
                
                product_data = {
                    "Product Name": name,
                    "Regular Price": regular_price,
                    "Price After Discount": price_after_discount,
                    "Price Without Discount": price_without_discount,
                    "Discount %": discount_percent
                }

                # Check for duplicates in the current list
                if product_data not in products:
                    products.append(product_data)
            
            if progress_callback:
                progress_callback(scraped_pages_count, len(products))

            page += 1
            
    except Exception as e:
        print(f"Error during scraping: {e}")
    finally:
        driver.quit()
        
    return products, scraped_pages_count, len(products)

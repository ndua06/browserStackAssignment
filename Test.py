import os
import json
import requests
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

USERNAME = os.getenv("BROWSERSTACK_USERNAME")
ACCESS_KEY = os.getenv("BROWSERSTACK_ACCESS_KEY")
RAPID_API=os.getenv("RAPID_API")

# Utility functions
def click_element_by_xpath(wait, xpath):
    """Click an element using its XPath."""
    try:
        element = wait.until(EC.element_to_be_clickable((By.XPATH, xpath)))
        element.click()
    except Exception as e:
        print(f"Error clicking element {xpath}: {e}")

def get_element_text_by_xpath(wait, xpath):
    """Retrieve text of an element using its XPath."""
    try:
        element = wait.until(EC.presence_of_element_located((By.XPATH, xpath)))
        return element.text
    except Exception as e:
        print(f"Error retrieving text from element {xpath}: {e}")
        return None

def translate_text(text, from_lang="es", to_lang="en"):
    """Translate text using Google Translate API."""
    try:
        url = "https://google-translate113.p.rapidapi.com/api/v1/translator/html"
        payload = {"from": from_lang, "to": to_lang, "html": text}
        headers = {
            "x-rapidapi-key": RAPID_API,
            "x-rapidapi-host": "google-translate113.p.rapidapi.com",
            "Content-Type": "application/json"
        }
        response = requests.post(url, json=payload, headers=headers)
        if response.status_code == 200:
            return response.json().get("trans", text)
        else:
            print(f"Translation failed for '{text}': {response.text}")
            return text
    except Exception as e:
        print(f"Error translating '{text}': {e}")
        return text

def count_words(text):
    """Count word occurrences in a text."""
    words = text.lower().split()
    word_count = defaultdict(int)
    for word in words:
        word_count[word] += 1
    return word_count

# Read capabilities from JSON file
with open("capabilities.json", "r") as f:
    raw_capabilities = json.load(f)

# Preprocess capabilities to ensure uniformity
def preprocess_capabilities(capabilities):
    for cap in capabilities:
        cap["desired_capabilities"]["bstack:options"]["userName"] = USERNAME
        cap["desired_capabilities"]["bstack:options"]["accessKey"] = ACCESS_KEY
        if "browserName" not in cap["desired_capabilities"]:
            cap["desired_capabilities"]["browserName"] = "Chrome"
    return capabilities

processed_capabilities = preprocess_capabilities(raw_capabilities)

# Function to execute a single session
def execute_session(session_index, session_capabilities):
    driver = None
    try:
        # Initialize WebDriver
        options = webdriver.ChromeOptions()
        for key, value in session_capabilities.items():
            options.set_capability(key, value)

        driver = webdriver.Remote(
            command_executor=f"https://{USERNAME}:{ACCESS_KEY}@hub-cloud.browserstack.com/wd/hub",
            options=options,
        )
        wait = WebDriverWait(driver, 10)

        # Test actions
        driver.get("https://elpais.com/")
        print("Successfully opened the website.")

        # Handle cookies or pop-ups
        click_element_by_xpath(wait, '//*[@id="didomi-notice-agree-button"]')
        click_element_by_xpath(wait, '//*[@id="pmConsentWall"]/div/div/div[2]/div[1]/a')

        # Verify page language
        page_language = driver.find_element(By.TAG_NAME, "html").get_attribute("lang")
        if page_language == "es":
            print("The page is in Spanish.")
        else:
            print("The page is not in Spanish.")

        # Navigate to the Opinion section
        click_element_by_xpath(wait, '//*[@id="csw"]/div[1]/nav/div/a[3]')

        # Extract top 5 articles
        articles = driver.find_elements(By.TAG_NAME, "article")[:5]
        article_links = [
            article.find_element(By.TAG_NAME, "a").get_attribute("href")
            for article in articles if article.find_elements(By.TAG_NAME, "a")
        ]

        # Create directory for images
        if not os.path.exists("article_images"):
            os.makedirs("article_images")

        # Scrape articles
        articles_data = {}
        for idx, link in enumerate(article_links, start=1):
            driver.execute_script("window.open(arguments[0], '_blank');", link)
            driver.switch_to.window(driver.window_handles[-1])

            try:
                title = get_element_text_by_xpath(wait, "/html/body/article/header/div[1]/h1")
                content = get_element_text_by_xpath(wait, "/html/body/article/header/div[1]/h2")
                image_url = driver.find_element(By.TAG_NAME, "img").get_attribute("src")

                if title and content and image_url:
                    articles_data[idx] = {
                        "title": title,
                        "content": content,
                        "image": image_url,
                    }

                    # Save image locally
                    driver.get(image_url)
                    driver.save_screenshot(f"article_images/{title.replace(' ', '_')}.png")
            except Exception as e:
                print(f"Error processing article {idx}: {e}")
            finally:
                driver.close()
                driver.switch_to.window(driver.window_handles[0])

        # Translate article titles
        for idx, article in articles_data.items():
            translated_title = translate_text(article["title"])
            articles_data[idx]["translated_title"] = translated_title
            print(f"Article {idx} - Translated Title: {translated_title}")

        # Analyze repeated words in titles
        word_counts = defaultdict(int)
        for article in articles_data.values():
            word_count = count_words(article["translated_title"])
            for word, count in word_count.items():
                word_counts[word] += count

        print("Words repeated more than twice across titles:")
        repeated_words = {word: count for word, count in word_counts.items() if count > 2}
        if repeated_words:
            for word, count in repeated_words.items():
                print(f"{word}: {count}")

    except Exception as e:
        print(f"Error in session {session_index}: {e}")
    finally:
        if driver:
            driver.quit()

# Run sessions in parallel
def run_sessions():
    with ThreadPoolExecutor(max_workers=5) as executor:
        for index, capability in enumerate(processed_capabilities):
            executor.submit(execute_session, index, capability["desired_capabilities"])

if __name__ == "__main__":
    run_sessions()
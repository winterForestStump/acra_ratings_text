import csv
import os
import random
import time
import pandas as pd 
from tqdm import tqdm
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from selenium.common.exceptions import TimeoutException, WebDriverException
from webdriver_manager.chrome import ChromeDriverManager

INPUT_CSV = "data/links_to_ratings_initial.csv"
OUTPUT_CSV = "data/_rating_texts_.csv"   # appended to row by row (checkpoint)

MAX_RETRIES = 2             # attempts per URL
PAGE_TIMEOUT = 10           # seconds to wait for page load / element
RESTART_EVERY = 10          # restart browser every N pages
DELAY_RANGE = (3.9, 19.9)   # polite random pause between requests

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64; rv:122.0) Gecko/20100101 Firefox/122.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_5_1) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_2 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Mobile/15E148 Safari/604.1",
]

_driver_path = None

def make_browser():
    global _driver_path
    if _driver_path is None:
        _driver_path = ChromeDriverManager().install()
    opts = Options()
    opts.add_argument("--headless")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument(f"user-agent={random.choice(USER_AGENTS)}")
    browser = webdriver.Chrome(service=ChromeService(_driver_path), options=opts)
    browser.set_page_load_timeout(PAGE_TIMEOUT)
    return browser


def safe_quit(browser):
    try:
        browser.quit()
    except Exception:
        pass


def fetch_text(browser, url):
    """Returns (text, status, browser). Browser may be replaced after a failure."""
    #last_err = ""
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            browser.get(url)
            try:
                WebDriverWait(browser, PAGE_TIMEOUT).until(
                    EC.presence_of_element_located((By.CLASS_NAME, "text-content-wrapper"))
                )
            except TimeoutException:
                pass  # page loaded but no text block; handled below

            elements = browser.find_elements(By.CLASS_NAME, "text-content-wrapper")
            text = "\n".join(e.text.strip() for e in elements if e.text.strip())
            return text, ("ok" if text else "no_text"), browser

        except (WebDriverException, TimeoutException) as e:
            #last_err = type(e).__name__ + ": " + str(e).splitlines()[0][:150]
            # Session is often dead after a connection error: restart browser
            safe_quit(browser)
            time.sleep(min(60, 5 * 2 ** (attempt - 1)))  # 5, 10, 20, 40 s
            browser = make_browser()
 
    return "", "failed", browser


def load_done_links():
    """Links that were scraped successfully (ok) - skipped on resume."""
    fails = ["failed", "no_text"]
    if not os.path.exists(OUTPUT_CSV):
        return set()
    df = pd.read_csv(OUTPUT_CSV, dtype=str, on_bad_lines='warn').fillna("")
    return set(df.loc[~df["status"].isin(fails), "link"])


def main():
    issuers = pd.read_csv(INPUT_CSV)
    done = load_done_links()
    todo = issuers[~issuers["link"].isin(done)]
    print(f"{len(done)} already done, {len(todo)} to scrape")

    columns = list(issuers.columns) + ["text", "status"]
    new_file = not os.path.exists(OUTPUT_CSV)

    browser = make_browser()
    try:
        with open(OUTPUT_CSV, "a", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=columns)
            if new_file:
                writer.writeheader()

            for n, (_, row) in enumerate(tqdm(todo.iterrows(), total=len(todo), desc="Processing issuers")):
                if n and n % RESTART_EVERY == 0:
                    safe_quit(browser)
                    break_time = random.uniform(*[11.1, 22.2])
                    print(f'\nBreak for {break_time}')
                    time.sleep(break_time)
                    print('New browser')
                    browser = make_browser()

                text, status, browser = fetch_text(browser, f"{row['link']}?lang=en")
                print(f"\n{row['link']}?lang=en")
                record = row.to_dict()
                record["text"] = text
                record["status"] = status
                print(status)
                writer.writerow(record)
                f.flush()  # checkpoint every row

                time.sleep(random.uniform(*DELAY_RANGE))
    except KeyboardInterrupt:
        print("\nInterrupted - progress is saved, rerun to resume.")
    finally:
        safe_quit(browser)

    # Final de-duplicated view: keep the latest attempt per link
    out = pd.read_csv(OUTPUT_CSV, dtype=str, on_bad_lines='warn').fillna("")
    out = out.drop_duplicates(subset="link", keep="last")
    failed = out["status"].str.startswith("failed").sum()
    print(f"Total records: {len(out)} | failed: {failed}")
    if failed:
        print("Rerun the script to retry failed links.")
    out.to_csv("data/_rating_texts_final.csv", index=False, encoding="utf-8-sig")


if __name__ == "__main__":
    main()
import os
import math
import random
import pandas as pd
from bs4 import BeautifulSoup  # pip install beautifulsoup4
from tqdm import tqdm
from webdriver_manager.chrome import ChromeDriverManager
from selenium import webdriver
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64; rv:122.0) Gecko/20100101 Firefox/122.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_5_1) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_2 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Mobile/15E148 Safari/604.1",
]

chrome_options = Options()
chrome_options.add_argument("--headless")
chrome_options.add_argument("--no-sandbox")
chrome_options.add_argument("--disable-dev-shm-usage")
chrome_options.add_argument(f"user-agent={random.choice(USER_AGENTS)}")

# ---- parameters ----
wait_time = 10
show_by = 30  # max. also possible: 10 and 20

CSV_PATH = 'data/issuers_ratings_initial.csv'          # stage 1 output
DETAILS_CSV = 'data/links_to_ratings_initial.csv'      # stage 2 output
PENDING_PATH = 'data/pending_links.txt'                # issuers waiting for stage 2

KEY_COLS = ['issuer', 'link', 'sector', 'rating_scale', 'rating', 'forecast', 'date']
ROW_SELECTOR = '.emits-row__wrapper.search-table-row__wrapper'
URL = ('https://www.acra-ratings.ru/ratings/issuers/?lang=en&text=&sectors[]=&activities[]='
       '&countries[]=&forecasts[]=&on_revision=0&rating_scale=0&rate_from=0&rate_to=0'
       '&page={page}&sort=&count=' + str(show_by) + '&')

HEADER_COLS = ['full_name', 'name_rus', 'country', 'sector', 'activity', 'INN', 'OGRN']
RATING_COLS = ['scale', 'rating', 'outlook', 'date', 'link']
OUT_COLS = HEADER_COLS + RATING_COLS
DETAIL_KEY = ['full_name', 'scale', 'rating', 'outlook', 'date', 'link']


# stage 1: issuers list
def rows_in(df, other, key_cols=KEY_COLS):
    """Boolean mask: each row of df has a matching key in other."""
    keys = other[key_cols].drop_duplicates()
    merged = df[key_cols].merge(keys, on=key_cols, how='left', indicator=True)
    return (merged['_merge'] == 'both').values


def parse_rate_block(block, rate_title):
    rate_text = block.find_element(By.CSS_SELECTOR, '[data-type="rate"]').text.strip()
    parts = rate_text.split('\n')
    return {
        'rating_scale': rate_title,
        'rating': parts[0].strip(),
        'forecast': ''.join(parts[1:]).strip(),
        'sector': block.find_element(By.CSS_SELECTOR, '[data-type="sector"]').text.strip(),
        'date': block.find_element(By.CSS_SELECTOR, '[data-type="pressRelease"]').text.strip(),
    }


def parse_item(item):
    issuer = item.find_element(By.CLASS_NAME, 'emits-row__item').text.strip()
    link = item.find_element(By.TAG_NAME, 'a').get_attribute('href')
    rows = []
    scales = item.find_elements(By.CLASS_NAME, 'emits-row__row-inner')
    if scales:
        for scale in scales:
            title = scale.find_element(By.CSS_SELECTOR, '[data-type="rateTitle"]').text.strip()
            rows.append(parse_rate_block(scale, title))
    else:
        rows.append(parse_rate_block(item, 'National rating scale'))
    for r in rows:
        r.update(issuer=issuer, link=link)
    return rows


# stage 2: issuer pages scraping
def parse_rating_item(item):
    """Return (scale, rating, outlook, date, link) or None. Works on hidden elements."""
    soup_lines = BeautifulSoup(item.get_attribute('outerHTML'), 'html.parser') \
        .get_text(separator='\n', strip=True).split('\n')
    for lines in (item.text.strip().split('\n'), soup_lines):
        if len(lines) == 4:
            break
    else:
        return None

    a = item.find_elements(By.TAG_NAME, 'a')
    link = a[0].get_attribute('href') if a else ''
    outlook = ' '.join(lines[2].split()[1:])
    return lines[0], lines[1], outlook, lines[3], link


def parse_header(wait):
    header = wait.until(EC.presence_of_element_located((By.CLASS_NAME, 'issuer-header-wrap')))
    lines = header.text.strip().split('\n')
    values = lines[1::2][:len(HEADER_COLS)]
    values += [''] * (len(HEADER_COLS) - len(values))
    return dict(zip(HEADER_COLS, values))


def parse_ratings(browser, wait):
    rows = []
    for selector in ('.inner-table.green .rating-item',                  # current ratings
                     'div.rating-list.rating-list--js .rating-item'):    # history (hidden)
        try:
            wait.until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, selector)))
        except TimeoutException:
            continue
        for item in browser.find_elements(By.CSS_SELECTOR, selector):
            r = parse_rating_item(item)
            if r:
                rows.append(r)
    return rows


def load_pending():
    if not os.path.exists(PENDING_PATH):
        return []
    with open(PENDING_PATH, encoding='utf-8') as f:
        return [l.strip() for l in f if l.strip()]

def save_pending(links):
    with open(PENDING_PATH, 'w', encoding='utf-8') as f:
        f.write('\n'.join(links))

def delete_pending_if_empty():
    if os.path.exists(PENDING_PATH) and not load_pending():
        os.remove(PENDING_PATH)


def save_details(scraped):
    """Append scraped rows to DETAILS_CSV; only rows with a new DETAIL_KEY are added."""
    if os.path.exists(DETAILS_CSV):
        old = pd.read_csv(DETAILS_CSV, dtype=str, keep_default_na=False)
        old = old.loc[:, ~old.columns.str.startswith('Unnamed')]
    else:
        old = pd.DataFrame(columns=OUT_COLS)
    for col in OUT_COLS:
        if col not in old.columns:
            old[col] = ''
    old = old[OUT_COLS]

    new = pd.DataFrame(scraped, columns=OUT_COLS).fillna('').drop_duplicates(subset=DETAIL_KEY)

    # only rows whose full key is not in the file yet
    known = set(map(tuple, old[DETAIL_KEY].values))
    new = new[[k not in known for k in map(tuple, new[DETAIL_KEY].values)]]

    # drop old "no ratings" placeholders of issuers that now have real rows
    real_names = set(new.loc[new['rating'] != '', 'full_name'])
    placeholder = old['full_name'].isin(real_names) & (old['rating'] == '') & (old['scale'] == '')
    old = old[~placeholder]

    result = pd.concat([old, new], ignore_index=True)
    result.to_csv(DETAILS_CSV, index=False)
    print(f"Details: added {len(new)} new rows, total {len(result)} in {DETAILS_CSV}")


# run
existing = pd.read_csv(CSV_PATH, dtype=str, keep_default_na=False)[KEY_COLS]
print(f'Already existing rows: {len(existing)}')
sentinels_left = existing.head(2).drop_duplicates()   # file is kept newest-first

browser = webdriver.Chrome(service=ChromeService(ChromeDriverManager().install()),
                           options=chrome_options)
browser.implicitly_wait(0)  # explicit waits only
wait = WebDriverWait(browser, wait_time)

try:
    # ---------- stage 1: new rows of the issuers list ----------
    new_chunks = []
    try:
        browser.get(URL.format(page=1))
        found = wait.until(EC.presence_of_element_located(
            (By.CSS_SELECTOR, '.search-emits__results.search-results'))).text
        total_issuers = int(found.split(' ')[1]) if found else 1
        total_pages = math.ceil(total_issuers / show_by)

        for page in tqdm(range(1, total_pages + 1), desc="Issuer pages"):
            browser.get(URL.format(page=page))
            wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, ROW_SELECTOR)))
            items = browser.find_elements(By.CSS_SELECTOR, ROW_SELECTOR)

            page_rows = []
            for item in items:
                page_rows.extend(parse_item(item))
            page_df = pd.DataFrame(page_rows)[KEY_COLS]

            new_rows = page_df.loc[~rows_in(page_df, existing)]
            if not new_rows.empty:
                new_chunks.append(new_rows)
            print(f"Page {page}: {len(new_rows)} new rows.")

            if len(sentinels_left):
                sentinels_left = sentinels_left.loc[~rows_in(sentinels_left, page_df)]
                if sentinels_left.empty:
                    print(f"All sentinels found on page {page} — stopping.")
                    break
    finally:
        # save what we have, and remember which issuers still need stage 2
        pending = load_pending()
        if new_chunks:
            new_df = pd.concat(new_chunks, ignore_index=True).drop_duplicates()
            pending = list(dict.fromkeys(pending + list(new_df['link'])))
            save_pending(pending)
            existing = pd.concat([new_df, existing], ignore_index=True)  # newest first
        print(f"Total records: {len(existing)}")
        existing.to_csv(CSV_PATH, index=False)

        # ---------- stage 2: ratings of the issuers with new rows ----------
    todo = list(dict.fromkeys(load_pending()))
    print(f"Issuers to scrape in stage 2: {len(todo)}")

    scraped, done, failed = [], set(), []
    try:
        for issuer_link in tqdm(todo, desc="Issuer details"):
            sep = '&' if '?' in issuer_link else '?'
            try:
                browser.get(f"{issuer_link}{sep}lang=en")
                header = parse_header(wait)
                ratings = parse_ratings(browser, wait)
            except Exception as e:  # one bad page must not kill the run
                failed.append((issuer_link, repr(e)))
                continue

            if not ratings:  # placeholder so the issuer is known
                ratings = [('', '', '', '', '')]
            for rt in ratings:
                scraped.append({**header, **dict(zip(RATING_COLS, rt))})
            done.add(issuer_link)
    finally:
        if scraped:
            save_details(scraped)
        save_pending([l for l in todo if l not in done])   # failed / unprocessed stay pending
        if failed:
            print(f"Failed issuers ({len(failed)}), they stay in {PENDING_PATH}:")
            for link, err in failed:
                print(' ', link, err)

finally:
    browser.quit()
    delete_pending_if_empty()
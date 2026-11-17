# Rating texts from russian ACRA agency.
*Scraped data for research/learning only, see Disclaimer section. Only the agency's official website is authoritative*

## About the repo
The repo contains the texts of the credit rating press releases from [Analytical Credit Rating Agency (ACRA)](https://www.acra-ratings.ru/ratings/issuers/). ACRA was established in Russia in 2015 as a response for the US-based agencies withdrawal due to sanctions.

### the scripts
The [`issuers_scraper.py script`](`code/issuers_scraper.py`), is a Selenium-based web scraper for ACRA’s issuer ratings pages. It does two main jobs. On stage 1 it crawls the paginated issuer listing and collect issuer/rating rows. Next, on stage 2 the script revisits each issuer page (which are not yet collected!) and collect richer rating metadata (rating scale, rating, outlook, issuers sector), then save it to CSV files, avoiding re-scraping duplicate rows, with an option to resume later without losing progress (in case of access denied from the host website). At a high level the script:
- Opens a headless Chrome browser, visits the ACRA issuer search page
- Extracts issuer names, links, sectors, rating scales, ratings, forecasts, and dates
- Saves the initial results to [`data/issuers_ratings_initial.csv`](data/issuers_ratings_initial.csv)
- Keeps a pending list in `data/pending_links.txt` (it's good if you can't see the txt file, that means all the links were requested correctly and the file was discarded at the end of the session) for second-stage scraping
- Opens each issuer’s detail page and extracts full_name, country, sector, activity, INN, OGRN, rating scale, rating, outlook, date, and link. Appends only new, non-duplicate rows to [`data/links_to_ratings_initial.csv`](data/links_to_ratings_initial.csv).


The second script [`rating_texts_scraper.py script`](`code/rating_texts_scraper.py`) visits each rating link, collects the text from its page, and saves the results:
* Reads its input from [`links_to_ratings_initial.csv`](data/links_to_ratings_initial.csv), produced by the issuer scraper.
* Checks what is already done in [`_rating_texts_.csv`](data/_rating_texts_.csv). Links with status `ok` are skipped; links marked `failed` or `no_text` are tried again.
* Starts a headless Chrome browser using Selenium, visits each remaining link, waits for the page’s text section, and collects the text it finds. 
* Records a status for each link: `ok` - text was found, `no_text` - the page loaded, but no text was found, `failed` - browser or navigation errors persisted after retries.
* Saves progress after each link by appending a row to the checkpoint CSV and flushing the file. If you interrupt the run, you can rerun it; successful links are skipped. Writes a final, deduplicated CSV to [`_rating_texts_final.csv`](data/_rating_texts_final.csv), with deleting duplicated rows. The database load task uses this final file.

All scraping was conducted politely and responsibly:
* Requests were rate-limited, with waiting time between requests to avoid placing undue load on the agency's servers.
* Only publicly available pages were accessed.
* No authentication was bypassed, and no access restrictions were circumvented.

### workspace file
[`tasks.json`](.vscode/tasks.json) runs the workspace file with scripts (by hotkey ´Ctrl + Shift + B´ in VSCode). The combined task runs the issuer scraper, then the rating-text scraper, then loads the resulting texts into the database.

## Disclaimer
This repository contains text data scraped from the public website of a [Analytical Credit Rating Agency (ACRA)](https://www.acra-ratings.ru/ratings/issuers/). The data is collected and provided strictly for research and learning purposes only. It is not intended for commercial use, investment decisions, regulatory compliance, or any other purpose.

The scraped texts are provided "as is", without warranty of any kind, express or implied. While reasonable efforts were made to collect the data correctly:
* No guarantee is made that the scraped texts are free of errors, including but not limited to omissions, truncation, encoding issues, formatting artifacts, parsing mistakes, or missing documents.
* No guarantee is made that the dataset is complete — some publications may not have been captured, may have been updated or removed at the source, or may have been published after the scraping date.

Only the official website of the [Analytical Credit Rating Agency (ACRA)](https://www.acra-ratings.ru/ratings/issuers/) should be considered a reliable and authoritative source. Any information contained in this repository should be verified against the agency's official publications before being relied upon in any way. This repository and its maintainers are not affiliated with, endorsed by, or acting on behalf of the credit rating agency.
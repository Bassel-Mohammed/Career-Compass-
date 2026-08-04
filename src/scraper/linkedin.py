import requests
from bs4 import BeautifulSoup
import time
import pandas as pd

# ----------------- TEST LINKEDIN JOB SCRAPER -----------------
def scrape_linkedin_jobs(keyword, location, pages=1):
    jobs_data = []
    
    # The hidden guest endpoint that returns static HTML
    base_url = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    for page in range(pages):
        start_index = page * 25
        params = {
            "keywords": keyword,
            "location": location,
            "start": start_index
        }
        
        print(f"Scraping page {page + 1}...")
        response = requests.get(base_url, params=params, headers=headers)
        
        if response.status_code != 200:
            print(f"Failed or blocked! Status Code: {response.status_code}")
            break
            
        soup = BeautifulSoup(response.text, "html.parser")
        job_cards = soup.find_all("li")
        
        for card in job_cards:
            try:
                title_elem = card.find("h3", class_="base-search-card__title")
                company_elem = card.find("h4", class_="base-search-card__subtitle")
                location_elem = card.find("span", class_="job-search-card__location")
                link_elem = card.find("a", class_="base-card__full-link")
                
                # FIX 2: If there is no title, this isn't a real job card. Skip it.
                if not title_elem:
                    continue
                
                # FIX 3: Safely use .get("href", "") to avoid crashes
                raw_url = link_elem.get("href", "") if link_elem else ""
                clean_url = raw_url.split("?")[0] if raw_url else "N/A"
                
                job = {
                    "search_query": keyword,  # FIX 1: Save the keyword so we can group data later!
                    "title": title_elem.text.strip(),
                    "company": company_elem.text.strip() if company_elem else "N/A",
                    "location": location_elem.text.strip() if location_elem else "N/A",
                    "url": clean_url
                }
                jobs_data.append(job)
                
            except Exception as e:
                # If a specific card fails, just skip to the next one
                continue
                
        # CRITICAL: Sleep between requests so you don't get IP banned
        time.sleep(3)
        
    return jobs_data

job_search_queries = [
    "Full Stack Developer",
    "Cybersecurity Specialist",
    "DevOps Engineer AWS",
    "Data Analyst Power BI",
    "Backend Engineer Java",
    "Mobile Developer Flutter",
    "Machine Learning Engineer",
    "UI UX Designer",
    "QA Automation Engineer"
]

all_scraped_jobs = []

for query in job_search_queries:
    print(f"Scraping jobs for: {query}")
    # Searching specifically in Jordan
    scraped_jobs = scrape_linkedin_jobs(keyword=query, location="Jordan", pages=3)
    all_scraped_jobs.extend(scraped_jobs)
    print(scraped_jobs[0] if scraped_jobs else "No jobs found for this query.")
    print(f"-> Found {len(scraped_jobs)} jobs for {query}\n")

# Convert the list of dictionaries to a DataFrame
df = pd.DataFrame(all_scraped_jobs)

# Save to JSON using orient="records"
df.to_json("src/data/jobs.json", orient="records", indent=4, force_ascii=False)

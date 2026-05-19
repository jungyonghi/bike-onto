# Timestamp: 2026-04-22 00:22:00
import requests
from bs4 import BeautifulSoup
import pandas as pd
import time
import os

class FFCRScraper:
    def __init__(self):
        self.base_url = "https://db.ffcr.or.jp/front/"
        # Updated endpoint according to JS function: searchPesticide()
        self.search_url = f"{self.base_url}?m=p"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Content-Type": "application/x-www-form-urlencoded",
            "Referer": "https://db.ffcr.or.jp/front/"
        }
        self.session = requests.Session()
        # Initialize session with English language
        print("Initializing session (lng=en)...")
        self.session.get("https://db.ffcr.or.jp/front/?lng=en")

    def get_all_substance_ids(self, limit_chars=None):
        """Collect IDs using POST request."""
        print("[1/2] ID 매핑 수집 시작...")
        mapping = {}
        
        chars = "abcdefghijklmnopqrstuvwxyz"
        if limit_chars:
            chars = chars[:limit_chars]

        for char in chars:
            payload = {"pesticide_class_eng": char}
            try:
                # Actual POST call to pesticide_comp
                response = self.session.post(self.search_url, data=payload, headers=self.headers)
                
                if char == 'a':
                    print(f"DEBUG: Response length: {len(response.text)}")
                    with open("debug_response.html", "w", encoding="utf-8") as f:
                        f.write(response.text)
                    print("DEBUG: Saved response to debug_response.html")

                soup = BeautifulSoup(response.text, 'html.parser')
                
                # Rows in the results table - removing tbody for robustness
                rows = soup.select('div.list_contents table tr')
                
                char_count = 0
                for row in rows:
                    # Select the link that is NOT an excel download link
                    link = row.select_one('td a:not(.dl_xls)')
                    if link:
                        name = link.text.strip()
                        href = link.get('href', '')
                        if 'id=' in href:
                            substance_id = href.split('id=')[-1]
                            mapping[name] = substance_id
                            char_count += 1
                
                print(f" - Index '{char.upper()}' finished: {char_count} found (Total: {len(mapping)})")
                time.sleep(0.5)
                
            except Exception as e:
                print(f" ! Index '{char.upper()}' error: {e}")
            
        return mapping

    def get_mrl_details(self, substance_id):
        """Parse MRL data for a specific ID."""
        url = f"{self.base_url}pesticide_detail?id={substance_id}"
        response = self.session.get(url, headers=self.headers)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        substance_title = soup.select_one("dd.name_item strong")
        substance_name = substance_title.text.strip() if substance_title else "Unknown"
        
        results = []
        # Correct class is 'list_items'
        rows = soup.select("div.list_items table tr")
        for row in rows:
            cols = row.find_all("td")
            if len(cols) >= 2:
                results.append({
                    "Substance": substance_name,
                    "Substance_ID": substance_id,
                    "Food_Type": cols[0].get_text(separator=' ').strip(),
                    "MRL_ppm": cols[1].text.strip(),
                    "Basis": cols[2].text.strip() if len(cols) > 2 else "",
                    "Note": cols[3].text.strip() if len(cols) > 3 else ""
                })
        return results

    def test_run(self, limit_substances=3):
        # 1. Map IDs (only for 'a' to keep it fast)
        mapping = self.get_all_substance_ids(limit_chars=1)
        if not mapping:
            print("No IDs found. Check selectors or session.")
            return

        all_results = []
        print(f"\n[2/2] 상세 데이터 수집 테스트 시작 (대상: 상위 {min(len(mapping), limit_substances)}개)...")
        
        count = 0
        for name, sid in list(mapping.items())[:limit_substances]:
            print(f" - Collecting: {name} (ID: {sid})")
            details = self.get_mrl_details(sid)
            all_results.extend(details)
            count += 1
            time.sleep(0.5)

        # 4. Save to CSV
        output_file = "ffcr_test_results.csv"
        df = pd.DataFrame(all_results)
        df.to_csv(output_file, index=False, encoding="utf-8-sig")
        print(f"\nTest finished! Results saved to '{output_file}' ({len(df)} rows)")
        print("\n--- SAMPLE DATA ---")
        print(df.head(10).to_string())

if __name__ == "__main__":
    scraper = FFCRScraper()
    scraper.test_run()
